"""Property tests. Build spec 18.

Hypothesis is used here for the invariants that must hold for *every* input, not
for a handful of hand-picked ones: basis orthonormality under arbitrary pan/tilt,
the rebasing round trip, and the monotonicity and foreshortening bounds. A
hand-written case tests the geometry someone thought of; these test the geometry
nobody thought of.
"""

from __future__ import annotations

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from groma_contracts.site import HeightDatum, SiteOrigin
from groma_coverage.kernel import compute_coverage
from groma_coverage.types import Grid, Occluder
from groma_geo.optics import camera_basis, f_px, vfov_rad
from groma_geo.origin import to_local, to_storage
from tests.conftest import aimed_camera

pans = st.floats(min_value=-360.0, max_value=360.0, allow_nan=False)
tilts = st.floats(min_value=-89.9, max_value=89.9, allow_nan=False)


@given(pan_deg=pans, tilt_deg=tilts)
def test_basis_is_always_orthonormal(pan_deg: float, tilt_deg: float) -> None:
    """forward, right, up stay a unit orthogonal triple for any pan and tilt."""
    forward, right, up = camera_basis(pan_deg, tilt_deg)
    for v in (forward, right, up):
        assert abs(float(np.linalg.norm(v)) - 1.0) < 1e-9
    assert abs(float(np.dot(forward, right))) < 1e-9
    assert abs(float(np.dot(forward, up))) < 1e-9
    assert abs(float(np.dot(right, up))) < 1e-9


@given(pan_deg=pans, tilt_deg=tilts)
def test_forward_matches_the_stated_convention(pan_deg: float, tilt_deg: float) -> None:
    """The basis is exactly the formula in CLAUDE.md, for every input.

    forward = ( sin(pan)cos(tilt), -sin(tilt), -cos(pan)cos(tilt) )
    """
    pan = np.radians(pan_deg)
    tilt = np.radians(tilt_deg)
    expected = np.array([np.sin(pan) * np.cos(tilt), -np.sin(tilt), -np.cos(pan) * np.cos(tilt)])
    forward, _, _ = camera_basis(pan_deg, tilt_deg)
    assert np.allclose(forward, expected, atol=1e-9)


coords = st.floats(min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False)


@given(x=coords, y=coords, z=coords)
def test_rebasing_round_trips(x: float, y: float, z: float) -> None:
    """Storage -> Compute -> Storage returns the original, to sub-millimetre.

    Hong Kong Grid coordinates are ~830,000 m, so the round trip is done in
    float64 throughout; losing this property is exactly the float32 failure
    explained 3.3 describes.
    """
    origin = SiteOrigin(
        srid=2326,
        x=833_000.0,
        y=817_000.0,
        z=5.0,
        height_datum=HeightDatum.ORTHOMETRIC_MPD,
    )
    storage = np.array([origin.x + x, origin.y + y, origin.z + z])
    local = to_local(storage, origin)
    back = to_storage(local, origin)
    assert np.allclose(back, storage, atol=1e-6)


@given(x=coords, y=coords, z=coords)
def test_rebasing_keeps_coordinates_small(x: float, y: float, z: float) -> None:
    """The local frame stays near zero, which is the entire point of rebasing."""
    origin = SiteOrigin(srid=2326, x=833_000.0, y=817_000.0, z=5.0)
    local = to_local(np.array([origin.x + x, origin.y + y, origin.z + z]), origin)
    assert float(np.abs(local).max()) <= 500.0 + 1e-6


@given(
    focal_mm=st.floats(min_value=1.0, max_value=200.0),
    sensor_h_mm=st.floats(min_value=1.0, max_value=40.0),
    res_y=st.integers(min_value=64, max_value=8192),
)
def test_f_px_identity_holds_everywhere(focal_mm: float, sensor_h_mm: float, res_y: int) -> None:
    """T1 as a property, over the whole plausible lens and sensor space."""
    direct = f_px(focal_mm, res_y, sensor_h_mm)
    via_fov = res_y / (2.0 * np.tan(vfov_rad(sensor_h_mm, focal_mm) / 2.0))
    assert abs(direct - via_fov) <= 1e-9 * max(1.0, direct)


@settings(max_examples=25, deadline=None)
@given(
    tilt_deg=st.floats(min_value=0.0, max_value=45.0),
    height=st.floats(min_value=4.0, max_value=25.0),
)
def test_foreshortening_bound_holds_for_any_camera(tilt_deg: float, height: float) -> None:
    """T7 as a property: the foreshortened map never exceeds the flat one."""
    cam = aimed_camera((-20.0, height, -20.0), tilt_deg=tilt_deg)
    grid = Grid(x_min=-20.0, x_max=20.0, z_min=-20.0, z_max=20.0, spacing=2.0)

    fore = compute_coverage([cam], [], grid, None, 1.6, foreshorten=True)
    flat = compute_coverage([cam], [], grid, None, 1.6, foreshorten=False)
    assert np.all(fore.ppm <= flat.ppm + 1e-5)


@settings(max_examples=25, deadline=None)
@given(
    cx=st.floats(min_value=-12.0, max_value=12.0),
    cz=st.floats(min_value=-12.0, max_value=12.0),
    radius=st.floats(min_value=0.15, max_value=2.0),
    top=st.floats(min_value=1.0, max_value=15.0),
)
def test_any_occluder_only_ever_removes_coverage(
    cx: float, cz: float, radius: float, top: float
) -> None:
    """T6 as a property: wherever you put an occluder, it cannot help."""
    from groma_contracts.geometry import CylinderPrim

    cam = aimed_camera((-22.0, 12.0, -22.0), tilt_deg=18.0)
    grid = Grid(x_min=-20.0, x_max=20.0, z_min=-20.0, z_max=20.0, spacing=2.0)

    bare = compute_coverage([cam], [], grid, None, 1.6)
    obstructed = compute_coverage(
        [cam],
        [Occluder(id="o", prim=CylinderPrim(cx=cx, cz=cz, r=radius, y0=0.0, y1=top))],
        grid,
        None,
        1.6,
    )
    assert np.all(obstructed.ppm <= bare.ppm + 1e-5)
    assert np.all(obstructed.count <= bare.count)


@settings(max_examples=20, deadline=None)
@given(porosity=st.floats(min_value=0.0, max_value=1.0))
def test_porosity_is_monotone(porosity: float) -> None:
    """More porous is never less visible, and never more visible than no occluder.

    This brackets the attenuation between the solid and absent cases for every
    value in between, which is the property the choice of factor has to satisfy
    whichever way the specification's contradiction is resolved.
    """
    from groma_contracts.geometry import ExtrudedPolyline

    cam = aimed_camera((0.0, 10.0, 0.0), look_at=(40.0, 0.0), tilt_deg=8.0)
    grid = Grid(x_min=20.5, x_max=40.0, z_min=-4.0, z_max=4.0, spacing=1.0)
    fence = ExtrudedPolyline(points=[(20.0, -10.0), (20.0, 10.0)], y0=0.0, y1=3.0, thickness=0.12)

    absent = compute_coverage([cam], [], grid, None, 1.6)
    solid = compute_coverage([cam], [Occluder(id="f", prim=fence, porosity=0.0)], grid, None, 1.6)
    partial = compute_coverage(
        [cam], [Occluder(id="f", prim=fence, porosity=porosity)], grid, None, 1.6
    )

    assert np.all(partial.ppm >= solid.ppm - 1e-5)
    assert np.all(partial.ppm <= absent.ppm + 1e-5)
