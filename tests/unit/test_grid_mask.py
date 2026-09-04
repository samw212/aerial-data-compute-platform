"""T15 and T16: the facility mask. Build spec 6.1, 6.3, 6.6.

All percentages are of the masked AOI, never of the bounding rectangle. A facility
polygon is rarely rectangular; "92% Detect" against a bounding box that includes
the car park is a fabricated number.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from groma_contracts.camera import DORI_TIERS_HARDEST_FIRST, DoriTier
from groma_coverage.fixtures import golden_cameras, load_site, site_occluders
from groma_coverage.kernel import compute_coverage
from groma_coverage.stats import blind_polygons, summarise
from groma_coverage.types import Grid, rasterise_polygon


def circle(cx: float, cz: float, r: float, n: int = 180) -> list[tuple[float, float]]:
    return [
        (cx + r * math.cos(2 * math.pi * k / n), cz + r * math.sin(2 * math.pi * k / n))
        for k in range(n)
    ]


def test_rasterise_polygon_area_matches_the_analytic_circle() -> None:
    """A circle of radius 30 m at 0.5 m cells covers pi r^2 within one cell ring."""
    grid = Grid(x_min=-40, x_max=40, z_min=-40, z_max=40, spacing=0.5)
    xs, zs = grid.centres()
    mask = rasterise_polygon(circle(0, 0, 30), xs + 0.25, zs + 0.25)
    area = np.count_nonzero(mask) * grid.cell_area_m2
    expected = math.pi * 30 * 30
    # The boundary ring is 2*pi*r*spacing ~ 94 m2 wide at most; be well within it.
    assert abs(area - expected) < 0.5 * 2 * math.pi * 30 * 0.5


def test_t16_facility_grid_area_of_the_site_alpha_pitch() -> None:
    """Grid.from_facility on the 105 x 68 pitch gives 7,140 m2 within 0.5%."""
    pitch = [(-52.5, -34.0), (52.5, -34.0), (52.5, 34.0), (-52.5, 34.0)]
    grid = Grid.from_facility(pitch, spacing=0.5)
    assert grid.mask is not None
    assert abs(grid.area_m2 - 105 * 68) / (105 * 68) < 0.005
    # Padding: the extent is the polygon plus 2 m, snapped to whole cells.
    assert grid.x_min <= -54.5 and grid.x_max >= 54.5
    assert grid.z_min <= -36.0 and grid.z_max >= 36.0
    assert grid.nx * grid.spacing == pytest.approx(grid.x_max - grid.x_min)


def test_t15_masked_percentages_equal_manual_extraction(site_alpha_path) -> None:
    """Stats over a circular mask equal stats over the same cells picked by hand,
    and no masked-out cell ever appears in blind_m2 or in a blind polygon."""
    site = load_site(site_alpha_path)
    cams = golden_cameras(site)
    occ = site_occluders(site)

    full = Grid(x_min=site.x_min, x_max=site.x_max, z_min=site.z_min, z_max=site.z_max, spacing=1.0)
    xs, zs = full.centres()
    mask = rasterise_polygon(circle(10.0, -5.0, 30.0), xs + 0.5, zs + 0.5)
    masked = Grid(
        x_min=site.x_min,
        x_max=site.x_max,
        z_min=site.z_min,
        z_max=site.z_max,
        spacing=1.0,
        mask=mask,
    )

    unmasked_result = compute_coverage(cams, occ, full, None, 1.6, True)
    masked_result = compute_coverage(cams, occ, masked, None, 1.6, True)

    # The kernel itself is unaffected by the mask: same ppm everywhere.
    np.testing.assert_array_equal(unmasked_result.ppm, masked_result.ppm)

    stats = summarise(masked_result, cams)
    cell = masked.cell_area_m2
    inside = mask
    ppm_in = unmasked_result.ppm[inside]
    count_in = unmasked_result.count[inside]

    assert stats.cells == int(np.count_nonzero(inside))
    assert stats.area_m2 == pytest.approx(np.count_nonzero(inside) * cell)
    for tier in DORI_TIERS_HARDEST_FIRST:
        from groma_contracts.camera import DORI_PX_PER_M

        expected = np.count_nonzero(ppm_in >= DORI_PX_PER_M[tier]) * cell
        assert stats.tier_area_m2[tier] == pytest.approx(expected)
    assert stats.blind_m2 == pytest.approx(np.count_nonzero(count_in == 0) * cell)
    assert stats.redundant_2plus_m2 == pytest.approx(np.count_nonzero(count_in >= 2) * cell)

    # Masked-out cells are not blind: the corners of the site are dark in the
    # unmasked run, and must contribute nothing here.
    unmasked_stats = summarise(unmasked_result, cams)
    assert unmasked_stats.blind_m2 > stats.blind_m2

    for ring in blind_polygons(masked_result, min_area_m2=1.0):
        for x, z in ring:
            # Every ring vertex is a corner shared by up to four cells, of which at
            # least one is an in-scope blind cell. Cell (i, j) is sampled at
            # (x_min + i*s, z_min + j*s) and its corners lie at +/- s/2, so a corner
            # at fractional index k + 0.5 belongs to cells k and k + 1.
            fi = (x - masked.x_min) / masked.spacing
            fj = (z - masked.z_min) / masked.spacing
            i0, j0 = math.floor(fi), math.floor(fj)
            cells = [
                (j, i)
                for j in (j0, j0 + 1)
                for i in (i0, i0 + 1)
                if 0 <= j < masked.nz and 0 <= i < masked.nx
            ]
            assert any(mask[j, i] and unmasked_result.count[j, i] == 0 for j, i in cells), (
                f"ring vertex ({x}, {z}) is not on an in-scope blind cell"
            )


def test_masked_and_unmasked_grids_are_not_equal() -> None:
    a = Grid(x_min=0, x_max=10, z_min=0, z_max=10, spacing=1.0)
    b = Grid(x_min=0, x_max=10, z_min=0, z_max=10, spacing=1.0, mask=np.ones((10, 10), bool))
    c = Grid(x_min=0, x_max=10, z_min=0, z_max=10, spacing=1.0, mask=np.ones((10, 10), bool))
    assert a != b
    assert b == c


def test_mask_shape_is_checked() -> None:
    with pytest.raises(ValueError, match="mask has shape"):
        Grid(x_min=0, x_max=10, z_min=0, z_max=10, spacing=1.0, mask=np.ones((5, 5), bool))


def test_tier_pct_is_of_the_aoi(site_alpha_path) -> None:
    """A tier percentage is area / masked area, not area / rectangle area."""
    site = load_site(site_alpha_path)
    cams = golden_cameras(site)
    pitch = [(-52.5, -34.0), (52.5, -34.0), (52.5, 34.0), (-52.5, 34.0)]
    grid = Grid.from_facility(pitch, spacing=0.5)
    stats = summarise(compute_coverage(cams, site_occluders(site), grid), cams)
    assert stats.tier_pct(DoriTier.DETECT) == pytest.approx(
        100 * stats.tier_area_m2[DoriTier.DETECT] / grid.area_m2
    )
    assert stats.area_m2 < (grid.x_max - grid.x_min) * (grid.z_max - grid.z_min)
