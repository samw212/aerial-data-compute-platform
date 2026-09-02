"""Coverage kernel analytic cases. Build spec 6.6, T2-T12.

Every expected value here is a closed form, computed from the geometry rather than
from the kernel. That is the whole point: a coverage assertion like "the array has
the right shape and some non-zero values" passes for nearly every bug this
codebase can have.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from groma_contracts.camera import DORI_PX_PER_M, DoriTier
from groma_contracts.geometry import BoxPrim, CylinderPrim, ExtrudedPolyline
from groma_coverage.kernel import compute_coverage
from groma_coverage.stats import summarise
from groma_coverage.types import Grid, Occluder
from groma_geo.optics import f_px, hfov_rad, vfov_rad
from tests.conftest import (
    SENSOR_H_MM,
    SENSOR_W_MM,
    WIDE_FOCAL_MM,
    aimed_camera,
    assert_sees_something,
    flat_terrain,
    make_camera,
    ridge_terrain,
    row_at_z,
    sloped_terrain,
    wall_shadow_end,
)

# --------------------------------------------------------------------------- T2


def test_t2_nadir_footprint_and_peak_density() -> None:
    """T2: a nadir camera's footprint and peak pixel density.

        area     = 2h tan(HFOV/2) * 2h tan(VFOV/2)
        peak ppm = f_px / h

    Foreshortening is off here, and it has to be. Coverage evaluates *vertical*
    targets, so a camera looking straight down at the cell beneath it sees that
    target edge-on and the foreshortened density is zero. That is correct
    behaviour, and it is also why flat-ground footprint coverage overstates a
    system by about a third (CLAUDE.md, "Coverage semantics"). The footprint
    identity being tested is a property of the frustum, so it is measured without
    the foreshortening term.
    """
    h = 30.0
    focal = 8.0

    hfov = hfov_rad(SENSOR_W_MM, focal)
    vfov = vfov_rad(SENSOR_H_MM, focal)
    expected_x = 2.0 * h * math.tan(hfov / 2.0)
    expected_z = 2.0 * h * math.tan(vfov / 2.0)
    expected_area = expected_x * expected_z

    spacing = 0.05
    cam = make_camera((0.0, h, 0.0), pan_deg=0.0, tilt_deg=90.0, focal_mm=focal)
    grid = Grid(x_min=-15.0, x_max=15.0, z_min=-12.0, z_max=12.0, spacing=spacing)

    result = compute_coverage([cam], [], grid, None, eval_height_m=0.0, foreshorten=False)

    lit = result.ppm > 0
    measured_area = float(np.count_nonzero(lit)) * grid.cell_area_m2

    # Discretisation error scales with the perimeter times the cell size.
    perimeter = 2.0 * (expected_x + expected_z)
    tolerance = 1.5 * perimeter * spacing
    assert abs(measured_area - expected_area) < tolerance

    # The footprint is a rectangle of the predicted dimensions, not merely of the
    # predicted area: a frustum with the two axes swapped has the same area.
    xs = grid.x_min + np.arange(grid.nx) * spacing
    zs = grid.z_min + np.arange(grid.nz) * spacing
    lit_x = xs[lit.any(axis=0)]
    lit_z = zs[lit.any(axis=1)]
    assert lit_x.max() - lit_x.min() == pytest.approx(expected_x, abs=3 * spacing)
    assert lit_z.max() - lit_z.min() == pytest.approx(expected_z, abs=3 * spacing)

    expected_peak = f_px(focal, cam.res_y, SENSOR_H_MM) / h
    assert result.ppm.max() == pytest.approx(expected_peak, rel=0.005)


# --------------------------------------------------------------------------- T3


def test_t3_wall_shadow_ends_at_closed_form() -> None:
    """T3: a wall of height w at distance a casts a shadow ending at a(h-e)/(h-w).

    With h = 10, w = 3, a = 20, e = 1.6 that is exactly 24.0 m.
    """
    h, w, a, e = 10.0, 3.0, 20.0, 1.6
    expected = wall_shadow_end(h, w, a, e)
    assert expected == pytest.approx(24.0)

    spacing = 0.25
    cam = make_camera((0.0, h, 0.0), pan_deg=90.0, tilt_deg=0.0, focal_mm=WIDE_FOCAL_MM)
    wall = Occluder(
        id="wall",
        prim=BoxPrim(cx=a, cy=w / 2.0, cz=0.0, hx=0.05, hy=w / 2.0, hz=30.0),
    )
    grid = Grid(x_min=0.0, x_max=40.0, z_min=-0.5, z_max=0.5, spacing=spacing)

    result = compute_coverage([cam], [wall], grid, None, eval_height_m=e)
    xs, ppm = row_at_z(result, 0.0)

    beyond = xs > a
    first_lit = xs[beyond & (ppm > 0)].min()
    last_dark = xs[beyond & (ppm == 0)].max()

    assert abs(first_lit - expected) <= spacing
    assert last_dark < expected + spacing


# --------------------------------------------------------------------------- T4


def _four_camera_scene() -> tuple[list, list]:
    """A small four-camera scene with mixed occluder kinds, for grid invariance."""
    cams = [
        aimed_camera((-25.0, 12.0, -18.0), tilt_deg=16.0, id="c0"),
        aimed_camera((25.0, 12.0, -18.0), tilt_deg=16.0, id="c1"),
        aimed_camera((25.0, 12.0, 18.0), tilt_deg=16.0, id="c2"),
        aimed_camera((-25.0, 12.0, 18.0), tilt_deg=16.0, id="c3"),
    ]
    occluders = [
        Occluder(id="hut", prim=BoxPrim(cx=0.0, cy=2.0, cz=6.0, hx=5.0, hy=2.0, hz=3.0)),
        Occluder(id="mast", prim=CylinderPrim(cx=-8.0, cz=-4.0, r=0.3, y0=0.0, y1=14.0)),
        Occluder(
            id="fence",
            prim=ExtrudedPolyline(
                points=[(-20.0, -12.0), (20.0, -12.0)], y0=0.0, y1=2.4, thickness=0.12
            ),
            porosity=0.85,
        ),
    ]
    return cams, occluders


@pytest.mark.parametrize("tier", list(DoriTier))
def test_t4_grid_invariance(tier: DoriTier) -> None:
    """T4: tier percentages agree across 1.0 / 0.5 / 0.25 m grids within 0.5 pp.

    A result that moves with the sample spacing is measuring the grid, not the
    site. This is the test that catches an off-by-one in the cell centres and a
    kernel that samples cell corners in one path and centres in another.
    """
    percentages = []
    for spacing in (1.0, 0.5, 0.25):
        cams, occluders = _four_camera_scene()
        grid = Grid(x_min=-30.0, x_max=30.0, z_min=-24.0, z_max=24.0, spacing=spacing)
        result = compute_coverage(cams, occluders, grid, None, eval_height_m=1.6)
        percentages.append(summarise(result, cams).tier_pct(tier))

    spread = max(percentages) - min(percentages)
    assert spread < 0.5, f"{tier.value} varies by {spread:.3f} pp across grids: {percentages}"


# --------------------------------------------------------------------------- T6


def test_t6_adding_an_occluder_never_raises_coverage() -> None:
    """T6: occluders never help."""
    cam = aimed_camera((0.0, 12.0, -30.0), tilt_deg=15.0)
    grid = Grid(x_min=-20.0, x_max=20.0, z_min=-20.0, z_max=20.0, spacing=0.5)

    bare = compute_coverage([cam], [], grid, None, 1.6)
    obstructed = compute_coverage(
        [cam],
        [Occluder(id="hut", prim=BoxPrim(cx=0.0, cy=2.0, cz=-10.0, hx=4.0, hy=2.0, hz=2.0))],
        grid,
        None,
        1.6,
    )

    assert_sees_something(bare)
    assert np.all(obstructed.ppm <= bare.ppm + 1e-6)
    assert np.all(obstructed.count <= bare.count)
    assert np.any(obstructed.ppm < bare.ppm), "the occluder changed nothing at all"


def test_t6_adding_a_camera_never_lowers_coverage() -> None:
    """T6: cameras never hurt."""
    a = aimed_camera((-20.0, 12.0, -20.0), tilt_deg=18.0, id="a")
    b = aimed_camera((20.0, 12.0, -20.0), tilt_deg=18.0, id="b")
    grid = Grid(x_min=-25.0, x_max=25.0, z_min=-25.0, z_max=25.0, spacing=0.5)
    occluders = [Occluder(id="hut", prim=BoxPrim(cx=2.0, cy=2.0, cz=0.0, hx=4.0, hy=2.0, hz=3.0))]

    one = compute_coverage([a], occluders, grid, None, 1.6)
    two = compute_coverage([a, b], occluders, grid, None, 1.6)

    assert_sees_something(one)
    assert np.all(two.ppm >= one.ppm - 1e-6)
    assert np.all(two.count >= one.count)
    assert np.any(two.count > one.count), "the second camera added nothing at all"


def test_t6_disabling_a_camera_equals_removing_it() -> None:
    """T6: `enabled = False` is exactly absence — and leaves indices stable.

    best_camera indexes into the camera list as given, so disabling the first of
    two cameras must not renumber the second.
    """
    b = aimed_camera((20.0, 12.0, -20.0), tilt_deg=18.0, id="b")
    grid = Grid(x_min=-25.0, x_max=25.0, z_min=-25.0, z_max=25.0, spacing=0.5)

    disabled = aimed_camera((-20.0, 12.0, -20.0), tilt_deg=18.0, id="a", enabled=False)
    with_disabled = compute_coverage([disabled, b], [], grid, None, 1.6)
    b_only = compute_coverage([b], [], grid, None, 1.6)

    assert np.array_equal(with_disabled.ppm, b_only.ppm)
    assert np.array_equal(with_disabled.count, b_only.count)
    # b is index 1 in the first run and index 0 in the second.
    seen = b_only.count > 0
    assert np.all(with_disabled.best_camera[seen] == 1)
    assert np.all(b_only.best_camera[seen] == 0)


# --------------------------------------------------------------------------- T7


def test_t7_foreshortening_never_raises_density() -> None:
    """T7: ppm(foreshorten) <= ppm(flat) everywhere, with equality iff V.y == 0.

    The factor is sqrt(1 - (V.y/d)^2), which is 1 only when the camera and the
    target are at the same height.
    """
    cam = aimed_camera((0.0, 14.0, -40.0), tilt_deg=12.0)
    grid = Grid(x_min=-30.0, x_max=30.0, z_min=-30.0, z_max=30.0, spacing=0.5)

    fore = compute_coverage([cam], [], grid, None, 1.6, foreshorten=True)
    flat = compute_coverage([cam], [], grid, None, 1.6, foreshorten=False)

    assert_sees_something(flat)
    assert np.all(fore.ppm <= flat.ppm + 1e-6)

    # Every cell here is 12.4 m below the lens, so none is exempt.
    seen = flat.count > 0
    assert np.all(fore.ppm[seen] < flat.ppm[seen])


def test_t7_equality_holds_at_camera_height() -> None:
    """The bound is tight: a target level with the lens is not foreshortened."""
    cam = aimed_camera((0.0, 1.6, -30.0), tilt_deg=0.0)
    grid = Grid(x_min=-10.0, x_max=10.0, z_min=-20.0, z_max=0.0, spacing=0.5)

    fore = compute_coverage([cam], [], grid, None, 1.6, foreshorten=True)
    flat = compute_coverage([cam], [], grid, None, 1.6, foreshorten=False)

    assert_sees_something(flat)
    assert np.allclose(fore.ppm, flat.ppm, rtol=1e-6)


# --------------------------------------------------------------------------- T8


def test_t8_camera_is_not_occluded_by_its_own_mast() -> None:
    """T8: self-occlusion by the mount structure.

    Every pole-mounted camera in every system like this finds its own pole between
    itself and half the site. With `mount_structure_id` set the mast has no effect;
    without it, a large part of the frustum goes dark — and the symptom ("the west
    half is blind for no reason") points nowhere near the cause.
    """
    mast = Occluder(
        id="mast",
        prim=CylinderPrim(cx=0.0, cz=0.0, r=0.35, y0=0.0, y1=16.0),
        owner_id="mast",
    )
    # On the cylinder axis, as build spec 6.6 specifies for this case. That is the
    # unbracketed modelling — position taken straight from the mast centreline —
    # and it is the state in which the bug actually ships: every ray leaves the
    # lens inside the mast and has to cross its wall to get anywhere.
    position = (0.0, 14.0, 0.0)
    grid = Grid(x_min=2.0, x_max=60.0, z_min=-25.0, z_max=25.0, spacing=0.5)

    mounted = make_camera(position, pan_deg=90.0, tilt_deg=14.0, mount_structure_id="mast")
    unmounted = make_camera(position, pan_deg=90.0, tilt_deg=14.0)

    excluded = compute_coverage([mounted], [mast], grid, None, 1.6)
    included = compute_coverage([unmounted], [mast], grid, None, 1.6)
    no_mast = compute_coverage([unmounted], [], grid, None, 1.6)

    # With the exclusion, the mast is exactly as if it were not there.
    assert np.array_equal(excluded.ppm, no_mast.ppm)

    # Without it, the mast blocks a large share of what the camera could see.
    visible = no_mast.count > 0
    lost = int(np.count_nonzero(visible & (included.count == 0)))
    fraction = lost / int(np.count_nonzero(visible))
    assert fraction > 0.40, f"mast only blocked {fraction:.1%} of the frustum"


# --------------------------------------------------------------------------- T9


@pytest.mark.parametrize(
    ("pan_deg", "axis", "sign"),
    [
        (0.0, "z", -1.0),
        (90.0, "x", +1.0),
        (180.0, "z", +1.0),
        (-90.0, "x", -1.0),
    ],
)
def test_pan_cardinals(pan_deg: float, axis: str, sign: float) -> None:
    """T9: pan 0 covers -Z, 90 covers +X, 180 covers +Z, -90 covers -X.

    This test exists solely to catch a pan/tilt sign error, which produces coverage
    in the wrong quadrant and looks superficially fine. It is named in CLAUDE.md
    for that reason. Almost every geometry bug in this repository will be a
    violation of the convention it pins.
    """
    cam = make_camera((0.0, 10.0, 0.0), pan_deg=pan_deg, tilt_deg=20.0)
    grid = Grid(x_min=-40.0, x_max=40.0, z_min=-40.0, z_max=40.0, spacing=0.5)

    result = compute_coverage([cam], [], grid, None, 1.6)
    xs, zs = grid.centres()

    lit = result.ppm > 0
    assert np.any(lit), "camera saw nothing at all"

    coord = xs[lit] if axis == "x" else zs[lit]
    # Every lit cell must be on the expected side of the camera, and the centre of
    # mass must be clearly out along that axis rather than merely non-negative.
    assert np.all(coord * sign > -grid.spacing)
    assert coord.mean() * sign > 5.0

    other = zs[lit] if axis == "x" else xs[lit]
    assert abs(float(other.mean())) < 1.0, "coverage is not centred on the pan axis"


# -------------------------------------------------------------------------- T10


def test_t10_terrain_ridge_casts_the_wall_shadow() -> None:
    """T10: a terrain ridge shadows exactly like the T3 wall.

    Same geometry, different occluder: the ridge is in the heightfield rather than
    in the primitive list, so this checks the DDA march against a closed form
    instead of against the slab test.
    """
    h, w, a, e = 10.0, 3.0, 20.0, 1.6
    expected = wall_shadow_end(h, w, a, e)

    spacing = 0.25
    cam = make_camera((0.0, h, 0.0), pan_deg=90.0, tilt_deg=0.0, focal_mm=WIDE_FOCAL_MM)
    terrain = ridge_terrain(
        x_min=-2.0,
        z_min=-4.0,
        x_max=44.0,
        z_max=4.0,
        spacing=0.25,
        ridge_x=a,
        ridge_height=w,
        half_width=0.25,
    )
    grid = Grid(x_min=0.0, x_max=40.0, z_min=-0.5, z_max=0.5, spacing=spacing)

    result = compute_coverage([cam], [], grid, terrain, eval_height_m=e)
    xs, ppm = row_at_z(result, 0.0)

    beyond = xs > a + 1.0
    first_lit = xs[beyond & (ppm > 0)].min()
    assert abs(first_lit - expected) <= 2 * spacing


# -------------------------------------------------------------------------- T11


def test_t11_eval_height_follows_the_slope() -> None:
    """T11: on a 5% slope, eval_y == terrain + 1.6 everywhere, within 1 mm.

    Evaluating 1.6 m above the datum instead of above the ground is the bug this
    catches, and on a real site it silently moves every target underground at one
    end of the pitch and into the air at the other.
    """
    slope = 0.05
    eval_h = 1.6
    terrain = sloped_terrain(-60.0, -40.0, 60.0, 40.0, spacing=0.5, slope=slope)
    grid = Grid(x_min=-50.0, x_max=50.0, z_min=-30.0, z_max=30.0, spacing=0.5)
    cam = make_camera((0.0, 20.0, -45.0), pan_deg=0.0, tilt_deg=20.0)

    result = compute_coverage([cam], [], grid, terrain, eval_height_m=eval_h)

    xs, _ = grid.centres()
    expected = xs * slope + eval_h
    assert np.max(np.abs(result.eval_y - expected)) < 1e-3


def test_t11_flat_terrain_and_no_terrain_agree() -> None:
    """Terrain at y = 0 must give exactly what `terrain=None` gives."""
    terrain = flat_terrain(-40.0, -30.0, 40.0, 30.0, spacing=0.5, height=0.0)
    grid = Grid(x_min=-30.0, x_max=30.0, z_min=-20.0, z_max=20.0, spacing=0.5)
    cam = make_camera((0.0, 12.0, -25.0), pan_deg=0.0, tilt_deg=15.0)

    with_terrain = compute_coverage([cam], [], grid, terrain, 1.6)
    without = compute_coverage([cam], [], grid, None, 1.6)

    assert np.allclose(with_terrain.eval_y, without.eval_y)
    assert np.allclose(with_terrain.ppm, without.ppm, rtol=1e-6)


# -------------------------------------------------------------------------- T12


def test_t12_porosity_halves_density_without_zeroing_it() -> None:
    """T12: porosity 0.5 halves ppm behind an occluder, and does not zero it.

    A porous occluder attenuates rather than blocks. Modelling chain-link as solid
    puts large false shadows on the map; modelling it as absent overstates
    coverage (explained 7.8).
    """
    cam = make_camera((0.0, 10.0, 0.0), pan_deg=90.0, tilt_deg=0.0, focal_mm=WIDE_FOCAL_MM)
    # The fence is 3 m tall at x = 20, and the camera is at 10 m. By similar
    # triangles its shadow on a 1.6 m target ends at 20*(10-1.6)/(10-3) = 24 m, so
    # the grid has to start inside that shadow to have anything to attenuate.
    grid = Grid(x_min=20.5, x_max=30.0, z_min=-0.5, z_max=0.5, spacing=0.25)
    fence = ExtrudedPolyline(points=[(20.0, -10.0), (20.0, 10.0)], y0=0.0, y1=3.0, thickness=0.12)

    clear = compute_coverage([cam], [], grid, None, 1.6)
    porous = compute_coverage([cam], [Occluder(id="f", prim=fence, porosity=0.5)], grid, None, 1.6)
    solid = compute_coverage([cam], [Occluder(id="f", prim=fence, porosity=0.0)], grid, None, 1.6)

    shadowed = solid.ppm == 0
    assert np.any(shadowed & (clear.ppm > 0)), "the fence casts no shadow to attenuate"

    behind = shadowed & (clear.ppm > 0)
    assert np.all(porous.ppm[behind] > 0), "porosity 0.5 zeroed the cells behind it"
    assert np.allclose(porous.ppm[behind], 0.5 * clear.ppm[behind], rtol=1e-6)

    # And a cell the fence never crossed is untouched.
    unshadowed = (clear.ppm > 0) & ~shadowed
    if np.any(unshadowed):
        assert np.allclose(porous.ppm[unshadowed], clear.ppm[unshadowed], rtol=1e-6)


def test_fully_transparent_occluder_has_no_effect() -> None:
    """porosity 1.0 is 'fully transparent' and must behave as absence.

    This is the case that distinguishes the two readings of the specification's
    porosity field; see groma_coverage.types.Occluder.
    """
    cam = make_camera((0.0, 10.0, 0.0), pan_deg=90.0, tilt_deg=0.0, focal_mm=WIDE_FOCAL_MM)
    # The fence is 3 m tall at x = 20, and the camera is at 10 m. By similar
    # triangles its shadow on a 1.6 m target ends at 20*(10-1.6)/(10-3) = 24 m, so
    # the grid has to start inside that shadow to have anything to attenuate.
    grid = Grid(x_min=20.5, x_max=30.0, z_min=-0.5, z_max=0.5, spacing=0.25)
    fence = ExtrudedPolyline(points=[(20.0, -10.0), (20.0, 10.0)], y0=0.0, y1=3.0, thickness=0.12)

    clear = compute_coverage([cam], [], grid, None, 1.6)
    ghost = compute_coverage([cam], [Occluder(id="f", prim=fence, porosity=1.0)], grid, None, 1.6)
    assert np.array_equal(clear.ppm, ghost.ppm)


# ------------------------------------------------------------------ guardrails


def test_roll_is_refused_rather_than_ignored() -> None:
    """A rolled camera is rejected, because the frustum test cannot honour it.

    Silently ignoring roll would produce a map that is wrong at the frustum edges
    in a way nothing else in the suite would catch.
    """
    cam = make_camera((0.0, 10.0, 0.0), pan_deg=0.0, tilt_deg=20.0).model_copy(
        update={"roll_deg": 15.0}
    )
    grid = Grid(x_min=-10.0, x_max=10.0, z_min=-10.0, z_max=10.0, spacing=1.0)
    with pytest.raises(NotImplementedError, match="roll"):
        compute_coverage([cam], [], grid, None, 1.6)


def test_range_gate_excludes_beyond_far_plane() -> None:
    """The far plane is a hard cut, at the distance it says."""
    far = 30.0
    cam = make_camera((0.0, 1.6, 0.0), pan_deg=90.0, tilt_deg=0.0, far_m=far)
    grid = Grid(x_min=0.0, x_max=60.0, z_min=-0.5, z_max=0.5, spacing=0.25)

    result = compute_coverage([cam], [], grid, None, 1.6)
    xs, ppm = row_at_z(result, 0.0)

    assert np.all(ppm[xs > far + 0.25] == 0)
    assert np.any(ppm[xs < far - 0.25] > 0)


def test_dori_tiers_are_cumulative() -> None:
    """Tier areas nest: identify <= recognise <= observe <= detect."""
    cam = aimed_camera((0.0, 12.0, -30.0), tilt_deg=14.0)
    grid = Grid(x_min=-25.0, x_max=25.0, z_min=-25.0, z_max=25.0, spacing=0.5)
    result = compute_coverage([cam], [], grid, None, 1.6)
    assert_sees_something(result)
    stats = summarise(result, [cam])

    ordered = [
        stats.tier_area_m2[DoriTier.IDENTIFY],
        stats.tier_area_m2[DoriTier.RECOGNISE],
        stats.tier_area_m2[DoriTier.OBSERVE],
        stats.tier_area_m2[DoriTier.DETECT],
    ]
    assert ordered == sorted(ordered)
    assert DORI_PX_PER_M[DoriTier.IDENTIFY] > DORI_PX_PER_M[DoriTier.DETECT]


def test_blind_and_below_detect_are_distinct() -> None:
    """A cell that is seen badly is not blind, and the two must not be conflated.

    Reporting them as one number is how a site with poor but usable coverage gets
    described as having a hole in it.
    """
    # A wide lens, so that the far end of the grid genuinely falls below 25 px/m:
    # f_px is 1497 here, so 25 px/m is reached at 60 m and the far corner is past
    # 100 m. With the 8 mm lens every cell in range would clear Detect and the
    # test would assert nothing.
    cam = aimed_camera((0.0, 12.0, -60.0), tilt_deg=8.0, focal_mm=WIDE_FOCAL_MM)
    grid = Grid(x_min=-40.0, x_max=40.0, z_min=-40.0, z_max=40.0, spacing=0.5)
    result = compute_coverage([cam], [], grid, None, 1.6)
    stats = summarise(result, [cam])

    assert_sees_something(result)
    seen = int(np.count_nonzero(result.count > 0))
    assert stats.blind_m2 == pytest.approx((result.ppm.size - seen) * grid.cell_area_m2)
    assert stats.below_detect_m2 > 0, "expected some seen-but-poor cells at this range"
    assert stats.blind_m2 + stats.tier_area_m2[DoriTier.DETECT] + stats.below_detect_m2 == (
        pytest.approx(stats.area_m2)
    )
