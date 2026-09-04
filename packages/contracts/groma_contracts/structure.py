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


class Evidence(BaseModel):
    """One source image that shows a structure, with the bounding box in pixels."""

    model_config = ConfigDict(frozen=True)

    image_id: str
    bbox: tuple[float, float, float, float]
    """x0, y0, x1, y1 in image pixels."""


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
    view_count: int | None = None
    """Source images that saw it, from the poses (build spec 10.10)."""
    mean_incidence_deg: float | None = None
    accuracy_m: float | None = None
    """The build spec 10.6 quadrature sum for a point on this structure."""
    evidence: list[Evidence] = Field(default_factory=list)
    """Best source views, for the review UI."""
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None

    @property
    def insufficient_for_mount_design(self) -> bool:
        """Build spec 10.10: accepted as an occluder, refused as a mount."""
        return (self.view_count is not None and self.view_count < 20) or (
            self.accuracy_m is not None and self.accuracy_m > 0.10
        )

    @property
    def occludes(self) -> bool:
        """Only accepted structures occlude. Seasonal ones are toggled per run."""
        return self.state is ReviewState.ACCEPTED


class MountingType(StrEnum):
    POLE_CLAMP = "pole_clamp"
    WALL_BRACKET = "wall_bracket"
    CORNER_BRACKET = "corner_bracket"
    NEW_MAST = "new_mast"


class MountPoint(BaseModel):
    """A place a camera can physically go. Build spec 12.6, 12.7.

    `structure_id` is None for a proposed new mast; the proposed structure row is
    created alongside so that the mast you are about to install occludes too.
    """

    id: str
    venue_id: str
    structure_id: str | None = None
    position: Vec3
    """Local ENU metres, Y up."""
    normal: Vec3 | None = None
    """Surface normal at the mount face, for bracket direction."""
    origin: Literal["extracted", "manual", "proposed_structure"] = "extracted"
    mounting_type: MountingType | None = None
    height_agl_m: float
    max_load_kg: float | None = None
    cable_run_m: float | None = None
    accuracy_m: float | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)
    state: ReviewState = ReviewState.PENDING
    label: str | None = None
    created_by: str | None = None
    created_at: datetime | None = None


__all__ = [
    "Evidence",
    "MountPoint",
    "MountingType",
    "RejectReason",
    "ReviewState",
    "Structure",
    "StructureClass",
]
