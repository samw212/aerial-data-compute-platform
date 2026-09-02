"""Surveys, ground control, and the accuracy statement. Build spec 4.3.

A survey is immutable once complete. Re-flying a site creates a new survey and sets
superseded_by on the old one; reports reference a specific survey id forever.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from groma_contracts.imagery import CaptureQA


class GeorefMethod(StrEnum):
    RTK = "rtk"
    PPK = "ppk"
    GCP = "gcp"
    SCALE_BAR = "scale_bar"
    NONE = "none"
    """Scale-free. Dimensioning is disabled: the API returns 409, it does not warn."""


class SurveyStatus(StrEnum):
    DRAFT = "draft"
    INGESTING = "ingesting"
    QA_REVIEW = "qa_review"
    QUEUED = "queued"
    RECONSTRUCTING = "reconstructing"
    PROCESSING = "processing"
    EXTRACTING = "extracting"
    COMPLETE = "complete"
    FAILED = "failed"


class GcpObservation(BaseModel):
    """One marking of a ground control point in one image."""

    model_config = ConfigDict(frozen=True)

    gcp_id: str
    image_id: str
    px: float
    py: float


class Gcp(BaseModel):
    """A surveyed ground control point.

    Control points are used to solve the transform; check points are held out, and
    their residuals are the only honest accuracy number (build spec 10.3).
    """

    id: str
    survey_id: str
    label: str
    easting: float
    northing: float
    height: float
    role: Literal["control", "check"] = "control"
    observations: list[GcpObservation] = Field(default_factory=list)


class AccuracyReport(BaseModel):
    """What the model is actually worth. Printed in every deliverable."""

    model_config = ConfigDict(frozen=True)

    reproj_rmse_px: float | None = None
    gcp_rmse_h_m: float | None = None
    """Control points. Always optimistic: these were fitted, not predicted."""
    gcp_rmse_v_m: float | None = None
    check_rmse_h_m: float | None = None
    """The honest number."""
    check_rmse_v_m: float | None = None
    check_point_count: int = 0
    gsd_m: float | None = None
    scale_error_pct: float | None = None
    """From the pitch-marking scale check, build spec 10.4."""
    registered_images: int = 0
    total_images: int = 0


class Survey(BaseModel):
    id: str
    site_id: str
    name: str
    flown_at: date | None = None
    platform: str | None = None
    georef: GeorefMethod = GeorefMethod.NONE
    status: SurveyStatus = SurveyStatus.DRAFT
    engine: str | None = None
    """odm-3.5.4 | colmap-3.11 | fixture | import"""
    capture_qa: CaptureQA | None = None
    accuracy: AccuracyReport | None = None
    immutable: bool = False
    superseded_by: str | None = None
    created_at: datetime | None = None

    @property
    def dimensioning_allowed(self) -> bool:
        """False when the model is correct in shape and arbitrary in size."""
        return self.georef is not GeorefMethod.NONE


class Artefact(BaseModel):
    """A file produced by reconstruction or processing. One per (survey, kind)."""

    model_config = ConfigDict(frozen=True)

    id: str
    survey_id: str
    kind: Literal[
        "pointcloud",
        "dsm",
        "dtm",
        "ortho",
        "mesh",
        "poses",
        "tiles_pc",
        "tiles_mesh",
        "tiles_ortho",
        "terrain_grid",
        "report",
    ]
    uri: str
    bytes: int | None = None
    sha256: str = Field(min_length=64, max_length=64)
    meta: dict[str, object] = Field(default_factory=dict)
    """bounds, srid, resolution, point count."""
    created_at: datetime | None = None


__all__ = [
    "AccuracyReport",
    "Artefact",
    "Gcp",
    "GcpObservation",
    "GeorefMethod",
    "Survey",
    "SurveyStatus",
]
