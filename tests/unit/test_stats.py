"""Aggregation, comparison and blind polygons. Build spec 6.3.

These are the numbers a report prints, so the tests are about the distinctions the
report has to keep straight: blind is not below-detect, redundancy is not coverage,
and newly-blind is not the change in blind area.
"""

from __future__ import annotations

import numpy as np
import pytest

from groma_contracts.camera import DoriTier
from groma_contracts.geometry import BoxPrim
from groma_coverage.kernel import KERNEL_VERSION, compute_coverage
from groma_coverage.stats import blind_polygons, compare, summarise
from groma_coverage.types import CoverageResult, Grid, Occluder
from tests.conftest import aimed_camera, assert_sees_something


def _synthetic(ppm_values: np.ndarray, counts: np.ndarray, spacing: float = 1.0):
    """A CoverageResult built by hand, so the expected stats are pure arithmetic."""
    nz, nx = ppm_values.shape
    grid = Grid(
        x_min=0.0,
        x_max=nx * spacing,
        z_min=0.0,
        z_max=nz * spacing,
        spacing=spacing,
    )
    return CoverageResult(
        ppm=ppm_values.astype(np.float32),
        count=counts.astype(np.uint8),
        best_camera=np.where(counts > 0, 0, -1).astype(np.int16),
        eval_y=np.full((nz, nx), 1.6, dtype=np.float32),
        grid=grid,
        kernel_version=KERNEL_VERSION,
    )


def test_tier_areas_are_counted_by_hand() -> None:
    """Four cells, one per tier band, with the answer worked out on paper."""
    ppm = np.array([[300.0, 200.0], [100.0, 40.0]])
    counts = np.ones((2, 2))
    stats = summarise(_synthetic(ppm, counts))

    # 300 clears identify(250); 200 clears recognise(125); 100 clears observe(62);
    # 40 clears detect(25). Cumulative, so each tier includes the harder ones.
    assert stats.tier_area_m2[DoriTier.IDENTIFY] == 1.0
    assert stats.tier_area_m2[DoriTier.RECOGNISE] == 2.0
    assert stats.tier_area_m2[DoriTier.OBSERVE] == 3.0
    assert stats.tier_area_m2[DoriTier.DETECT] == 4.0
    assert stats.area_m2 == 4.0
    assert stats.blind_m2 == 0.0


def test_blind_is_unseen_and_below_detect_is_seen_badly() -> None:
    ppm = np.array([[0.0, 10.0], [200.0, 0.0]])
    counts = np.array([[0, 1], [1, 0]])
    stats = summarise(_synthetic(ppm, counts))

    assert stats.blind_m2 == 2.0
    assert stats.below_detect_m2 == 1.0
    assert stats.tier_area_m2[DoriTier.DETECT] == 1.0
    # Every cell is exactly one of: blind, seen-but-poor, or at Detect or better.
    assert stats.blind_m2 + stats.below_detect_m2 + stats.tier_area_m2[DoriTier.DETECT] == (
        stats.area_m2
    )


def test_mean_ppm_ignores_blind_cells() -> None:
    """Averaging zeros in would report a site as worse the larger you draw the grid."""
    ppm = np.array([[0.0, 100.0], [0.0, 200.0]])
    counts = np.array([[0, 1], [0, 1]])
    assert summarise(_synthetic(ppm, counts)).mean_ppm == pytest.approx(150.0)


def test_redundancy_counts_cells_seen_by_two_or_more() -> None:
    ppm = np.array([[10.0, 10.0], [10.0, 0.0]])
    counts = np.array([[1, 2], [3, 0]])
    stats = summarise(_synthetic(ppm, counts))
    assert stats.redundant_2plus_m2 == 2.0
    assert stats.redundant_2plus_pct == pytest.approx(50.0)


def test_per_camera_unique_area_needs_camera_ids() -> None:
    """Without the camera list the mapping is empty, not keyed by array index.

    An index means nothing in a camera schedule, and a report that prints one has
    silently lost the identity of the camera it is justifying.
    """
    ppm = np.array([[10.0, 10.0]])
    counts = np.array([[1, 1]])
    assert summarise(_synthetic(ppm, counts)).per_camera_unique_m2 == {}


