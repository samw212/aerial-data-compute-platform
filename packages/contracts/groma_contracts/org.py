"""Organisations, venues and facilities. Build spec 5, 7.

A venue is the thing that gets flown; a facility is the thing coverage is reported
for. The facility boundary is the coverage area of interest: every percentage in a
report is of that polygon, never of a bounding rectangle (build spec 6.3).

Boundaries are stored in the venue's projected CRS (the Storage frame). Anything
that draws or computes rebases them to the venue origin first; see
groma_geo.origin and CLAUDE.md, "Coordinate frames".
"""

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from groma_contracts.camera import DoriTier
from groma_contracts.site import HeightDatum


class FacilityKind(StrEnum):
    FOOTBALL = "football"
    BASKETBALL = "basketball"
    TENNIS = "tennis"
    NETBALL = "netball"
    HANDBALL = "handball"
    ATHLETICS = "athletics"
    MULTI_USE = "multi_use"
    CAR_PARK = "car_park"
    CIRCULATION = "circulation"
    PERIMETER = "perimeter"
    OTHER = "other"


class Organisation(BaseModel):
    id: str
    name: str
    default_srid: int
    created_at: datetime | None = None


class Venue(BaseModel):
    id: str
    org_id: str
    name: str
    reference: str | None = None
    """The client's own asset reference."""
    address: str | None = None
    srid: int
    origin_x: float
    origin_y: float
    origin_z: float
    """Storage-frame anchor of the Compute frame. Rebased to once, on load."""
    height_datum: HeightDatum
    boundary: list[tuple[float, float]] | None = None
    """Venue extent as (easting, northing) in `srid`."""
    centroid_lon: float | None = None
    centroid_lat: float | None = None
    """WGS84, for the portfolio map only."""
    survey_interval_months: int = 24
    created_at: datetime | None = None


class Facility(BaseModel):
    id: str
    venue_id: str
    name: str
    kind: FacilityKind
    boundary: list[tuple[float, float]] = Field(min_length=3)
    """The coverage AOI as (easting, northing) in the venue's `srid`."""
    nominal_dims: dict[str, float] | None = None
    """{length, width} for the pitch-marking scale check (build spec 10.4)."""
    target_tier: DoriTier = DoriTier.DETECT
    target_pct: float = Field(default=95.0, ge=0, le=100)
    created_at: datetime | None = None


class FacilityHealth(BaseModel):
    """One row of the portfolio table: a facility against its target."""

    model_config = ConfigDict(frozen=True)

    venue_id: str
    venue_name: str
    facility_id: str
    facility_name: str
    kind: FacilityKind
    target_tier: DoriTier
    target_pct: float
    latest_run_id: str | None = None
    latest_pct: float | None = None
    """Percentage of the facility polygon at or above `target_tier` in the latest
    persisted run, or None when nothing has been run."""
    meets_target: bool | None = None
    last_survey_id: str | None = None
    last_survey_flown_at: date | None = None
    stale: bool = False
    """True when the latest complete survey is older than the venue's interval."""


class VenueSummary(BaseModel):
    """A venue with what the portfolio needs to draw it."""

    venue: Venue
    facility_count: int
    survey_count: int
    latest_survey_id: str | None = None
    latest_survey_flown_at: date | None = None
    stale: bool = False
    health: list[FacilityHealth] = Field(default_factory=list)


__all__ = [
    "Facility",
    "FacilityHealth",
    "FacilityKind",
    "Organisation",
    "Venue",
    "VenueSummary",
]
