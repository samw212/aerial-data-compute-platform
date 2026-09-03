"""Source imagery and capture quality. Build spec 4.2.

CaptureQA.blocking is the gate: POST /surveys/{id}/reconstruct returns 409 while it
is non-empty and unacknowledged (build spec 5, 8.7).
"""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from groma_contracts.geometry import Vec3


class SensorSpec(BaseModel):
    """A physical sensor. Looked up from fixtures/sensors/sensors.yaml by make+model.

    EXIF gives focal length in millimetres but rarely gives sensor dimensions, and
    px/m depends on both. A missing entry here is why a survey cannot be scaled.
    """

    model_config = ConfigDict(frozen=True)

    make: str
    model: str
    sensor_w_mm: float = Field(gt=0)
    sensor_h_mm: float = Field(gt=0)
    res_x: int = Field(gt=0)
    res_y: int = Field(gt=0)


class ImageState(StrEnum):
    ACCEPTED = "accepted"
    REJECTED_BLUR = "rejected_blur"
    REJECTED_EXPOSURE = "rejected_exposure"
    REJECTED_MANUAL = "rejected_manual"


class SourceImage(BaseModel):
    id: str
    survey_id: str
    filename: str
    uri: str
    sha256: str = Field(min_length=64, max_length=64)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    focal_mm: float | None = None
    sensor: SensorSpec | None = None
    captured_at: datetime | None = None
    gps: Vec3 | None = None
    """Storage CRS, from EXIF."""
    gps_accuracy_m: float | None = None
    rtk_fixed: bool = False
    gimbal_pitch_deg: float | None = None
    """-90 = nadir."""
    gimbal_yaw_deg: float | None = None
    sharpness: float | None = None
    """Variance of Laplacian."""
    clipped_fraction: float | None = None
    state: ImageState = ImageState.ACCEPTED
    source: Literal["still", "video_frame"] = "still"
    video_frame_index: int | None = None


class CaptureQA(BaseModel):
    """The QA report for one survey's imagery. Build spec 8.7."""

    model_config = ConfigDict(frozen=True)

    image_count: int
    accepted_count: int
    rejected: dict[str, int] = Field(default_factory=dict)
    sharpness_p10: float
    estimated_gsd_m: float | None = None
    estimated_front_overlap: float | None = Field(default=None, ge=0, le=1)
    estimated_side_overlap: float | None = Field(default=None, ge=0, le=1)
    nadir_count: int = 0
    oblique_count: int = 0
    rtk_fraction: float = Field(default=0.0, ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)
    blocking: list[str] = Field(default_factory=list)
    """Must be acknowledged before reconstruction is permitted."""


__all__ = ["CaptureQA", "ImageState", "SensorSpec", "SourceImage"]