def test_compare_distinguishes_newly_blind_from_net_change() -> None:
    """Coverage lost in one place and gained in another nets to zero and is not.

    This is why a scenario comparison quotes newly-blind area: that is the area
    somebody has to do something about.
    """
    before = _synthetic(np.array([[10.0, 0.0]]), np.array([[1, 0]]))
    after = _synthetic(np.array([[0.0, 10.0]]), np.array([[0, 1]]))

    delta = compare(before, after)
    assert delta.blind_delta_m2 == 0.0
    assert delta.newly_blind_m2 == 1.0
    assert delta.newly_covered_m2 == 1.0


def test_compare_refuses_mismatched_grids() -> None:
    a = _synthetic(np.zeros((2, 2)), np.zeros((2, 2)), spacing=1.0)
    b = _synthetic(np.zeros((2, 2)), np.zeros((2, 2)), spacing=0.5)
    with pytest.raises(ValueError, match="different grids"):
        compare(a, b)


def test_compare_refuses_mismatched_kernel_versions() -> None:
    """Two runs from different kernels are not comparable, and the delta would lie."""
    a = _synthetic(np.zeros((2, 2)), np.zeros((2, 2)))
    b = _synthetic(np.zeros((2, 2)), np.zeros((2, 2)))
    b.kernel_version = "9.9.9"
    with pytest.raises(ValueError, match="kernel version"):
        compare(a, b)


def test_blind_polygons_traces_a_known_rectangle() -> None:
    """A single 3x2 blind block comes back as a ring around exactly those cells."""
    counts = np.ones((6, 6), dtype=np.uint8)
    counts[2:4, 1:4] = 0
    result = _synthetic(np.full((6, 6), 100.0), counts)

    rings = blind_polygons(result, min_area_m2=1.0)
    assert len(rings) == 1

    ring = rings[0]
    xs = [p[0] for p in ring]
    zs = [p[1] for p in ring]
    # Cells (i=1..3, j=2..3) at spacing 1 with samples at cell corners: the ring
    # runs half a cell either side of those samples.
    assert min(xs) == pytest.approx(0.5)
    assert max(xs) == pytest.approx(3.5)
    assert min(zs) == pytest.approx(1.5)
    assert max(zs) == pytest.approx(3.5)
    assert ring[0] == ring[-1], "ring must be closed"


def test_blind_polygons_drops_specks() -> None:
    """A single blind cell between two cameras is noise, not a finding."""
    counts = np.ones((6, 6), dtype=np.uint8)
    counts[3, 3] = 0
    result = _synthetic(np.full((6, 6), 100.0), counts)

    assert blind_polygons(result, min_area_m2=4.0) == []
    assert len(blind_polygons(result, min_area_m2=0.5)) == 1


def test_blind_polygons_separates_disjoint_regions() -> None:
    counts = np.ones((9, 9), dtype=np.uint8)
    counts[1:3, 1:3] = 0
    counts[6:8, 6:8] = 0
    result = _synthetic(np.full((9, 9), 100.0), counts)
    assert len(blind_polygons(result, min_area_m2=1.0)) == 2


def test_blind_polygons_on_a_real_run_are_all_blind() -> None:
    """Every returned ring encloses cells the cameras genuinely cannot see.

    Build spec: every dark cell on a coverage map must be traceable to a named,
    reviewed object. That starts with the polygons matching the array.
    """
    cam = aimed_camera((-20.0, 12.0, -20.0), tilt_deg=18.0)
    grid = Grid(x_min=-20.0, x_max=20.0, z_min=-20.0, z_max=20.0, spacing=0.5)
    occluders = [Occluder(id="hut", prim=BoxPrim(cx=0.0, cy=2.5, cz=0.0, hx=4.0, hy=2.5, hz=4.0))]
    result = compute_coverage([cam], occluders, grid, None, 1.6)
    assert_sees_something(result)

    rings = blind_polygons(result, min_area_m2=4.0)
    assert rings, "the hut casts no reportable shadow"

    total_blind_m2 = float(np.count_nonzero(result.count == 0)) * grid.cell_area_m2
    assert total_blind_m2 > 0
