"""Scenarios, cameras and tents. Build spec 7."""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from groma_api.db import models as m
from groma_api.deps import DB, CurrentUser, Surveyor
from groma_api.geom import (
    origin_of,
    point_to_local,
    point_to_storage,
    polygon_to_local,
    polygon_to_storage,
)
from groma_api.routers.portfolio import get_venue
from groma_contracts.camera import CameraSpec
from groma_contracts.geometry import Vec3
from groma_contracts.scenario import Scenario, Tent

router = APIRouter(prefix="/api", tags=["scenarios"])


class ScenarioCreate(BaseModel):
    name: str
    base_survey_id: uuid.UUID
    facility_id: uuid.UUID | None = None
    include_seasonal: bool = True


class ScenarioPatch(BaseModel):
    name: str | None = None
    include_seasonal: bool | None = None


class CameraCreate(BaseModel):
    name: str
    position: Vec3
    pan_deg: float
    tilt_deg: float
    roll_deg: float = 0.0
    sensor_w_mm: float = Field(gt=0)
    sensor_h_mm: float = Field(gt=0)
    focal_mm: float = Field(gt=0)
    res_x: int = Field(gt=0)
    res_y: int = Field(gt=0)
    near_m: float = 1.0
    far_m: float = 200.0
    mount_point_id: uuid.UUID | None = None
    mount_structure_id: uuid.UUID | None = None
    bracket_offset_m: float = 0.0
    model_name: str | None = None
    enabled: bool = True


class CameraPatch(BaseModel):
    name: str | None = None
    position: Vec3 | None = None
    pan_deg: float | None = None
    tilt_deg: float | None = None
    roll_deg: float | None = None
    sensor_w_mm: float | None = None
    sensor_h_mm: float | None = None
    focal_mm: float | None = None
    res_x: int | None = None
    res_y: int | None = None
    near_m: float | None = None
    far_m: float | None = None
    mount_point_id: uuid.UUID | None = None
    mount_structure_id: uuid.UUID | None = None
    bracket_offset_m: float | None = None
    model_name: str | None = None
    enabled: bool | None = None


class TentCreate(BaseModel):
    name: str
    footprint: list[tuple[float, float]] = Field(min_length=3)
    """Plan-view (x, z), local ENU metres."""
    height_m: float = Field(gt=0)
    yaw_deg: float = 0.0


class TentPatch(BaseModel):
    name: str | None = None
    footprint: list[tuple[float, float]] | None = Field(default=None, min_length=3)
    height_m: float | None = None
    yaw_deg: float | None = None


def to_camera(c: m.Camera, origin) -> CameraSpec:  # type: ignore[no-untyped-def]
    return CameraSpec(
        id=str(c.id),
        name=c.name,
        position=point_to_local(c.position, origin),
        pan_deg=c.pan_deg,
        tilt_deg=c.tilt_deg,
        roll_deg=c.roll_deg,
        sensor_w_mm=c.sensor_w_mm,
        sensor_h_mm=c.sensor_h_mm,
        focal_mm=c.focal_mm,
        res_x=c.res_x,
        res_y=c.res_y,
        near_m=c.near_m,
        far_m=c.far_m,
        mount_structure_id=str(c.mount_structure_id) if c.mount_structure_id else None,
        bracket_offset_m=c.bracket_offset_m,
        enabled=c.enabled,
    )


def to_tent(t: m.Tent, origin) -> Tent:  # type: ignore[no-untyped-def]
    return Tent(
        id=str(t.id),
        scenario_id=str(t.scenario_id),
        name=t.name,
        footprint=polygon_to_local(t.footprint, origin),
        height_m=t.height_m,
        yaw_deg=t.yaw_deg,
    )


def to_scenario(db: Session, s: m.Scenario) -> Scenario:
    origin = origin_of(get_venue(db, s.venue_id))
    return Scenario(
        id=str(s.id),
        venue_id=str(s.venue_id),
        facility_id=str(s.facility_id) if s.facility_id else None,
        base_survey_id=str(s.base_survey_id),
        name=s.name,
        include_seasonal=s.include_seasonal,
        cameras=[to_camera(c, origin) for c in sorted(s.cameras, key=lambda c: c.name)],
        tents=[to_tent(t, origin) for t in sorted(s.tents, key=lambda t: t.name)],
        created_by=s.created_by,
        created_at=s.created_at,
    )


def get_scenario(db: Session, scenario_id: uuid.UUID) -> m.Scenario:
    s = db.get(m.Scenario, scenario_id)
    if s is None:
        raise HTTPException(404, "no such scenario")
    return s


@router.get("/venues/{venue_id}/scenarios", response_model=list[Scenario])
def list_scenarios(venue_id: uuid.UUID, _: CurrentUser, db: DB) -> list[Scenario]:
    get_venue(db, venue_id)
    rows = db.scalars(
        select(m.Scenario).where(m.Scenario.venue_id == venue_id).order_by(m.Scenario.created_at)
    )
    return [to_scenario(db, s) for s in rows]


