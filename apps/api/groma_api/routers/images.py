"""Source imagery: the gallery, thumbnails and ground footprints. Build spec 8.

Three reads. The list is what the Capture gallery paginates, the thumbnail is what
each tile loads, and the footprints are the GeoJSON the map drapes so an operator can
see where the aircraft actually looked.

Footprints are drawn for nadir frames only. An oblique frame's ground coverage is a
trapezium that runs away from the aircraft and, as the tilt approaches level, off to
the horizon. Drawing that as a rectangle would not be an approximation, it would be
wrong in a way that reads as authoritative on a map.
"""

from __future__ import annotations

import math
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select

from groma_api.db import models as m
from groma_api.deps import DB, Cfg, CurrentUser
from groma_api.routers.surveys import get_survey
from groma_capture.classify import is_nadir
from groma_capture.footprint import footprint_corners

router = APIRouter(prefix="/api", tags=["images"])

EARTH_RADIUS_M = 6_378_137.0


class SourceImageRow(BaseModel):
    """One frame, as the gallery needs it. Deliberately narrower than the contract.

    The gallery renders hundreds of these at once, so the row carries what a tile
    shows and what a tile is sorted by, and nothing else.
    """

    id: str
    filename: str
    width: int
    height: int
    state: str
    captured_at: str | None = None
    sharpness: float | None = None
    clipped_fraction: float | None = None
    gimbal_pitch_deg: float | None = None
    gimbal_yaw_deg: float | None = None
    rtk_fixed: bool = False
    lon: float | None = None
    lat: float | None = None
    altitude_m: float | None = None
    thumb_url: str


class ImagePage(BaseModel):
    total: int
    accepted: int
    items: list[SourceImageRow]


def _pose(row: m.SourceImage) -> dict[str, Any]:
    return row.pose or {}


def to_row(row: m.SourceImage) -> SourceImageRow:
    p = _pose(row)
    return SourceImageRow(
        id=str(row.id),
        filename=row.filename,
        width=row.width,
        height=row.height,
        state=row.state,
        captured_at=row.captured_at.isoformat() if row.captured_at else None,
        sharpness=row.sharpness,
        clipped_fraction=row.clipped_fraction,
        gimbal_pitch_deg=row.gimbal_pitch_deg,
        gimbal_yaw_deg=row.gimbal_yaw_deg,
        rtk_fixed=row.rtk_fixed,
        lon=p.get("lon"),
        lat=p.get("lat"),
        altitude_m=p.get("alt_m"),
        thumb_url=f"/api/surveys/{row.survey_id}/images/{row.id}/thumb",
    )


def _ordered(survey_id: uuid.UUID):  # type: ignore[no-untyped-def]
    """Capture order: by timestamp, then filename so a set with no clock is stable."""
    return (
        select(m.SourceImage)
        .where(m.SourceImage.survey_id == survey_id)
        .order_by(m.SourceImage.captured_at.asc().nulls_last(), m.SourceImage.filename.asc())
    )


@router.get("/surveys/{survey_id}/images", response_model=ImagePage)
def list_images(
    survey_id: uuid.UUID,
    _: CurrentUser,
    db: DB,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    state: str | None = Query(default=None, description="Filter to one image state."),
) -> ImagePage:
    get_survey(db, survey_id)
    total = db.scalar(
        select(func.count()).select_from(m.SourceImage).where(m.SourceImage.survey_id == survey_id)
    )
    accepted = db.scalar(
        select(func.count())
        .select_from(m.SourceImage)
        .where(m.SourceImage.survey_id == survey_id, m.SourceImage.state == "accepted")
    )
    stmt = _ordered(survey_id)
    if state:
        stmt = stmt.where(m.SourceImage.state == state)
    rows = db.scalars(stmt.limit(limit).offset(offset)).all()
    return ImagePage(
        total=int(total or 0), accepted=int(accepted or 0), items=[to_row(r) for r in rows]
    )


@router.get("/surveys/{survey_id}/images/{image_id}/thumb")
def read_thumbnail(
    survey_id: uuid.UUID, image_id: uuid.UUID, _: CurrentUser, db: DB, cfg: Cfg
) -> Response:
    row = db.get(m.SourceImage, image_id)
    if row is None or row.survey_id != survey_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such image")
    path = Path(cfg.artefact_root) / "thumbs" / str(survey_id) / f"{image_id}.jpg"
    if not path.is_file():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "no thumbnail for this image; re-run `groma capture ingest` with thumbnails on",
        )
    return Response(
        content=path.read_bytes(),
        media_type="image/jpeg",
        # Thumbnails are content-addressed by image id and never change in place.
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/surveys/{survey_id}/images/footprints")
def image_footprints(
    survey_id: uuid.UUID, _: CurrentUser, db: DB
) -> dict[str, Any]:
    """Ground footprints and the flight line, as GeoJSON in WGS 84.

    The footprint needs a height above ground. EXIF gives height above the take-off
    point, which is what the aircraft records and what this uses; over sloping ground
    the two differ and the footprint drawn here is correspondingly approximate. It is
    a map overlay for orientation, never an input to coverage.
    """
    get_survey(db, survey_id)
    rows = list(db.scalars(_ordered(survey_id)))
    features: list[dict[str, Any]] = []
    track: list[list[float]] = []

    for row in rows:
        p = _pose(row)
        lon, lat = p.get("lon"), p.get("lat")
        if lon is None or lat is None:
            continue
        track.append([lon, lat])
        agl = p.get("agl_m")
        if (
            agl is None
            or not row.sensor_w_mm
            or not row.sensor_h_mm
            or not row.focal_mm
            or not is_nadir(row.gimbal_pitch_deg)
        ):
            continue
        corners = footprint_corners(
            0.0,
            0.0,
            altitude_agl_m=float(agl),
            yaw_deg=row.gimbal_yaw_deg or 0.0,
            sensor_w_mm=row.sensor_w_mm,
            sensor_h_mm=row.sensor_h_mm,
            focal_mm=row.focal_mm,
        )
        if not corners:
            continue
        m_per_deg_lat = EARTH_RADIUS_M * math.pi / 180.0
        m_per_deg_lon = m_per_deg_lat * math.cos(math.radians(lat))
        ring = [[lon + cx / m_per_deg_lon, lat + cy / m_per_deg_lat] for cx, cy in corners]
        ring.append(ring[0])
        features.append(
            {
                "type": "Feature",
                "id": str(row.id),
                # image_id is duplicated into properties on purpose: a MapLibre
                # filter on ["id"] depends on feature-id promotion, and when that is
                # not configured the filter matches nothing and fails silently.
                "properties": {
                    "image_id": str(row.id),
                    "filename": row.filename,
                    "state": row.state,
                },
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            }
        )

    if len(track) >= 2:
        features.append(
            {
                "type": "Feature",
                "id": "flight-line",
                "properties": {"kind": "flight_line"},
                "geometry": {"type": "LineString", "coordinates": track},
            }
        )
    return {"type": "FeatureCollection", "features": features}


__all__ = ["router"]
