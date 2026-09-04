"""Measurements, which always carry uncertainty. Build spec 7, 14.

POST returns 409 when survey.georef = 'none': a scale-free model is correct in
shape and arbitrary in size, and looks perfect. Return 409, do not warn.
"""

from __future__ import annotations

import math
import uuid

from fastapi import APIRouter, HTTPException, status
from geoalchemy2.shape import from_shape
from pydantic import BaseModel, Field
from shapely.geometry import LineString, Point, Polygon
from sqlalchemy import select

from groma_api.db import models as m
from groma_api.deps import DB, CurrentUser, Surveyor
from groma_api.geom import origin_of
from groma_api.routers.portfolio import get_venue
from groma_api.routers.surveys import get_survey
from groma_contracts.measurement import Measurement, MeasurementKind, SnapMode, format_measurement
from groma_geo.origin import to_storage

router = APIRouter(prefix="/api", tags=["measurements"])

K_H = 1.5
K_V = 3.0


class MeasurementCreate(BaseModel):
    survey_id: uuid.UUID
    kind: MeasurementKind
    points: list[tuple[float, float, float]] = Field(min_length=1)
    """Snapped points in local ENU metres, Y up."""
    snap_modes: list[SnapMode] = Field(min_length=1)
    snap_sigmas_m: list[float] = Field(min_length=1)
    """sigma_snap per point, from the snapping hierarchy (build spec 14.1)."""


class MeasurementOut(Measurement):
    formatted: str


def survey_sigmas(s: m.Survey) -> tuple[float, float, str]:
    """(sigma_h, sigma_v, note) from the survey's accuracy report. Build spec 14.3.

    Check-point RMSE is the honest number. Where only control points exist, use
    them with a 50% penalty and say so. Where neither exists the survey is
    georef = none and the caller has already been refused.
    """
    acc = s.accuracy or {}
    gsd = float(acc.get("gsd_m") or 0.0)
    if acc.get("check_rmse_h_m") is not None:
        rh, rv = (
            float(acc["check_rmse_h_m"]),
            float(acc.get("check_rmse_v_m") or acc["check_rmse_h_m"]),
        )
        note = "check points"
    elif acc.get("gcp_rmse_h_m") is not None:
        rh, rv = (
            1.5 * float(acc["gcp_rmse_h_m"]),
            1.5 * float(acc.get("gcp_rmse_v_m") or acc["gcp_rmse_h_m"]),
        )
        note = "control points +50% (no check points)"
    else:
        rh = rv = 0.0
        note = "no georeferencing residuals recorded"
    return math.hypot(K_H * gsd, rh), math.hypot(K_V * gsd, rv), note


def evaluate(
    kind: MeasurementKind,
    pts: list[tuple[float, float, float]],
    sig_h: float,
    sig_v: float,
    snap: list[float],
) -> tuple[float, float, str]:
    """(value, uncertainty, unit). Per-point anisotropic uncertainty projected onto
    the measurement direction and combined in quadrature."""

    def sigma_along(i: int, dx: float, dy: float, dz: float) -> float:
        n = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
        h = math.hypot(dx, dz) / n
        v = abs(dy) / n
        return math.sqrt((h * sig_h) ** 2 + (v * sig_v) ** 2 + snap[min(i, len(snap) - 1)] ** 2)

    if kind in (
        MeasurementKind.DISTANCE,
        MeasurementKind.HORIZONTAL_DISTANCE,
        MeasurementKind.VERTICAL_DIFFERENCE,
        MeasurementKind.ELEVATION_DIFFERENCE,
        MeasurementKind.CLEARANCE,
    ):
        if len(pts) < 2:
            raise HTTPException(422, f"{kind.value} needs two points")
        (x0, y0, z0), (x1, y1, z1) = pts[0], pts[1]
        dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
        if kind is MeasurementKind.HORIZONTAL_DISTANCE:
            dy = 0.0
        if kind in (MeasurementKind.VERTICAL_DIFFERENCE, MeasurementKind.ELEVATION_DIFFERENCE):
            dx = dz = 0.0
        value = math.sqrt(dx * dx + dy * dy + dz * dz)
        unc = math.hypot(sigma_along(0, dx, dy, dz), sigma_along(1, dx, dy, dz))
        return value, unc, "m"
    if kind is MeasurementKind.HEIGHT:
        # Height above local ground: one point, vertical sigma plus the terrain's.
        y = pts[0][1] - (pts[1][1] if len(pts) > 1 else 0.0)
        return y, math.hypot(sig_v, snap[0], snap[-1]), "m"
    if kind is MeasurementKind.POLYLINE_LENGTH:
        total = 0.0
        var = 0.0
        for i in range(len(pts) - 1):
            (x0, y0, z0), (x1, y1, z1) = pts[i], pts[i + 1]
            dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
            total += math.sqrt(dx * dx + dy * dy + dz * dz)
            var += sigma_along(i, dx, dy, dz) ** 2 + sigma_along(i + 1, dx, dy, dz) ** 2
        return total, math.sqrt(var), "m"
    if kind in (MeasurementKind.AREA, MeasurementKind.FOOTPRINT_AREA):
        if len(pts) < 3:
            raise HTTPException(422, "an area needs three points")
        poly = Polygon([(x, z) for x, _, z in pts])
        area = float(abs(poly.area))
        # dA ~ perimeter * sigma_h for a boundary uncertain by sigma_h everywhere.
        unc = float(poly.length) * math.hypot(sig_h, max(snap))
        return area, unc, "m2"
    if kind is MeasurementKind.SLOPE:
        if len(pts) < 2:
            raise HTTPException(422, "slope needs two points")
        (x0, y0, z0), (x1, y1, z1) = pts[0], pts[1]
        run = math.hypot(x1 - x0, z1 - z0)
        if run <= 0:
            raise HTTPException(422, "slope needs horizontal separation")
        rise = y1 - y0
        value = 100.0 * rise / run
        unc = 100.0 * math.hypot(
            math.hypot(sig_v, snap[0], snap[-1]) / run, abs(rise) * sig_h / (run * run)
        )
        return value, unc, "%"
    if kind is MeasurementKind.VOLUME:
        raise HTTPException(422, "volume needs a surface; lands with the DSM in M12")
    raise HTTPException(422, f"unsupported kind {kind.value}")


