"""Site and the origin that defines the Compute frame. Build spec 5.

Every stored height is labelled with its datum. Mixing ellipsoidal, orthometric and
above-ground-level heights in one model puts cameras tens of metres underground,
and the symptom appears nowhere near the cause (CLAUDE.md, known trap 5).
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from groma_contracts.geometry import Primitive


class HeightDatum(StrEnum):
    ORTHOMETRIC_MPD = "orthometric_mpd"
    """Metres above Hong Kong Principal Datum."""
    ELLIPSOIDAL = "ellipsoidal"
    """Metres above the reference ellipsoid, as GNSS reports it."""
    LOCAL = "local"
    """An arbitrary local vertical datum. Not comparable across sites."""


class Site(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    srid: int
    """Projected CRS of the Storage frame, e.g. 2326 for Hong Kong 1980 Grid."""
    origin_x: float
    origin_y: float
    origin_z: float
    """Storage-frame origin that the Compute frame is rebased to, once, on load."""
    height_datum: HeightDatum
    created_at: datetime | None = None


class SiteOrigin(BaseModel):
    """The rebasing parameters on their own, for code that has no Site row."""

    model_config = ConfigDict(frozen=True)

    srid: int
    x: float
    y: float
    z: float
    height_datum: HeightDatum = HeightDatum.LOCAL


class AuthoredStructure(BaseModel):
    """One structure in a hand-authored site fixture (fixtures/sites/*.json).

    This is the input to scripts/synthesise_site.py and the truth that
    tests/integration/test_extraction_recovers_truth.py asserts against
    (build spec 12.5). It is deliberately not `Structure`: an authored primitive
    has no survey, no confidence and no review state, because nobody extracted it.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    cls: str
    """A StructureClass value. Kept as str so this module does not import structure."""
    primitive: Primitive
    porosity: float = Field(default=0.0, ge=0, le=1)
    mountable: bool = False
    seasonal: bool = False


class SiteFixture(BaseModel):
    """A hand-authored site: fixtures/sites/site_alpha.json.

    The extent is the coverage area of interest in local ENU metres, and it is what
    the golden fixture grid is built over. Terrain is flat at y = 0 unless a survey
    supplies a DTM.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    srid: int
    origin: SiteOrigin
    x_min: float
    x_max: float
    z_min: float
    z_max: float
    structures: list[AuthoredStructure]

    @property
    def width_m(self) -> float:
        return self.x_max - self.x_min

    @property
    def depth_m(self) -> float:
        return self.z_max - self.z_min


__all__ = [
    "AuthoredStructure",
    "HeightDatum",
    "Site",
    "SiteFixture",
    "SiteOrigin",
]
