"""Structure review and mount points. Build spec 7, 12.4, 12.6, 12.7.

Review requires the surveyor role: the audit trail is worthless if anonymous.
Structures are stored in local ENU relative to the venue origin, so no rebasing
happens here; mount points and cameras are PostGIS points and do rebase.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field, TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from groma_api.db import models as m
from groma_api.deps import DB, CurrentUser, Surveyor
from groma_api.geom import origin_of, point_to_local, point_to_storage
from groma_api.routers.portfolio import get_venue
from groma_api.routers.surveys import get_survey
from groma_contracts.geometry import CylinderPrim, Primitive, Vec3
from groma_contracts.structure import (
    Evidence,
    MountingType,
    MountPoint,
    RejectReason,
    ReviewState,
    Structure,
    StructureClass,
)

router = APIRouter(prefix="/api", tags=["structures"])

_prim: TypeAdapter[Primitive] = TypeAdapter(Primitive)


def to_structure(s: m.Structure) -> Structure:
    return Structure(
        id=str(s.id),
        survey_id=str(s.survey_id),
        cls=StructureClass(s.cls),
        name=s.name,
        confidence=s.confidence,
        state=ReviewState(s.state),
        reject_reason=RejectReason(s.reject_reason) if s.reject_reason else None,
        primitive=_prim.validate_python(s.primitive),
        porosity=s.porosity,
        mountable=s.mountable,
        fit_rmse_m=s.fit_rmse_m,
        point_count=s.point_count,
        origin=s.origin,
        view_count=s.view_count,
        mean_incidence_deg=s.mean_incidence_deg,
        accuracy_m=s.accuracy_m,
        evidence=[Evidence.model_validate(e) for e in (s.evidence or [])],
        reviewed_by=s.reviewed_by,
        reviewed_at=s.reviewed_at,
    )


def get_structure(db: Session, structure_id: uuid.UUID) -> m.Structure:
    s = db.get(m.Structure, structure_id)
    if s is None:
        raise HTTPException(404, "no such structure")
    return s


class StructurePatch(BaseModel):
    state: ReviewState | None = None
    reject_reason: RejectReason | None = None
    cls: StructureClass | None = None
    primitive: Primitive | None = None
    porosity: float | None = Field(default=None, ge=0, le=1)
    mountable: bool | None = None
    name: str | None = None


class StructureCreate(BaseModel):
    name: str
    cls: StructureClass
    primitive: Primitive
    porosity: float = Field(default=0.0, ge=0, le=1)
    mountable: bool = False
    state: ReviewState = ReviewState.ACCEPTED
    """A manually drawn structure is accepted by the person drawing it; use
    `seasonal` for vegetation that is only there part of the year."""


class BulkReview(BaseModel):
    ids: list[uuid.UUID]
    state: ReviewState
    reject_reason: RejectReason | None = None


class StructurePage(BaseModel):
    items: list[Structure]
    next_cursor: str | None = None


@router.get("/surveys/{survey_id}/structures", response_model=StructurePage)
def list_structures(
    survey_id: uuid.UUID,
    _: CurrentUser,
    db: DB,
    state: ReviewState | None = None,
    cls: StructureClass | None = None,
    cursor: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> StructurePage:
    """Keyset-paginated on (name, id): a survey can have thousands of candidates."""
    get_survey(db, survey_id)
    q = select(m.Structure).where(m.Structure.survey_id == survey_id)
    if state is not None:
        q = q.where(m.Structure.state == state.value)
    if cls is not None:
        q = q.where(m.Structure.cls == cls.value)
    if cursor:
        c_name, c_id = cursor.split("|", 1)
        q = q.where(
            (m.Structure.name > c_name)
            | ((m.Structure.name == c_name) & (m.Structure.id > uuid.UUID(c_id)))
        )
    rows = list(db.scalars(q.order_by(m.Structure.name, m.Structure.id).limit(limit + 1)))
    nxt = None
    if len(rows) > limit:
        rows = rows[:limit]
        nxt = f"{rows[-1].name}|{rows[-1].id}"
    return StructurePage(items=[to_structure(s) for s in rows], next_cursor=nxt)


def apply_review(s: m.Structure, body: StructurePatch, user: m.User) -> None:
    now = datetime.now(UTC)
    if body.state is not None:
        if (
            body.state is ReviewState.REJECTED
            and body.reject_reason is None
            and not s.reject_reason
        ):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "rejection is typed: give reject_reason = noise | transient | duplicate",
            )
        s.state = body.state.value
        s.reject_reason = (
            body.reject_reason.value
            if body.reject_reason
            else (s.reject_reason if body.state is ReviewState.REJECTED else None)
        )
        s.reviewed_by = user.email
        s.reviewed_at = now
    if body.cls is not None and body.cls.value != s.cls:
        s.cls = body.cls.value
        s.primitive = refit(s, body.cls).model_dump(mode="json")
        s.mountable = body.cls in (
            StructureClass.POLE,
            StructureClass.BUILDING,
            StructureClass.STAND,
        )
        s.reviewed_by = user.email
        s.reviewed_at = now
    if body.primitive is not None:
        s.primitive = body.primitive.model_dump(mode="json")
        s.origin = "adjusted"
        s.reviewed_by = user.email
        s.reviewed_at = now
    if body.porosity is not None:
        s.porosity = body.porosity
    if body.mountable is not None:
        s.mountable = body.mountable
    if body.name is not None:
        s.name = body.name


def refit(s: m.Structure, cls: StructureClass) -> Primitive:
    """Reclassifying refits with the new class's fitter. Until M10 lands the
    point cloud, the refit is geometric: a fence becomes thin, a wall solid."""
    prim: Primitive = _prim.validate_python(s.primitive)
    if cls is StructureClass.FENCE and prim.kind == "polyline":
        thinner: Primitive = prim.model_copy(update={"thickness": min(prim.thickness, 0.12)})
        return thinner
    if cls is StructureClass.FENCE and prim.kind == "box":
        import math

        from groma_contracts.geometry import ExtrudedPolyline

        c, s_ = math.cos(prim.yaw), math.sin(prim.yaw)
        a = (prim.cx - prim.hx * c, prim.cz + prim.hx * s_)
        b = (prim.cx + prim.hx * c, prim.cz - prim.hx * s_)
        return ExtrudedPolyline(
            points=[a, b], y0=prim.cy - prim.hy, y1=prim.cy + prim.hy, thickness=0.12
        )
    return prim


@router.patch("/structures/{structure_id}", response_model=Structure)
def patch_structure(
    structure_id: uuid.UUID, body: StructurePatch, user: Surveyor, db: DB
) -> Structure:
    s = get_structure(db, structure_id)
    apply_review(s, body, user)
    db.commit()
    return to_structure(s)


@router.post("/structures/{structure_id}/refit", response_model=Structure)
def refit_structure(structure_id: uuid.UUID, user: Surveyor, db: DB) -> Structure:
    s = get_structure(db, structure_id)
    s.primitive = refit(s, StructureClass(s.cls)).model_dump(mode="json")
    s.reviewed_by = user.email
    s.reviewed_at = datetime.now(UTC)
    db.commit()
    return to_structure(s)


@router.patch("/structures/{structure_id}/mountable", response_model=Structure)
def set_mountable(structure_id: uuid.UUID, mountable: bool, user: Surveyor, db: DB) -> Structure:
    s = get_structure(db, structure_id)
    s.mountable = mountable
    s.reviewed_by = user.email
    s.reviewed_at = datetime.now(UTC)
    db.commit()
    return to_structure(s)


@router.post("/structures:bulk-review", response_model=list[Structure])
def bulk_review(body: BulkReview, user: Surveyor, db: DB) -> list[Structure]:
    out = []
    for sid in body.ids:
        s = get_structure(db, sid)
        apply_review(s, StructurePatch(state=body.state, reject_reason=body.reject_reason), user)
        out.append(s)
    db.commit()
    return [to_structure(s) for s in out]


@router.post("/surveys/{survey_id}/structures", response_model=Structure, status_code=201)
def create_structure(
    survey_id: uuid.UUID, body: StructureCreate, user: Surveyor, db: DB
) -> Structure:
    """A manual structure for anything extraction missed. origin = 'manual'."""
    get_survey(db, survey_id)
    s = m.Structure(
        survey_id=survey_id,
        cls=body.cls.value,
        name=body.name,
        confidence=1.0,
        state=body.state.value,
        primitive=body.primitive.model_dump(mode="json"),
        porosity=body.porosity,
        mountable=body.mountable,
        origin="manual",
        reviewed_by=user.email,
        reviewed_at=datetime.now(UTC),
    )
    db.add(s)
    db.commit()
    return to_structure(s)


@router.get("/structures/{structure_id}/evidence", response_model=list[Evidence])
def structure_evidence(structure_id: uuid.UUID, _: CurrentUser, db: DB) -> list[Evidence]:
    return [Evidence.model_validate(e) for e in (get_structure(db, structure_id).evidence or [])]


# ---- mount points ---------------------------------------------------------------


def to_mount(mp: m.MountPoint, origin) -> MountPoint:  # type: ignore[no-untyped-def]
    return MountPoint(
        id=str(mp.id),
        venue_id=str(mp.venue_id),
        structure_id=str(mp.structure_id) if mp.structure_id else None,
        position=point_to_local(mp.position, origin),
        normal=Vec3.model_validate(mp.normal) if mp.normal else None,
        origin=mp.origin,
        mounting_type=MountingType(mp.mounting_type) if mp.mounting_type else None,
        height_agl_m=mp.height_agl_m,
        max_load_kg=mp.max_load_kg,
        cable_run_m=mp.cable_run_m,
        accuracy_m=mp.accuracy_m,
        confidence=mp.confidence,
        state=ReviewState(mp.state),
        label=mp.label,
        created_by=mp.created_by,
        created_at=mp.created_at,
    )


class MountCreate(BaseModel):
    """Build spec 12.7: a camera dropped onto a spot."""

    position: Vec3
    normal: Vec3 | None = None
    structure_id: uuid.UUID | None = None
    landed_on: Literal["structure", "mesh", "terrain", "none"] = "structure"
    mounting_type: MountingType | None = None
    height_agl_m: float
    max_load_kg: float | None = None
    cable_run_m: float | None = None
    label: str | None = None
    accept_rejected_structure: bool = False
    proposed_mast_height_m: float | None = None
    proposed_mast_radius_m: float = 0.15


class MountPatch(BaseModel):
    state: ReviewState | None = None
    max_load_kg: float | None = None
    cable_run_m: float | None = None
    label: str | None = None
    mounting_type: MountingType | None = None


@router.get("/venues/{venue_id}/mount-points", response_model=list[MountPoint])
def list_mounts(venue_id: uuid.UUID, _: CurrentUser, db: DB) -> list[MountPoint]:
    v = get_venue(db, venue_id)
    origin = origin_of(v)
    return [
        to_mount(mp, origin)
        for mp in db.scalars(select(m.MountPoint).where(m.MountPoint.venue_id == venue_id))
    ]


@router.post("/venues/{venue_id}/mount-points", response_model=MountPoint, status_code=201)
def create_mount(venue_id: uuid.UUID, body: MountCreate, user: Surveyor, db: DB) -> MountPoint:
    v = get_venue(db, venue_id)
    origin = origin_of(v)
    structure_id = body.structure_id
    mp_origin = "manual"
    if body.landed_on == "structure":
        if structure_id is None:
            raise HTTPException(422, "landed_on = structure needs structure_id")
        s = get_structure(db, structure_id)
        if s.state == "rejected":
            # Never silent: the occlusion model does not believe this exists.
            if not body.accept_rejected_structure:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    {
                        "message": f"{s.name} is rejected; a camera on it would be mounted on "
                        "something the occlusion model does not believe exists",
                        "structure_id": str(s.id),
                        "fix": "resend with accept_rejected_structure = true to accept it",
                    },
                )
            s.state = "accepted"
            s.reject_reason = None
            s.reviewed_by = user.email
            s.reviewed_at = datetime.now(UTC)
        if s.insufficient_for_mount_design_flag():
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{s.name} is insufficient for mount design (view_count {s.view_count}, "
                f"accuracy {s.accuracy_m} m); it stays an occluder only",
            )
    elif body.landed_on == "terrain":
        # A proposed new mast: the mount point AND an accepted occluder, because a
        # mast you are about to install is itself an occluder (build spec 12.7).
        if body.proposed_mast_height_m is None:
            raise HTTPException(422, "a terrain drop needs proposed_mast_height_m")
        survey = db.scalar(
            select(m.Survey)
            .where(m.Survey.venue_id == venue_id, m.Survey.status == "complete")
            .order_by(m.Survey.created_at.desc())
            .limit(1)
        )
        if survey is None:
            raise HTTPException(409, "no complete survey to attach the proposed mast to")
        ground_y = body.position.y - body.height_agl_m
        prim = CylinderPrim(
            cx=body.position.x,
            cz=body.position.z,
            r=body.proposed_mast_radius_m,
            y0=ground_y,
            y1=ground_y + body.proposed_mast_height_m,
        )
        s = m.Structure(
            survey_id=survey.id,
            cls="pole",
            name=body.label or "proposed mast",
            confidence=1.0,
            state="accepted",
            primitive=prim.model_dump(mode="json"),
            porosity=0.0,
            mountable=True,
            origin="manual",
            reviewed_by=user.email,
            reviewed_at=datetime.now(UTC),
        )
        db.add(s)
        db.flush()
        structure_id = s.id
        mp_origin = "proposed_structure"
    elif body.landed_on == "none":
        raise HTTPException(422, "a free-floating camera needs a position on a surface first")

    mp = m.MountPoint(
        venue_id=venue_id,
        structure_id=structure_id,
        position=point_to_storage(body.position, origin),
        normal=body.normal.model_dump() if body.normal else None,
        origin=mp_origin,
        mounting_type=(
            body.mounting_type
            or (MountingType.NEW_MAST if mp_origin == "proposed_structure" else None)
        ),
        height_agl_m=body.height_agl_m,
        max_load_kg=body.max_load_kg,
        cable_run_m=body.cable_run_m,
        accuracy_m=(s_acc.accuracy_m if (s_acc := db.get(m.Structure, structure_id)) else None)
        if structure_id
        else None,
        confidence=1.0,
        state="accepted",
        label=body.label,
        created_by=user.email,
    )
    db.add(mp)
    db.commit()
    return to_mount(mp, origin)


@router.patch("/mount-points/{mount_id}", response_model=MountPoint)
def patch_mount(mount_id: uuid.UUID, body: MountPatch, _: Surveyor, db: DB) -> MountPoint:
    mp = db.get(m.MountPoint, mount_id)
    if mp is None:
        raise HTTPException(404, "no such mount point")
    if body.state is not None:
        mp.state = body.state.value
    for field in ("max_load_kg", "cable_run_m", "label"):
        if getattr(body, field) is not None:
            setattr(mp, field, getattr(body, field))
    if body.mounting_type is not None:
        mp.mounting_type = body.mounting_type.value
    db.commit()
    return to_mount(mp, origin_of(get_venue(db, mp.venue_id)))
