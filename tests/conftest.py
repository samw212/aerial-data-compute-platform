"""Shared test helpers.

Nothing here computes an expected value. Every expectation in this suite comes
from arithmetic, from reference.py, or from a committed golden file — a coverage
assertion of "right shape, some non-zero values" passes for nearly every bug this
system can have (build spec 18).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from groma_contracts.camera import CameraSpec
from groma_contracts.geometry import Vec3
from groma_coverage.fixtures import pan_towards
from groma_coverage.types import Terrain

REPO_ROOT = Path(__file__).resolve().parent.parent

# A 1/2.8" sensor with an 8 mm lens at 4K: the T13 golden camera.
SENSOR_W_MM = 5.37
SENSOR_H_MM = 4.04
FOCAL_MM = 8.0
RES_X = 3840
RES_Y = 2160

# A deliberately wide lens for the analytic cases. T3 and T10 put a camera at 10 m
# looking horizontally and ask where its shadow ends 24 m away; with the 8 mm lens
# above, the ground closer than 33 m falls below the frustum, so the edge measured
# would be the lens rather than the wall.
WIDE_FOCAL_MM = 2.8


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def site_alpha_path() -> Path:
    return REPO_ROOT / "fixtures" / "sites" / "site_alpha.json"


def make_camera(
    position: tuple[float, float, float],
    pan_deg: float = 0.0,
    tilt_deg: float = 0.0,
    *,
    id: str = "cam",
    focal_mm: float = FOCAL_MM,
    near_m: float = 0.5,
    far_m: float = 500.0,
    mount_structure_id: str | None = None,
    enabled: bool = True,
) -> CameraSpec:
    x, y, z = position
    return CameraSpec(
        id=id,
        name=id,
        position=Vec3(x=x, y=y, z=z),
        pan_deg=pan_deg,
        tilt_deg=tilt_deg,
        sensor_w_mm=SENSOR_W_MM,
        sensor_h_mm=SENSOR_H_MM,
        focal_mm=focal_mm,
        res_x=RES_X,
        res_y=RES_Y,
        near_m=near_m,
        far_m=far_m,
        mount_structure_id=mount_structure_id,
        enabled=enabled,
    )


def aimed_camera(
    position: tuple[float, float, float],
    look_at: tuple[float, float] = (0.0, 0.0),
    tilt_deg: float = 18.0,
    **kwargs: object,
) -> CameraSpec:
    """A camera at `position` panned towards a plan-view point.

    Hand-written pan values are how a test ends up aimed into empty space, where
    every array is zero and every monotonicity assertion passes without testing
    anything. Deriving the pan from the geometry removes that whole class of dud.
    """
    pan = pan_towards(position[0], position[2], look_at[0], look_at[1])
    return make_camera(position, pan_deg=pan, tilt_deg=tilt_deg, **kwargs)  # type: ignore[arg-type]


def assert_sees_something(result, minimum_fraction: float = 0.05) -> None:
    """Guard against a test that passes because the camera saw nothing.

    Build spec 18: "The dangerous tests here are the ones that pass by testing
    nothing." Monotonicity and bound assertions are all trivially true over an
    all-zero array, so the scenes they run on have to be shown to be live.
    """
    seen = float(np.count_nonzero(result.count > 0)) / result.count.size
    assert seen >= minimum_fraction, (
        f"only {seen:.1%} of cells are covered; this scene is too empty to test "
        "anything (is the camera aimed at the grid?)"
    )


def flat_terrain(
    x_min: float,
    z_min: float,
    x_max: float,
    z_max: float,
    spacing: float,
    height: float = 0.0,
) -> Terrain:
    nx = round((x_max - x_min) / spacing) + 1
    nz = round((z_max - z_min) / spacing) + 1
    return Terrain(
        x_min=x_min,
        z_min=z_min,
        spacing=spacing,
        heights=np.full((nz, nx), height, dtype=np.float32),
    )


def sloped_terrain(
    x_min: float,
    z_min: float,
    x_max: float,
    z_max: float,
    spacing: float,
    slope: float,
) -> Terrain:
    """Ground rising by `slope` metres per metre of +X."""
    nx = round((x_max - x_min) / spacing) + 1
    nz = round((z_max - z_min) / spacing) + 1
    xs = x_min + np.arange(nx, dtype=np.float32) * spacing
    heights = np.tile(xs * slope, (nz, 1)).astype(np.float32)
    return Terrain(x_min=x_min, z_min=z_min, spacing=spacing, heights=heights)


def ridge_terrain(
    x_min: float,
    z_min: float,
    x_max: float,
    z_max: float,
    spacing: float,
    ridge_x: float,
    ridge_height: float,
    half_width: float,
) -> Terrain:
    """Flat ground with a flat-topped ridge centred on `ridge_x`.

    Flat-topped rather than triangular so that the shadow it casts has the same
    closed form as the T3 wall: the occluding edge is a single known height at a
    single known distance.
    """
    nx = round((x_max - x_min) / spacing) + 1
    nz = round((z_max - z_min) / spacing) + 1
    xs = x_min + np.arange(nx) * spacing
    profile = np.where(np.abs(xs - ridge_x) <= half_width, ridge_height, 0.0)
    heights = np.tile(profile, (nz, 1)).astype(np.float32)
    return Terrain(x_min=x_min, z_min=z_min, spacing=spacing, heights=heights)


def wall_shadow_end(camera_h: float, wall_h: float, wall_x: float, eval_h: float) -> float:
    """Where the shadow of a wall ends, on flat ground.

    Similar triangles from the camera over the wall top:

        x = a * (h - e) / (h - w)

    With h = 10, w = 3, a = 20, e = 1.6 this is exactly 24.0 m (T3).
    """
    return wall_x * (camera_h - eval_h) / (camera_h - wall_h)


def row_at_z(result, z: float) -> tuple[np.ndarray, np.ndarray]:
    """The (xs, ppm) profile along the grid row nearest `z`."""
    grid = result.grid
    j = round((z - grid.z_min) / grid.spacing)
    j = max(0, min(j, grid.nz - 1))
    xs = grid.x_min + np.arange(grid.nx) * grid.spacing
    return xs, result.ppm[j]


def half_fov_deg(sensor_mm: float, focal_mm: float) -> float:
    return math.degrees(math.atan(sensor_mm / (2.0 * focal_mm)))