@router.post("/venues/{venue_id}/scenarios", response_model=Scenario, status_code=201)
def create_scenario(venue_id: uuid.UUID, body: ScenarioCreate, user: Surveyor, db: DB) -> Scenario:
    get_venue(db, venue_id)
    survey = db.get(m.Survey, body.base_survey_id)
    if survey is None or survey.venue_id != venue_id:
        raise HTTPException(422, "base_survey_id is not a survey of this venue")
    s = m.Scenario(
        venue_id=venue_id,
        facility_id=body.facility_id,
        base_survey_id=body.base_survey_id,
        name=body.name,
        include_seasonal=body.include_seasonal,
        created_by=user.email,
    )
    db.add(s)
    db.commit()
    return to_scenario(db, s)


@router.get("/scenarios/{scenario_id}", response_model=Scenario)
def read_scenario(scenario_id: uuid.UUID, _: CurrentUser, db: DB) -> Scenario:
    return to_scenario(db, get_scenario(db, scenario_id))


@router.patch("/scenarios/{scenario_id}", response_model=Scenario)
def patch_scenario(scenario_id: uuid.UUID, body: ScenarioPatch, _: Surveyor, db: DB) -> Scenario:
    s = get_scenario(db, scenario_id)
    if body.name is not None:
        s.name = body.name
    if body.include_seasonal is not None:
        s.include_seasonal = body.include_seasonal
    db.commit()
    return to_scenario(db, s)


