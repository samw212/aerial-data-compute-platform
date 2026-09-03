"""Structures and the review state that gates them. Build spec 4.4.

The occlusion model reads structures WHERE state = 'accepted'. Nothing else. Every
dark cell on a coverage map must be traceable to a named, reviewed object.
"""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from groma_contracts.geometry import Primitive, Vec3


class StructureClass(StrEnum):
    POLE = "pole"
    FENCE = "fence"
    BUILDING = "building"
    STAND = "stand"
    GOAL = "goal"
    VEGETATION = "vegetation"
    GROUND = "ground"
    OTHER = "other"


class ReviewState(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SEASONAL = "seasonal"
    """Present in one season, absent in another. Coverage is computed both ways."""


class RejectReason(StrEnum):
    """Rejection is typed and retained. An untyped rejection loses information
    you will want next year."""

    NOISE = "noise"
    TRANSIENT = "transient"
    DUPLICATE = "duplicate"


class Structure(BaseModel):
    id: str
    survey_id: str
    cls: StructureClass
    name: str
    confidence: float = Field(ge=0, le=1)
    state: ReviewState = ReviewState.PENDING
    reject_reason: RejectReason | None = None
    primitive: Primitive
    porosity: float = Field(default=0.0, ge=0, le=1)
    """0 = solid. Chain-link mesh is around 0.85: geometrically solid, optically
    nearly transparent (docs/explained.md 7.8)."""
    mountable: bool = False
    fit_rmse_m: float | None = None
    point_count: int | None = None
    origin: Literal["extracted", "manual", "adjusted"] = "extracted"
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None

    @property
    def occludes(self) -> bool:
        """Only accepted structures occlude. Seasonal ones are toggled per run."""
        return self.state is ReviewState.ACCEPTED


class MountPoint(BaseModel):
    """A place a camera can physically go, on an accepted mountable structure."""

    model_config = ConfigDict(frozen=True)

    id: str
    structure_id: str
    position: Vec3
    max_load_kg: float | None = None
    label: str | None = None


__all__ = [
    "MountPoint",
    "RejectReason",
    "ReviewState",
    "Structure",
    "StructureClass",
]
