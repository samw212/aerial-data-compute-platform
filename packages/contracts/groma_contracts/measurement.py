"""Measurements, which always carry uncertainty. Build spec 4, 14.

`uncertainty` is not optional and has no default. A measurement without a tolerance
is a number someone will paste into a site plan, and it will be wrong by an amount
nobody can bound. Never format a value to more precision than its tolerance:
47.82 m +/- 0.03, not 47.8213 m.
"""

import math
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class MeasurementKind(StrEnum):
    DISTANCE = "distance"
    HEIGHT = "height"
    AREA = "area"
    ELEVATION_DIFFERENCE = "elevation_difference"


class SnapMode(StrEnum):
    """The snapping hierarchy of build spec 14.1, best first. Which one was used
    determines sigma_snap, so it is stored, not inferred."""

    PRIMITIVE_FEATURE = "primitive_feature"
    TERRAIN = "terrain"
    LOCAL_PLANE = "local_plane"
    NEAREST_POINT = "nearest_point"


class Measurement(BaseModel):
    id: str
    site_id: str
    survey_id: str
    """Measurements belong to a specific survey forever. Re-flying does not move
    an old measurement; it produces a new one."""
    kind: MeasurementKind
    value: float
    uncertainty: float = Field(ge=0)
    """One standard deviation, in `unit`. Deliberately required."""
    unit: str
    snap_mode: SnapMode
    created_by: str | None = None
    created_at: datetime | None = None


def format_measurement(value: float, uncertainty: float, unit: str = "m") -> str:
    """Render a measurement at the precision its tolerance justifies.

    The decimal count is set by the uncertainty, not by the value: enough places to
    show the uncertainty to one significant figure, and no more. This is the rule
    behind the example in CLAUDE.md, "Data rules".

        >>> format_measurement(47.8213, 0.03)
        '47.82 m +/- 0.03'
        >>> format_measurement(47.8213, 0.004)
        '47.821 m +/- 0.004'
        >>> format_measurement(47.8213, 1.5)
        '48 m +/- 2'

    That last case is not a rounding bug. A length known to within a metre and a
    half does not have a decimal place, and printing one implies precision the
    survey does not have.

    A zero uncertainty means the caller has not propagated one rather than that the
    value is exact, so it caps at millimetres instead of licensing infinite digits.
    """
    decimals = min(max(0, -math.floor(math.log10(uncertainty))), 6) if uncertainty > 0 else 3
    return f"{value:.{decimals}f} {unit} +/- {uncertainty:.{decimals}f}"


__all__ = [
    "Measurement",
    "MeasurementKind",
    "SnapMode",
    "format_measurement",
]
