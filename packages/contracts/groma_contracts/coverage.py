"""Coverage requests, statistics and deltas. Build spec 4.4, 6.

Every number a report prints comes from a persisted CoverageRun, never recomputed
at render time (build spec 15.2). kernel_version travels with the stats for that
reason: these percentages end up in tender documents.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from groma_contracts.camera import DoriTier


class CoverageRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario_id: str
    eval_height_m: float = 1.6
    """Above the local terrain surface, not above the datum."""
    grid_spacing_m: float = Field(default=0.5, gt=0)
    include_tents: bool = True
    include_seasonal: bool = True
    foreshorten: bool = True
    use_terrain: bool = True
    method: Literal["raycast", "shadowmap"] = "raycast"


class CoverageStats(BaseModel):
    """Aggregates over one coverage grid. Areas in square metres."""

    model_config = ConfigDict(frozen=True)

    kernel_version: str
    cells: int
    cell_area_m2: float
    area_m2: float
    tier_area_m2: dict[DoriTier, float]
    """Cumulative: `recognise` includes everything that also meets `identify`."""
    below_detect_m2: float
    """Seen, but under 25 px/m. Distinct from blind."""
    blind_m2: float
    """No sightline from any camera at all."""
    redundant_2plus_m2: float
    per_camera_unique_m2: dict[str, float]
    """Area only this camera covers. The number that justifies each camera."""
    mean_ppm: float

    def tier_pct(self, tier: DoriTier) -> float:
        """Percentage of site area at or above `tier`."""
        if self.area_m2 <= 0:
            return 0.0
        return 100.0 * self.tier_area_m2[tier] / self.area_m2

    @property
    def blind_pct(self) -> float:
        if self.area_m2 <= 0:
            return 0.0
        return 100.0 * self.blind_m2 / self.area_m2

    @property
    def redundant_2plus_pct(self) -> float:
        if self.area_m2 <= 0:
            return 0.0
        return 100.0 * self.redundant_2plus_m2 / self.area_m2


class CoverageDelta(BaseModel):
    """The difference between two runs, for scenario comparison."""

    model_config = ConfigDict(frozen=True)

    run_a: str
    run_b: str
    kernel_version: str
    tier_area_delta_m2: dict[DoriTier, float]
    blind_delta_m2: float
    newly_blind_m2: float
    """Area covered in A and blind in B. Not the same as the change in blind area:
    coverage can be lost in one place and gained in another."""
    newly_covered_m2: float
    mean_ppm_delta: float


class CoverageRun(BaseModel):
    """A persisted coverage computation."""

    id: str
    scenario_id: str
    eval_height_m: float
    grid_spacing_m: float
    include_tents: bool
    foreshorten: bool
    use_terrain: bool
    method: Literal["raycast", "shadowmap"]
    kernel_version: str
    stats: CoverageStats
    grid_uri: str | None = None
    computed_at: datetime | None = None
    duration_ms: int | None = None


__all__ = [
    "CoverageDelta",
    "CoverageRequest",
    "CoverageRun",
    "CoverageStats",
]
