"""Surveys: create, list, QA gate, supersede, artefacts. Build spec 7, 8.7.

Immutability: a survey with immutable = true rejects all mutations except
superseded_by. Reconstruction is gated on capture_qa.blocking being acknowledged.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from groma_api.db import models as m
from groma_api.deps import DB, CurrentUser, Surveyor
from groma_api.routers.portfolio import get_venue
from groma_contracts.imagery import CaptureQA
from groma_contracts.survey import AccuracyReport, Artefact, GeorefMethod, Survey, SurveyStatus

router = APIRouter(prefix="/api", tags=["surveys"])


class SurveyCreate(BaseModel):
    name: str
    flown_at: date | None = None
    platform: str | None = None
    georef: GeorefMethod = GeorefMethod.NONE
    facility_ids: list[uuid.UUID] = []


class SurveyPatch(BaseModel):
    name: str | None = None
    flown_at: date | None = None
    platform: str | None = None
    georef: GeorefMethod | None = None


def to_survey(s: m.Survey) -> Survey:
    return Survey(
        id=str(s.id),
        venue_id=str(s.venue_id),
        name=s.name,
        flown_at=s.flown_at,
        platform=s.platform,
        georef=GeorefMethod(s.georef),
        status=SurveyStatus(s.status),
        engine=s.engine,
        capture_qa=CaptureQA.model_validate(s.capture_qa) if s.capture_qa else None,
        accuracy=AccuracyReport.model_validate(s.accuracy) if s.accuracy else None,
        immutable=s.immutable,
        superseded_by=str(s.superseded_by) if s.superseded_by else None,
        created_at=s.created_at,
    )


def get_survey(db: Session, survey_id: uuid.UUID) -> m.Survey:
    s = db.get(m.Survey, survey_id)
    if s is None:
        raise HTTPException(404, "no such survey")
    return s


def mutable(s: m.Survey) -> m.Survey:
    if s.immutable:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "this survey is complete and immutable; supersede it to make changes",
        )
    return s


@router.get("/venues/{venue_id}/surveys", response_model=list[Survey])
def list_surveys(venue_id: uuid.UUID, _: CurrentUser, db: DB) -> list[Survey]:
    get_venue(db, venue_id)
    rows = db.scalars(
        select(m.Survey)
        .where(m.Survey.venue_id == venue_id)
        .order_by(m.Survey.flown_at.desc().nullslast(), m.Survey.created_at.desc())
    )
    return [to_survey(s) for s in rows]


@router.post("/venues/{venue_id}/surveys", response_model=Survey, status_code=201)
def create_survey(venue_id: uuid.UUID, body: SurveyCreate, user: Surveyor, db: DB) -> Survey:
    get_venue(db, venue_id)
    s = m.Survey(
        venue_id=venue_id,
        name=body.name,
        flown_at=body.flown_at,
        platform=body.platform,
        georef=body.georef.value,
        status="draft",
        created_by=user.email,
    )
    db.add(s)
    db.flush()
    for fid in body.facility_ids:
        db.add(m.SurveyFacility(survey_id=s.id, facility_id=fid))
    db.commit()
    return to_survey(s)


@router.get("/surveys/{survey_id}", response_model=Survey)
def read_survey(survey_id: uuid.UUID, _: CurrentUser, db: DB) -> Survey:
    return to_survey(get_survey(db, survey_id))


@router.patch("/surveys/{survey_id}", response_model=Survey)
def patch_survey(survey_id: uuid.UUID, body: SurveyPatch, _: Surveyor, db: DB) -> Survey:
    s = mutable(get_survey(db, survey_id))
    for field in ("name", "flown_at", "platform"):
        value = getattr(body, field)
        if value is not None:
            setattr(s, field, value)
    if body.georef is not None:
        s.georef = body.georef.value
    db.commit()
    return to_survey(s)


@router.get("/surveys/{survey_id}/qa", response_model=CaptureQA | None)
def read_qa(survey_id: uuid.UUID, _: CurrentUser, db: DB) -> CaptureQA | None:
    s = get_survey(db, survey_id)
    return CaptureQA.model_validate(s.capture_qa) if s.capture_qa else None


@router.post("/surveys/{survey_id}/qa:acknowledge", response_model=Survey)
def acknowledge_qa(survey_id: uuid.UUID, user: Surveyor, db: DB) -> Survey:
    """Records who accepted the blocking items and when. The items stay in the
    report; only the gate opens."""
    s = mutable(get_survey(db, survey_id))
    if not s.capture_qa or not s.capture_qa.get("blocking"):
        raise HTTPException(status.HTTP_409_CONFLICT, "nothing to acknowledge")
    s.qa_acknowledged_by = user.email
    s.qa_acknowledged_at = datetime.now(UTC)
    db.commit()
    return to_survey(s)


def reconstruction_gate(s: m.Survey) -> None:
    """Build spec 8.7: 409 while capture_qa.blocking is non-empty and unacknowledged."""
    blocking = (s.capture_qa or {}).get("blocking") or []
    if blocking and s.qa_acknowledged_at is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "message": "capture QA has blocking items that must be acknowledged",
                "blocking": blocking,
            },
        )


@router.post("/surveys/{survey_id}/supersede", response_model=Survey, status_code=201)
def supersede(survey_id: uuid.UUID, user: Surveyor, db: DB) -> Survey:
    """A new draft that copies the old survey's GCPs; the old one is never mutated."""
    old = get_survey(db, survey_id)
    new = m.Survey(
        venue_id=old.venue_id,
        name=f"{old.name} (re-flight)",
        platform=old.platform,
        georef=old.georef,
        status="draft",
        created_by=user.email,
    )
    db.add(new)
    db.flush()
    for sf in db.scalars(select(m.SurveyFacility).where(m.SurveyFacility.survey_id == old.id)):
        db.add(m.SurveyFacility(survey_id=new.id, facility_id=sf.facility_id))
    for g in db.scalars(select(m.Gcp).where(m.Gcp.survey_id == old.id)):
        db.add(m.Gcp(survey_id=new.id, label=g.label, position=g.position, role=g.role))
    old.superseded_by = new.id
    db.commit()
    return to_survey(new)


@router.get("/surveys/{survey_id}/artefacts", response_model=list[Artefact])
def list_artefacts(survey_id: uuid.UUID, _: CurrentUser, db: DB) -> list[Artefact]:
    get_survey(db, survey_id)
    return [
        Artefact(
            id=str(a.id),
            survey_id=str(a.survey_id),
            kind=a.kind,
            uri=a.uri,
            bytes=a.bytes,
            sha256=a.sha256,
            meta=a.meta or {},
            created_at=a.created_at,
        )
        for a in db.scalars(select(m.Artefact).where(m.Artefact.survey_id == survey_id))
    ]


@router.get("/surveys/{survey_id}/accuracy", response_model=AccuracyReport | None)
def read_accuracy(survey_id: uuid.UUID, _: CurrentUser, db: DB) -> AccuracyReport | None:
    s = get_survey(db, survey_id)
    return AccuracyReport.model_validate(s.accuracy) if s.accuracy else None
