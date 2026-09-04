"""Organisations, venues, facilities and the portfolio health view. Build spec 7."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from groma_api.db import models as m
from groma_api.deps import DB, CurrentUser, Surveyor
from groma_api.geom import storage_polygon, storage_polygon_coords
from groma_contracts.camera import DoriTier
from groma_contracts.org import Facility, FacilityHealth, FacilityKind, Venue, VenueSummary
from groma_contracts.site import HeightDatum

router = APIRouter(prefix="/api", tags=["portfolio"])


class VenueCreate(BaseModel):
    name: str
    reference: str | None = None
    address: str | None = None
    srid: int | None = None
    origin_x: float
    origin_y: float
    origin_z: float = 0.0
    height_datum: HeightDatum = HeightDatum.ORTHOMETRIC_MPD
    boundary: list[tuple[float, float]] | None = None
    centroid_lon: float | None = None
    centroid_lat: float | None = None
    survey_interval_months: int = 24


class FacilityCreate(BaseModel):
    name: str
    kind: FacilityKind
    boundary: list[tuple[float, float]] = Field(min_length=3)
    nominal_dims: dict[str, float] | None = None
    target_tier: DoriTier = DoriTier.DETECT
    target_pct: float = 95.0


class FacilityPatch(BaseModel):
    name: str | None = None
    boundary: list[tuple[float, float]] | None = Field(default=None, min_length=3)
    nominal_dims: dict[str, float] | None = None
    target_tier: DoriTier | None = None
    target_pct: float | None = None


def to_venue(v: m.Venue) -> Venue:
    lon = lat = None
    if v.centroid_wgs is not None:
        from geoalchemy2.shape import to_shape

        p = to_shape(v.centroid_wgs)
        lon, lat = float(p.x), float(p.y)
    return Venue(
        id=str(v.id),
        org_id=str(v.org_id),
        name=v.name,
        reference=v.reference,
        address=v.address,
        srid=v.srid,
        origin_x=v.origin_x,
        origin_y=v.origin_y,
        origin_z=v.origin_z,
        height_datum=HeightDatum(v.height_datum),
        boundary=storage_polygon_coords(v.boundary),
        centroid_lon=lon,
        centroid_lat=lat,
        survey_interval_months=v.survey_interval_months,
        created_at=v.created_at,
    )


def to_facility(f: m.Facility) -> Facility:
    return Facility(
        id=str(f.id),
        venue_id=str(f.venue_id),
        name=f.name,
        kind=FacilityKind(f.kind),
        boundary=storage_polygon_coords(f.boundary) or [],
        nominal_dims=f.nominal_dims,
        target_tier=DoriTier(f.target_tier),
        target_pct=f.target_pct,
        created_at=f.created_at,
    )


def get_venue(db: Session, venue_id: uuid.UUID) -> m.Venue:
    v = db.get(m.Venue, venue_id)
    if v is None:
        raise HTTPException(404, "no such venue")
    return v


def get_facility(db: Session, facility_id: uuid.UUID) -> m.Facility:
    f = db.get(m.Facility, facility_id)
    if f is None:
        raise HTTPException(404, "no such facility")
    return f


def latest_complete_survey(db: Session, venue_id: uuid.UUID) -> m.Survey | None:
    return db.scalar(
        select(m.Survey)
        .where(m.Survey.venue_id == venue_id, m.Survey.status == "complete")
        .order_by(m.Survey.flown_at.desc().nullslast(), m.Survey.created_at.desc())
        .limit(1)
    )


def latest_run_for_facility(db: Session, facility_id: uuid.UUID) -> m.CoverageRun | None:
    return db.scalar(
        select(m.CoverageRun)
        .join(m.Scenario, m.Scenario.id == m.CoverageRun.scenario_id)
        .where(m.Scenario.facility_id == facility_id)
        .order_by(m.CoverageRun.computed_at.desc())
        .limit(1)
    )


def facility_health(db: Session, v: m.Venue, f: m.Facility, today: date) -> FacilityHealth:
    run = latest_run_for_facility(db, f.id)
    survey = latest_complete_survey(db, v.id)
    pct = None
    meets = None
    if run is not None:
        stats = run.stats
        area = float(stats.get("area_m2") or 0.0)
        tier_area = float((stats.get("tier_area_m2") or {}).get(f.target_tier, 0.0))
        pct = 100.0 * tier_area / area if area > 0 else 0.0
        meets = pct >= f.target_pct
    stale = False
    if survey is not None and survey.flown_at is not None:
        stale = survey.flown_at < today - timedelta(days=30 * v.survey_interval_months)
    return FacilityHealth(
        venue_id=str(v.id),
        venue_name=v.name,
        facility_id=str(f.id),
        facility_name=f.name,
        kind=FacilityKind(f.kind),
        target_tier=DoriTier(f.target_tier),
        target_pct=f.target_pct,
        latest_run_id=str(run.id) if run else None,
        latest_pct=pct,
        meets_target=meets,
        last_survey_id=str(survey.id) if survey else None,
        last_survey_flown_at=survey.flown_at if survey else None,
        stale=stale,
    )


@router.get("/orgs/{org_id}/venues", response_model=list[VenueSummary])
def portfolio(org_id: uuid.UUID, user: CurrentUser, db: DB) -> list[VenueSummary]:
    if user.org_id != org_id:
        raise HTTPException(403, "not your organisation")
    today = datetime.now(UTC).date()
    out: list[VenueSummary] = []
    for v in db.scalars(select(m.Venue).where(m.Venue.org_id == org_id).order_by(m.Venue.name)):
        facilities = list(db.scalars(select(m.Facility).where(m.Facility.venue_id == v.id)))
        surveys = list(db.scalars(select(m.Survey).where(m.Survey.venue_id == v.id)))
        latest = latest_complete_survey(db, v.id)
        health = [facility_health(db, v, f, today) for f in facilities]
        out.append(
            VenueSummary(
                venue=to_venue(v),
                facility_count=len(facilities),
                survey_count=len(surveys),
                latest_survey_id=str(latest.id) if latest else None,
                latest_survey_flown_at=latest.flown_at if latest else None,
                stale=any(h.stale for h in health),
                health=health,
            )
        )
    return out


@router.get("/orgs/{org_id}/coverage-health", response_model=list[FacilityHealth])
def coverage_health(org_id: uuid.UUID, user: CurrentUser, db: DB) -> list[FacilityHealth]:
    if user.org_id != org_id:
        raise HTTPException(403, "not your organisation")
    today = datetime.now(UTC).date()
    rows: list[FacilityHealth] = []
    for v in db.scalars(select(m.Venue).where(m.Venue.org_id == org_id)):
        for f in db.scalars(select(m.Facility).where(m.Facility.venue_id == v.id)):
            rows.append(facility_health(db, v, f, today))
    # Worst first: below target, then unknown, then meeting target.
    rows.sort(key=lambda h: (h.meets_target is True, h.meets_target is None, h.latest_pct or 0.0))
    return rows


@router.post("/venues", response_model=Venue, status_code=201)
def create_venue(body: VenueCreate, user: Surveyor, db: DB) -> Venue:
    org = db.get(m.Organisation, user.org_id)
    assert org is not None
    v = m.Venue(
        org_id=user.org_id,
        name=body.name,
        reference=body.reference,
        address=body.address,
        srid=body.srid or org.default_srid,
        origin_x=body.origin_x,
        origin_y=body.origin_y,
        origin_z=body.origin_z,
        height_datum=body.height_datum.value,
        boundary=storage_polygon(body.boundary) if body.boundary else None,
        survey_interval_months=body.survey_interval_months,
    )
    if body.centroid_lon is not None and body.centroid_lat is not None:
        from geoalchemy2.shape import from_shape
        from shapely.geometry import Point

        v.centroid_wgs = from_shape(Point(body.centroid_lon, body.centroid_lat), srid=4326)
    db.add(v)
    db.commit()
    return to_venue(v)


@router.get("/venues/{venue_id}", response_model=Venue)
def read_venue(venue_id: uuid.UUID, _: CurrentUser, db: DB) -> Venue:
    return to_venue(get_venue(db, venue_id))


@router.get("/venues/{venue_id}/facilities", response_model=list[Facility])
def list_facilities(venue_id: uuid.UUID, _: CurrentUser, db: DB) -> list[Facility]:
    get_venue(db, venue_id)
    return [
        to_facility(f)
        for f in db.scalars(select(m.Facility).where(m.Facility.venue_id == venue_id))
    ]


@router.post("/venues/{venue_id}/facilities", response_model=Facility, status_code=201)
def create_facility(venue_id: uuid.UUID, body: FacilityCreate, _: Surveyor, db: DB) -> Facility:
    get_venue(db, venue_id)
    f = m.Facility(
        venue_id=venue_id,
        name=body.name,
        kind=body.kind.value,
        boundary=storage_polygon(body.boundary),
        nominal_dims=body.nominal_dims,
        target_tier=body.target_tier.value,
        target_pct=body.target_pct,
    )
    db.add(f)
    db.commit()
    return to_facility(f)


@router.patch("/facilities/{facility_id}", response_model=Facility)
def patch_facility(facility_id: uuid.UUID, body: FacilityPatch, _: Surveyor, db: DB) -> Facility:
    f = get_facility(db, facility_id)
    if body.name is not None:
        f.name = body.name
    if body.boundary is not None:
        f.boundary = storage_polygon(body.boundary)
    if body.nominal_dims is not None:
        f.nominal_dims = body.nominal_dims
    if body.target_tier is not None:
        f.target_tier = body.target_tier.value
    if body.target_pct is not None:
        f.target_pct = body.target_pct
    db.commit()
    return to_facility(f)


@router.get("/facilities/{facility_id}/latest-coverage")
def facility_latest_coverage(
    facility_id: uuid.UUID, _: CurrentUser, db: DB
) -> dict[str, Any] | None:
    get_facility(db, facility_id)
    run = latest_run_for_facility(db, facility_id)
    if run is None:
        return None
    from groma_api.routers.coverage import to_run

    return to_run(db, run).model_dump(mode="json")