@router.delete("/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: uuid.UUID, _: Surveyor, db: DB) -> None:
    db.delete(get_scenario(db, scenario_id))
    db.commit()


@router.post("/scenarios/{scenario_id}/clone", response_model=Scenario, status_code=201)
def clone_scenario(
    scenario_id: uuid.UUID, user: Surveyor, db: DB, name: str | None = None
) -> Scenario:
    src = get_scenario(db, scenario_id)
    dst = m.Scenario(
        venue_id=src.venue_id,
        facility_id=src.facility_id,
        base_survey_id=src.base_survey_id,
        name=name or f"{src.name} (copy)",
        include_seasonal=src.include_seasonal,
        created_by=user.email,
    )
    db.add(dst)
    db.flush()
    for c in src.cameras:
        db.add(
            m.Camera(
                scenario_id=dst.id,
                mount_point_id=c.mount_point_id,
                mount_structure_id=c.mount_structure_id,
                name=c.name,
                position=c.position,
                pan_deg=c.pan_deg,
                tilt_deg=c.tilt_deg,
                roll_deg=c.roll_deg,
                bracket_offset_m=c.bracket_offset_m,
                sensor_w_mm=c.sensor_w_mm,
                sensor_h_mm=c.sensor_h_mm,
                focal_mm=c.focal_mm,
                res_x=c.res_x,
                res_y=c.res_y,
                near_m=c.near_m,
                far_m=c.far_m,
                model_name=c.model_name,
                enabled=c.enabled,
            )
        )
    for t in src.tents:
        db.add(
            m.Tent(
                scenario_id=dst.id,
                name=t.name,
                footprint=t.footprint,
                height_m=t.height_m,
                yaw_deg=t.yaw_deg,
            )
        )
    db.commit()
    db.refresh(dst)
    return to_scenario(db, dst)


@router.post("/scenarios/{scenario_id}/cameras", response_model=CameraSpec, status_code=201)
def create_camera(scenario_id: uuid.UUID, body: CameraCreate, _: Surveyor, db: DB) -> CameraSpec:
    s = get_scenario(db, scenario_id)
    origin = origin_of(get_venue(db, s.venue_id))
    mount_structure_id = body.mount_structure_id
    if body.mount_point_id is not None and mount_structure_id is None:
        mp = db.get(m.MountPoint, body.mount_point_id)
        if mp is not None:
            mount_structure_id = mp.structure_id  # self-occlusion exclusion (T8)
    c = m.Camera(
        scenario_id=scenario_id,
        mount_point_id=body.mount_point_id,
        mount_structure_id=mount_structure_id,
        name=body.name,
        position=point_to_storage(body.position, origin),
        pan_deg=body.pan_deg,
        tilt_deg=body.tilt_deg,
        roll_deg=body.roll_deg,
        bracket_offset_m=body.bracket_offset_m,
        sensor_w_mm=body.sensor_w_mm,
        sensor_h_mm=body.sensor_h_mm,
        focal_mm=body.focal_mm,
        res_x=body.res_x,
        res_y=body.res_y,
        near_m=body.near_m,
        far_m=body.far_m,
        model_name=body.model_name,
        enabled=body.enabled,
    )
    db.add(c)
    db.commit()
    return to_camera(c, origin)


@router.patch("/cameras/{camera_id}", response_model=CameraSpec)
def patch_camera(camera_id: uuid.UUID, body: CameraPatch, _: Surveyor, db: DB) -> CameraSpec:
    c = db.get(m.Camera, camera_id)
    if c is None:
        raise HTTPException(404, "no such camera")
    origin = origin_of(get_venue(db, get_scenario(db, c.scenario_id).venue_id))
    data = body.model_dump(exclude_unset=True)
    if "position" in data and body.position is not None:
        c.position = point_to_storage(body.position, origin)
        del data["position"]
    for k, v in data.items():
        setattr(c, k, v)
    db.commit()
    return to_camera(c, origin)


@router.delete("/cameras/{camera_id}", status_code=204)
def delete_camera(camera_id: uuid.UUID, _: Surveyor, db: DB) -> None:
    c = db.get(m.Camera, camera_id)
    if c is None:
        raise HTTPException(404, "no such camera")
    db.delete(c)
    db.commit()


@router.post("/scenarios/{scenario_id}/tents", response_model=Tent, status_code=201)
def create_tent(scenario_id: uuid.UUID, body: TentCreate, _: Surveyor, db: DB) -> Tent:
    s = get_scenario(db, scenario_id)
    origin = origin_of(get_venue(db, s.venue_id))
    t = m.Tent(
        scenario_id=scenario_id,
        name=body.name,
        footprint=polygon_to_storage(body.footprint, origin),
        height_m=body.height_m,
        yaw_deg=body.yaw_deg,
    )
    db.add(t)
    db.commit()
    return to_tent(t, origin)


@router.patch("/tents/{tent_id}", response_model=Tent)
def patch_tent(tent_id: uuid.UUID, body: TentPatch, _: Surveyor, db: DB) -> Tent:
    t = db.get(m.Tent, tent_id)
    if t is None:
        raise HTTPException(404, "no such tent")
    origin = origin_of(get_venue(db, get_scenario(db, t.scenario_id).venue_id))
    if body.name is not None:
        t.name = body.name
    if body.footprint is not None:
        t.footprint = polygon_to_storage(body.footprint, origin)
    if body.height_m is not None:
        t.height_m = body.height_m
    if body.yaw_deg is not None:
        t.yaw_deg = body.yaw_deg
    db.commit()
    return to_tent(t, origin)


@router.delete("/tents/{tent_id}", status_code=204)
def delete_tent(tent_id: uuid.UUID, _: Surveyor, db: DB) -> None:
    t = db.get(m.Tent, tent_id)
    if t is None:
        raise HTTPException(404, "no such tent")
    db.delete(t)
    db.commit()


def tent_grid_footprints(
    rows: int = 3,
    cols: int = 4,
    size_m: float = 8.0,
    spacing_x_m: float = 20.0,
    spacing_z_m: float = 14.0,
    centre: tuple[float, float] = (0.0, 0.0),
) -> list[tuple[str, list[tuple[float, float]]]]:
    """The build spec 6.6 tent preset, as plan-view squares."""
    half = size_m / 2
    out = []
    for r in range(rows):
        for c in range(cols):
            cx = centre[0] + (c - (cols - 1) / 2) * spacing_x_m
            cz = centre[1] + (r - (rows - 1) / 2) * spacing_z_m
            out.append(
                (
                    f"tent_r{r}c{c}",
                    [
                        (cx - half, cz - half),
                        (cx + half, cz - half),
                        (cx + half, cz + half),
                        (cx - half, cz + half),
                    ],
                )
            )
    return out


@router.post("/scenarios/{scenario_id}/tents:preset", response_model=list[Tent], status_code=201)
def tent_preset(
    scenario_id: uuid.UUID,
    _: Surveyor,
    db: DB,
    rows: int = 3,
    cols: int = 4,
    size_m: float = 8.0,
    height_m: float = 3.2,
    spacing_x_m: float = 20.0,
    spacing_z_m: float = 14.0,
    centre_x: float = 0.0,
    centre_z: float = 0.0,
) -> list[Tent]:
    s = get_scenario(db, scenario_id)
    origin = origin_of(get_venue(db, s.venue_id))
    out = []
    for name, ring in tent_grid_footprints(
        rows, cols, size_m, spacing_x_m, spacing_z_m, (centre_x, centre_z)
    ):
        t = m.Tent(
            scenario_id=scenario_id,
            name=name,
            footprint=polygon_to_storage(ring, origin),
            height_m=height_m,
        )
        db.add(t)
        out.append(t)
    db.commit()
    return [to_tent(t, origin) for t in out]


__all__ = ["get_scenario", "router", "tent_grid_footprints", "to_camera", "to_scenario", "to_tent"]
_ = (math, datetime, UTC)
