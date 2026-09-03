"""Geometric primitives. Build spec 4.1.

All coordinates here are local ENU metres with Y up (the Compute frame). Projected
CRS coordinates never reach these types: see CLAUDE.md, "Coordinate frames", and
docs/explained.md 3.3 for why a Hong Kong Grid easting in a float32 costs you 6 cm.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class Vec3(BaseModel):
    """A point or direction in local ENU metres, Y up."""

    model_config = ConfigDict(frozen=True)

    x: float
    y: float
    z: float


class BoxPrim(BaseModel):
    """Buildings, stands, tents, and fence segments once expanded.

    Rotation is yaw about Y only. Sites are built on the ground; a box that needs
    pitch or roll is a modelling mistake somewhere upstream.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["box"] = "box"
    cx: float
    cy: float
    cz: float
    hx: float = Field(gt=0, description="Half-extent along local X before yaw")
    hy: float = Field(gt=0, description="Half-extent along local Y (vertical)")
    hz: float = Field(gt=0, description="Half-extent along local Z before yaw")
    yaw: float = 0.0
    """Radians about Y."""


class CylinderPrim(BaseModel):
    """Light masts, CCTV poles, flagpoles. Vertical axis only."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["cylinder"] = "cylinder"
    cx: float
    cz: float
    r: float = Field(gt=0)
    y0: float
    y1: float


class ExtrudedPolyline(BaseModel):
    """Fence runs: a plan-view polyline given a thickness and a height band."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["polyline"] = "polyline"
    points: list[tuple[float, float]] = Field(min_length=2)
    """Plan view (x, z), local ENU."""
    y0: float
    y1: float
    thickness: float = Field(gt=0)


Primitive = Annotated[
    BoxPrim | CylinderPrim | ExtrudedPolyline,
    Field(discriminator="kind"),
]

__all__ = [
    "BoxPrim",
    "CylinderPrim",
    "ExtrudedPolyline",
    "Primitive",
    "Vec3",
]
