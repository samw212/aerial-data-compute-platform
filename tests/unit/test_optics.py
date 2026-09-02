"""Optics identities. Build spec 6.6 T1, and the basis the whole kernel rests on."""

from __future__ import annotations

import math

import numpy as np
import pytest

from groma_geo.optics import (
    camera_basis,
    dori_range_m,
    f_px,
    footprint_m,
    gsd_m,
    hfov_rad,
    vfov_rad,
)
from tests.conftest import FOCAL_MM, RES_Y, SENSOR_H_MM


@pytest.mark.parametrize(
    ("focal_mm", "res_y", "sensor_h_mm"),
    [
        (8.0, 2160, 4.04),
        (2.8, 1080, 5.6),
        (50.0, 4320, 24.0),
        (12.0, 1440, 3.2),
    ],
)
def test_t1_f_px_identity(focal_mm: float, res_y: int, sensor_h_mm: float) -> None:
    """T1: f_px computed two ways agrees to 1e-9.

    Directly from the sensor dimension:      f_px = focal * res_y / sensor_h
    Indirectly through the field of view:    f_px = res_y / (2 tan(vfov/2))

    These are the same quantity by construction, and the test exists because the
    two forms appear in different parts of the system — the kernel uses the first,
    a lens calculator naturally reaches for the second — and a factor-of-two slip
    between them would rescale every pixel density in the product.
    """
    direct = f_px(focal_mm, res_y, sensor_h_mm)
    via_fov = res_y / (2.0 * math.tan(vfov_rad(sensor_h_mm, focal_mm) / 2.0))
    assert abs(direct - via_fov) < 1e-9


def test_fov_matches_footprint() -> None:
    """A nadir footprint is 2h tan(fov/2) — the identity T2 leans on."""
    h = 30.0
    fov = hfov_rad(5.37, 8.0)
    assert footprint_m(h, fov) == pytest.approx(2.0 * h * math.tan(fov / 2.0))


def test_gsd_and_dori_are_consistent() -> None:
    """GSD and DORI range are reciprocal views of the same optics.

    A camera at height h looking straight down resolves 1/gsd pixels per metre, so
    the DORI range at that pixel density must be exactly h.
    """
    h = 40.0
    sensor_w, focal, res_x = 5.37, 8.0, 3840
    ground_per_px = gsd_m(sensor_w, h, focal, res_x)
    px_per_m = 1.0 / ground_per_px
    f_px_x = focal * res_x / sensor_w
    assert dori_range_m(f_px_x, px_per_m) == pytest.approx(h, rel=1e-12)


@pytest.mark.parametrize(
    ("pan_deg", "expected"),
    [
        (0.0, (0.0, 0.0, -1.0)),
        (90.0, (1.0, 0.0, 0.0)),
        (180.0, (0.0, 0.0, 1.0)),
        (-90.0, (-1.0, 0.0, 0.0)),
    ],
)
def test_basis_cardinals(pan_deg: float, expected: tuple[float, float, float]) -> None:
    """pan 0 looks along -Z and increases clockwise viewed from above.

    The kernel-level version of this is T9; this one pins the basis itself, so a
    failure here says the convention is wrong rather than that the coverage map
    landed in the wrong quadrant.
    """
    forward, _, _ = camera_basis(pan_deg, 0.0)
    assert np.allclose(forward, expected, atol=1e-12)


@pytest.mark.parametrize(
    ("tilt_deg", "expected_y"),
    [
        (-60.0, math.sin(math.radians(60.0))),
        (-18.0, math.sin(math.radians(18.0))),
        (0.0, 0.0),
        (18.0, -math.sin(math.radians(18.0))),
        (45.0, -math.sin(math.radians(45.0))),
        (89.0, -math.sin(math.radians(89.0))),
    ],
)
def test_positive_tilt_points_downward(tilt_deg: float, expected_y: float) -> None:
    """Positive tilt is downward: forward.y == -sin(tilt).

    The sign here is the one CLAUDE.md warns about. A camera specified at 18
    degrees of downtilt that looks 18 degrees up produces a coverage map that is
    entirely plausible and entirely wrong.
    """
    forward, _, _ = camera_basis(0.0, tilt_deg)
    assert forward[1] == pytest.approx(expected_y, abs=1e-12)


@pytest.mark.parametrize("pan_deg", [-180.0, -90.0, -33.0, 0.0, 17.0, 90.0, 179.0])
@pytest.mark.parametrize("tilt_deg", [-45.0, 0.0, 18.0, 60.0, 90.0])
def test_basis_is_orthonormal(pan_deg: float, tilt_deg: float) -> None:
    """The three vectors stay a unit orthogonal triple everywhere, nadir included."""
    forward, right, up = camera_basis(pan_deg, tilt_deg)
    for v in (forward, right, up):
        assert np.linalg.norm(v) == pytest.approx(1.0, abs=1e-12)
    assert abs(float(np.dot(forward, right))) < 1e-12
    assert abs(float(np.dot(forward, up))) < 1e-12
    assert abs(float(np.dot(right, up))) < 1e-12


def test_nadir_basis_is_stable() -> None:
    """At tilt 90 the cross product with world up degenerates.

    The limit approaching nadir and the value at nadir must agree, or a camera
    pointed straight down flips its image orientation against one pointed 89.999
    degrees down.
    """
    at_nadir = camera_basis(0.0, 90.0)
    approaching = camera_basis(0.0, 89.9999)
    for a, b in zip(at_nadir, approaching, strict=True):
        assert np.allclose(a, b, atol=1e-4)


def test_f_px_of_the_golden_camera() -> None:
    """The T13 camera resolves 4277.2 px/m at one metre.

    Pinned as a plain arithmetic check: 8.0 * 2160 / 4.04.
    """
    assert f_px(FOCAL_MM, RES_Y, SENSOR_H_MM) == pytest.approx(8.0 * 2160 / 4.04, rel=1e-12)
