"""T5: the fast kernel against reference.py. Build spec 6.6.

This is the test that catches a silent broadcasting bug in the vectorised kernel —
the failure that produces a map which is smooth, plausible and wrong, and which no
amount of staring at the output will reveal.

reference.py is plain Python loops with no broad phase and no cleverness, so
agreement between the two is meaningful: they share the convention and the
geometry, and nothing else.
"""

from __future__ import annotations

import numpy as np
import pytest

from groma_contracts.geometry import BoxPrim, CylinderPrim, ExtrudedPolyline
from groma_coverage.kernel import compute_coverage
from groma_coverage.reference import compute_coverage_reference
from groma_coverage.types import Grid, Occluder
from tests.conftest import aimed_camera, assert_sees_something, sloped_terrain


def _scene() -> tuple[list, list]:
    """Three cameras, five occluders: one of every primitive kind, plus porosity.

    Build spec 6.6 specifies a 40x40 grid, 3 cameras, 5 occluders, terrain on.
    """
    cams = [
        aimed_camera((-18.0, 11.0, -14.0), tilt_deg=17.0, id="c0"),
        aimed_camera((17.0, 9.0, -15.0), tilt_deg=12.0, id="c1"),
        aimed_camera((0.0, 13.0, 16.0), tilt_deg=21.0, id="c2"),
    ]
    occluders = [
        Occluder(
            id="hut",
            prim=BoxPrim(cx=3.0, cy=1.8, cz=2.0, hx=3.5, hy=1.8, hz=2.5, yaw=0.4),
        ),
        Occluder(
            id="shed",
            prim=BoxPrim(cx=-7.0, cy=1.2, cz=-6.0, hx=2.0, hy=1.2, hz=4.0, yaw=-0.9),
        ),
        Occluder(id="mast", prim=CylinderPrim(cx=6.0, cz=-8.0, r=0.4, y0=0.0, y1=12.0)),
        Occluder(
            id="fence",
            prim=ExtrudedPolyline(
                points=[(-14.0, 8.0), (-2.0, 8.0), (-2.0, 14.0)],
                y0=0.0,
                y1=2.4,
                thickness=0.12,
            ),
            porosity=0.85,
        ),
        Occluder(
            id="hoarding",
            prim=ExtrudedPolyline(points=[(9.0, 6.0), (9.0, -3.0)], y0=0.0, y1=3.0, thickness=0.2),
            porosity=0.0,
        ),
    ]
    return cams, occluders


def test_t5_fast_kernel_matches_reference_with_terrain() -> None:
    """T5: ppm within 1e-4, count identical, on a 40x40 grid with terrain on."""
    cams, occluders = _scene()
    grid = Grid(x_min=-20.0, x_max=20.0, z_min=-20.0, z_max=20.0, spacing=1.0)
    assert grid.nx == 40 and grid.nz == 40

    terrain = sloped_terrain(-25.0, -25.0, 25.0, 25.0, spacing=1.0, slope=0.04)

    fast = compute_coverage(cams, occluders, grid, terrain, 1.6)
    slow = compute_coverage_reference(cams, occluders, grid, terrain, 1.6)

    assert_sees_something(fast)

    worst = float(np.max(np.abs(fast.ppm.astype(np.float64) - slow.ppm.astype(np.float64))))
    if worst >= 1e-4:
        j, i = np.unravel_index(int(np.argmax(np.abs(fast.ppm - slow.ppm))), fast.ppm.shape)
        pytest.fail(
            f"kernels diverge by {worst:g} px/m; first worst cell is (j={j}, i={i}) at "
            f"x={grid.x_min + i * grid.spacing}, z={grid.z_min + j * grid.spacing}, "
            f"fast={fast.ppm[j, i]}, reference={slow.ppm[j, i]}"
        )

    assert np.array_equal(fast.count, slow.count)
    assert np.array_equal(fast.best_camera, slow.best_camera)
    assert np.allclose(fast.eval_y, slow.eval_y, atol=1e-6)


def test_t5_parity_without_terrain() -> None:
    """The same agreement with terrain off, isolating the primitive tests."""
    cams, occluders = _scene()
    grid = Grid(x_min=-20.0, x_max=20.0, z_min=-20.0, z_max=20.0, spacing=1.0)

    fast = compute_coverage(cams, occluders, grid, None, 1.6)
    slow = compute_coverage_reference(cams, occluders, grid, None, 1.6)

    assert_sees_something(fast)
    assert np.max(np.abs(fast.ppm - slow.ppm)) < 1e-4
    assert np.array_equal(fast.count, slow.count)


