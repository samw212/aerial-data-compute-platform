"""The kernel performance target. Build spec 6.4.

    173,184 cells (0.25 m over 132 x 82 m) x 6 cameras x 30 occluders + terrain,
    under 800 ms.

Marked `bench` and excluded from the unit suite, which has to stay under five
seconds. Run it with `make kernel-bench`.

The budget is what makes the interactive path viable: a coverage run the operator
waits on while dragging a camera has to come back inside a frame or two, and the
authoritative CPU path is the one whose numbers reach a document.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from groma_contracts.geometry import BoxPrim, CylinderPrim, ExtrudedPolyline
from groma_coverage.fixtures import (
    golden_cameras,
    load_site,
    pan_towards,
    site_grid,
    site_occluders,
)
from groma_coverage.kernel import compute_coverage
from groma_coverage.types import Occluder
from tests.conftest import flat_terrain, make_camera

BUDGET_MS = 800.0
TARGET_CELLS = 173_184
TARGET_CAMERAS = 6
TARGET_OCCLUDERS = 30


def _six_cameras(site) -> list:
    """The four golden corner cameras plus the two midfield masts."""
    cameras = list(golden_cameras(site))
    by_name = {s.name: s for s in site.structures}
    for mast in ("mast_mid_s", "mast_mid_n"):
        prim = by_name[mast].primitive
        pan = pan_towards(prim.cx, prim.cz, 0.0, 0.0)
        cameras.append(
            make_camera(
                (prim.cx, 14.0, prim.cz),
                pan_deg=pan,
                tilt_deg=22.0,
                id=f"cam_{mast}",
                far_m=200.0,
                mount_structure_id=mast,
            )
        )
    return cameras


def _pad_to_thirty(occluders: list[Occluder]) -> list[Occluder]:
    """Top the authored site up to 30 occluders with plausible clutter.

    site_alpha has 14 structures. The target is quoted at 30, so the shortfall is
    made up with the things a real ground has and a proxy model keeps: dugouts,
    equipment stores, a run of hoarding.
    """
    padded = list(occluders)
    index = 0
    while len(padded) < TARGET_OCCLUDERS:
        index += 1
        angle = index * 0.7
        cx = 30.0 * np.cos(angle)
        cz = 20.0 * np.sin(angle)
        if index % 3 == 0:
            prim = CylinderPrim(cx=cx, cz=cz, r=0.25, y0=0.0, y1=6.0)
        elif index % 3 == 1:
            prim = BoxPrim(cx=cx, cy=1.2, cz=cz, hx=2.0, hy=1.2, hz=1.5, yaw=angle)
        else:
            prim = ExtrudedPolyline(
                points=[(cx - 4.0, cz), (cx + 4.0, cz)],
                y0=0.0,
                y1=2.0,
                thickness=0.15,
            )
        padded.append(Occluder(id=f"clutter_{index}", prim=prim, owner_id=f"clutter_{index}"))
    return padded


@pytest.mark.bench
def test_kernel_meets_the_performance_target(site_alpha_path) -> None:
    """173k cells x 6 cameras x 30 occluders + terrain, under 800 ms."""
    site = load_site(site_alpha_path)
    cameras = _six_cameras(site)
    occluders = _pad_to_thirty(site_occluders(site))
    grid = site_grid(site, 0.25)
    terrain = flat_terrain(site.x_min, site.z_min, site.x_max, site.z_max, spacing=0.5)

    assert grid.cells == TARGET_CELLS, f"grid is {grid.cells} cells, target is {TARGET_CELLS}"
    assert len(cameras) == TARGET_CAMERAS
    assert len(occluders) == TARGET_OCCLUDERS

    # One untimed run first: the timed figure should measure the kernel, not the
    # first-touch page faults on a 173k-cell allocation.
    compute_coverage(cameras, occluders, grid, terrain, 1.6)

    best = min(_time_once(cameras, occluders, grid, terrain) for _ in range(3))
    print(f"\n  {grid.cells} cells x {len(cameras)} cameras x {len(occluders)} occluders")
    print(f"  best of 3: {best:.0f} ms (budget {BUDGET_MS:.0f} ms)")

    assert best < BUDGET_MS, (
        f"coverage took {best:.0f} ms against a {BUDGET_MS:.0f} ms budget. Check the "
        "broad phase before optimising anything else: an occluder with an oversized "
        "bounding radius sends every cell to the exact test."
    )


def _time_once(cameras, occluders, grid, terrain) -> float:
    start = time.perf_counter()
    compute_coverage(cameras, occluders, grid, terrain, 1.6)
    return (time.perf_counter() - start) * 1000.0
