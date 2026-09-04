"""Scenarios and tents. Build spec 4.4, 5.

A scenario is a camera layout over a specific base survey, plus the temporary
structures in place. Comparing two scenarios is the product question: "what does
erecting twelve event tents do to my coverage?"
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from groma_contracts.camera import CameraSpec


class Tent(BaseModel):
    """A temporary structure. Solid: marquee fabric is not chain-link."""

    model_config = ConfigDict(frozen=True)

    id: str
    scenario_id: str
    name: str
    footprint: list[tuple[float, float]] = Field(min_length=3)
    """Plan-view polygon (x, z) in local ENU metres."""
    height_m: float = Field(gt=0)
    yaw_deg: float = 0.0


class Scenario(BaseModel):
    id: str
    venue_id: str
    facility_id: str | None = None
    """None means the whole venue."""
    base_survey_id: str
    name: str
    include_seasonal: bool = True
    created_by: str | None = None
    cameras: list[CameraSpec] = Field(default_factory=list)
    tents: list[Tent] = Field(default_factory=list)
    created_at: datetime | None = None


__all__ = ["Scenario", "Tent"]
