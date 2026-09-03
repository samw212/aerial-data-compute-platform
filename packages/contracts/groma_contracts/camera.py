"""Camera specification and the pan/tilt convention. Build spec 4.4.

The convention, stated once and never restated differently anywhere in this
repository:

    pan   0 deg points along -Z, increasing clockwise viewed from above
    tilt  positive = downward

    forward = ( sin(pan)*cos(tilt), -sin(tilt), -cos(pan)*cos(tilt) )
    right   = normalise( forward x (0,1,0) )
    up      = right x forward

Almost every geometry bug in this repository will be a violation of it. If a
coverage map appears in the wrong quadrant, check here first. T9
(tests/unit/test_kernel_analytic.py::test_pan_cardinals) exists solely to catch it.

The basis is built in groma_geo.optics.camera_basis, which is the only place the
formula above appears as code. Contracts stay data-only.
"""

from enum import StrEnum
from typing import Final

from pydantic import BaseModel, Field

from groma_contracts.geometry import Vec3


class DoriTier(StrEnum):
    """IEC EN 62676-4 operational requirements, hardest first."""

    IDENTIFY = "identify"
    RECOGNISE = "recognise"
    OBSERVE = "observe"
    DETECT = "detect"


DORI_PX_PER_M: Final[dict[DoriTier, float]] = {
    DoriTier.IDENTIFY: 250.0,
    DoriTier.RECOGNISE: 125.0,
    DoriTier.OBSERVE: 62.0,
    DoriTier.DETECT: 25.0,
}

DORI_TIERS_HARDEST_FIRST: Final[tuple[DoriTier, ...]] = (
    DoriTier.IDENTIFY,
    DoriTier.RECOGNISE,
    DoriTier.OBSERVE,
    DoriTier.DETECT,
)


class CameraSpec(BaseModel):
    """One camera in a scenario.

    `position` is the lens position with the bracket already applied. Storing the
    pole centreline here instead is half of the self-occlusion trap; the other half
    is forgetting mount_structure_id (docs/explained.md 7.7, T8).
    """

    id: str
    name: str
    position: Vec3
    pan_deg: float
    """0 = -Z, increasing clockwise viewed from above."""
    tilt_deg: float
    """Positive = downward."""
    roll_deg: float = 0.0
    sensor_w_mm: float = Field(gt=0)
    sensor_h_mm: float = Field(gt=0)
    focal_mm: float = Field(gt=0)
    res_x: int = Field(gt=0)
    res_y: int = Field(gt=0)
    near_m: float = Field(default=1.0, ge=0)
    far_m: float = Field(default=200.0, gt=0)
    mount_structure_id: str | None = None
    """Excluded from this camera's occluder set."""
    bracket_offset_m: float = 0.0
    """How far the lens sits off the mount structure's centreline. Already applied
    to `position`; retained so the review UI can show and re-derive it."""
    enabled: bool = True


__all__ = [
    "DORI_PX_PER_M",
    "DORI_TIERS_HARDEST_FIRST",
    "CameraSpec",
    "DoriTier",
]