def to_out(row: m.Measurement, pts: list[tuple[float, float, float]]) -> MeasurementOut:
    return MeasurementOut(
        id=str(row.id),
        venue_id=str(row.venue_id),
        survey_id=str(row.survey_id),
        kind=MeasurementKind(row.kind),
        value=row.value,
        uncertainty=row.uncertainty,
        unit=row.unit,
        snap_mode=SnapMode(row.snap_mode),
        points=pts,
        created_by=row.created_by,
        created_at=row.created_at,
        formatted=format_measurement(row.value, row.uncertainty, row.unit),
    )


@router.post("/measurements", response_model=MeasurementOut, status_code=201)
def create_measurement(body: MeasurementCreate, user: Surveyor, db: DB) -> MeasurementOut:
    s = get_survey(db, body.survey_id)
    if s.georef == "none":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "this survey is not georeferenced (georef = none): the model is correct in "
            "shape and arbitrary in size, so no dimension from it is valid",
        )
    sig_h, sig_v, _note = survey_sigmas(s)
    value, unc, unit = evaluate(body.kind, body.points, sig_h, sig_v, body.snap_sigmas_m)
    origin = origin_of(get_venue(db, s.venue_id))
    en = to_storage(body.points, origin)
    coords = [(float(e), float(n), float(h)) for e, n, h in en]
    geom = (
        Point(coords[0])
        if len(coords) == 1
        else (
            Polygon(coords)
            if body.kind in (MeasurementKind.AREA, MeasurementKind.FOOTPRINT_AREA)
            else LineString(coords)
        )
    )
    worst = max(
        body.snap_modes,
        key=lambda sm: [
            SnapMode.PRIMITIVE_FEATURE,
            SnapMode.TERRAIN,
            SnapMode.LOCAL_PLANE,
            SnapMode.NEAREST_POINT,
        ].index(sm),
    )
    row = m.Measurement(
        venue_id=s.venue_id,
        survey_id=s.id,
        kind=body.kind.value,
        geom=from_shape(geom, srid=0),
        value=value,
        uncertainty=unc,
        unit=unit,
        snap_mode=worst.value,
        created_by=user.email,
    )
    db.add(row)
    db.commit()
    return to_out(row, body.points)


@router.get("/venues/{venue_id}/measurements", response_model=list[MeasurementOut])
def list_measurements(venue_id: uuid.UUID, _: CurrentUser, db: DB) -> list[MeasurementOut]:
    v = get_venue(db, venue_id)
    origin = origin_of(v)
    from geoalchemy2.shape import to_shape

    from groma_geo.origin import to_local

    out = []
    for row in db.scalars(
        select(m.Measurement)
        .where(m.Measurement.venue_id == venue_id)
        .order_by(m.Measurement.created_at.desc())
    ):
        shape = to_shape(row.geom)
        coords = (
            list(shape.exterior.coords)[:-1] if shape.geom_type == "Polygon" else list(shape.coords)
        )
        local = to_local([(c[0], c[1], c[2] if len(c) > 2 else 0.0) for c in coords], origin)
        out.append(to_out(row, [(float(x), float(y), float(z)) for x, y, z in local]))
    return out