def test_t5_parity_without_foreshortening() -> None:
    """Foreshortening is applied identically in both implementations."""
    cams, occluders = _scene()
    grid = Grid(x_min=-20.0, x_max=20.0, z_min=-20.0, z_max=20.0, spacing=2.0)

    fast = compute_coverage(cams, occluders, grid, None, 1.6, foreshorten=False)
    slow = compute_coverage_reference(cams, occluders, grid, None, 1.6, foreshorten=False)

    assert np.max(np.abs(fast.ppm - slow.ppm)) < 1e-4
    assert np.array_equal(fast.count, slow.count)


def test_t5_parity_with_mount_exclusion() -> None:
    """Mount exclusion is honoured the same way in both.

    The fast kernel skips the owner before the broad phase and the reference skips
    it inside the per-cell loop; a mismatch there would show up only here.
    """
    mast = Occluder(
        id="mast",
        prim=CylinderPrim(cx=0.0, cz=0.0, r=0.4, y0=0.0, y1=14.0),
        owner_id="mast",
    )
    cam = aimed_camera(
        (0.0, 12.0, 0.0), look_at=(20.0, 0.0), tilt_deg=15.0, mount_structure_id="mast"
    )
    grid = Grid(x_min=2.0, x_max=30.0, z_min=-14.0, z_max=14.0, spacing=1.0)

    fast = compute_coverage([cam], [mast], grid, None, 1.6)
    slow = compute_coverage_reference([cam], [mast], grid, None, 1.6)

    assert_sees_something(fast)
    assert np.max(np.abs(fast.ppm - slow.ppm)) < 1e-4
    assert np.array_equal(fast.count, slow.count)


def test_coarse_terrain_pass_never_clears_a_blocked_ray() -> None:
    """The coarse-to-fine terrain march is exact, on terrain built to break it.

    Seeded random bumps on a slope, with amplitude and wavelength chosen so that
    plenty of rays fail the coarse bound in one stretch and pass it in another.
    reference.py has no coarse pass at all, so any ray the coarse bound wrongly
    clears shows up here as a count mismatch.
    """
    from groma_coverage.types import Terrain

    rng = np.random.default_rng(7)
    spacing = 0.5
    nx, nz = 121, 101
    xs = np.arange(nx) * spacing - 30.0
    zs = np.arange(nz) * spacing - 25.0
    xg, zg = np.meshgrid(xs, zs)
    heights = (
        0.05 * xg
        + 1.2 * np.sin(xg * 0.9) * np.cos(zg * 0.7)
        + 2.5 * np.exp(-((xg - 2.0) ** 2) / 8.0)  # a 2.5 m ridge across the middle
        + rng.normal(0.0, 0.15, size=xg.shape)
    ).astype(np.float32)
    terrain = Terrain(x_min=-30.0, z_min=-25.0, spacing=spacing, heights=heights)

    cams = [
        aimed_camera((-18.0, 6.0, -14.0), tilt_deg=12.0, id="c0"),
        aimed_camera((17.0, 5.0, 15.0), tilt_deg=9.0, id="c1"),
    ]
    grid = Grid(x_min=-20.0, x_max=20.0, z_min=-20.0, z_max=20.0, spacing=1.0)

    fast = compute_coverage(cams, [], grid, terrain, 1.6)
    slow = compute_coverage_reference(cams, [], grid, terrain, 1.6)
    assert_sees_something(fast)

    # The terrain must actually block a good share of what the cameras would
    # otherwise see, or a coarse pass that cleared everything would pass here.
    # Measured against the reference, which has no coarse pass to be wrong.
    bare = compute_coverage(cams, [], grid, None, 1.6)
    shadowed = (bare.count > 0) & (slow.count == 0)
    assert np.count_nonzero(shadowed) > 0.10 * np.count_nonzero(bare.count > 0)

    assert np.array_equal(fast.count, slow.count)
    assert np.max(np.abs(fast.ppm - slow.ppm)) < 1e-4


def test_broad_phase_never_discards_a_real_hit() -> None:
    """The broad phase is an optimisation, and must change no result.

    Running the fast kernel against the reference — which has no broad phase at
    all — is what makes that claim testable. A bounding radius that is slightly
    too small produces missing shadows in exactly the places nobody looks.
    """
    cams, occluders = _scene()
    # A grid deliberately larger than the occluders, so most cells are rejected
    # by the broad phase and only a few reach the exact test.
    grid = Grid(x_min=-40.0, x_max=40.0, z_min=-40.0, z_max=40.0, spacing=2.0)

    fast = compute_coverage(cams, occluders, grid, None, 1.6)
    slow = compute_coverage_reference(cams, occluders, grid, None, 1.6)

    assert np.array_equal(fast.count, slow.count)
    assert np.max(np.abs(fast.ppm - slow.ppm)) < 1e-4
