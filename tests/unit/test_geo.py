"""Coordinate frames and height datums. Build spec 3; explained 3.3.

Two failures this guards against, both of which look like nothing until they cost
a day: projected coordinates reaching a float32, and heights from different datums
being subtracted from one another.
"""

from __future__ import annotations

import numpy as np
import pytest

from groma_contracts.site import HeightDatum, SiteOrigin
from groma_geo.heights import LabelledHeight, to_orthometric
from groma_geo.origin import assert_local, to_local, to_storage

HK = SiteOrigin(
    srid=2326,
    x=833_000.0,
    y=817_000.0,
    z=5.0,
    height_datum=HeightDatum.ORTHOMETRIC_MPD,
)


def test_axis_mapping_is_east_up_south() -> None:
    """x is east, y is up, z is south — so -Z is north, which is what pan 0 means."""
    east = to_local([HK.x + 10.0, HK.y, HK.z], HK)
    assert np.allclose(east, [10.0, 0.0, 0.0])

    north = to_local([HK.x, HK.y + 10.0, HK.z], HK)
    assert np.allclose(north, [0.0, 0.0, -10.0])

    up = to_local([HK.x, HK.y, HK.z + 10.0], HK)
    assert np.allclose(up, [0.0, 10.0, 0.0])


def test_round_trip_is_exact_enough_for_survey_work() -> None:
    storage = np.array([HK.x + 47.821, HK.y - 133.4, HK.z + 12.75])
    assert np.allclose(to_storage(to_local(storage, HK), HK), storage, atol=1e-9)


def test_rebasing_handles_arrays() -> None:
    """Shape (..., 3) throughout: the loader rebases a whole point cloud at once."""
    pts = np.array(
        [
            [HK.x, HK.y, HK.z],
            [HK.x + 1.0, HK.y + 2.0, HK.z + 3.0],
            [HK.x - 4.0, HK.y - 5.0, HK.z - 6.0],
        ]
    )
    local = to_local(pts, HK)
    assert local.shape == (3, 3)
    assert np.allclose(local[0], [0.0, 0.0, 0.0])
    assert np.allclose(to_storage(local, HK), pts, atol=1e-9)


def test_rebasing_rejects_a_wrong_trailing_axis() -> None:
    with pytest.raises(ValueError, match="trailing axis"):
        to_local(np.zeros((4, 2)), HK)


def test_float32_would_lose_centimetres_at_hong_kong_grid_eastings() -> None:
    """The measurement that justifies this whole module.

    Consecutive float32 values near 833,000 are ~6 cm apart, so a model accurate
    to 2 cm loses a third of its precision the moment it reaches a float32 array.
    After rebasing, the same array resolves far below a millimetre.
    """
    projected = np.float32(833_000.0)
    gap = float(np.nextafter(projected, np.float32(1e9)) - projected)
    assert gap > 0.03, f"expected centimetre-scale float32 spacing, got {gap}"

    local = np.float32(500.0)
    local_gap = float(np.nextafter(local, np.float32(1e9)) - local)
    assert local_gap < 1e-4


def test_assert_local_catches_unrebased_coordinates() -> None:
    """The guard at the boundary of anything that downcasts."""
    assert_local(np.array([120.0, 14.0, -80.0]))
    with pytest.raises(ValueError, match="never rebased"):
        assert_local(np.array([833_000.0, 14.0, 817_000.0]))


def test_heights_of_different_datums_cannot_be_subtracted() -> None:
    """Mixing datums puts cameras tens of metres underground."""
    ortho = LabelledHeight(12.0, HeightDatum.ORTHOMETRIC_MPD)
    ellip = LabelledHeight(12.0, HeightDatum.ELLIPSOIDAL)

    assert ortho.difference_to(LabelledHeight(4.0, HeightDatum.ORTHOMETRIC_MPD)) == 8.0
    with pytest.raises(ValueError, match="common datum"):
        ortho.difference_to(ellip)


def test_ellipsoidal_conversion_demands_a_geoid_separation() -> None:
    """No default separation, because a plausible guess is exactly the trap."""
    ellip = LabelledHeight(12.0, HeightDatum.ELLIPSOIDAL)
    with pytest.raises(ValueError, match="geoid separation"):
        to_orthometric(ellip)

    converted = to_orthometric(ellip, geoid_separation_m=2.5)
    assert converted.value_m == pytest.approx(9.5)
    assert converted.datum is HeightDatum.ORTHOMETRIC_MPD


def test_local_datum_cannot_be_converted() -> None:
    local = LabelledHeight(3.0, HeightDatum.LOCAL)
    with pytest.raises(ValueError, match="local vertical datum"):
        to_orthometric(local, geoid_separation_m=2.5)


def test_orthometric_conversion_is_idempotent() -> None:
    ortho = LabelledHeight(12.0, HeightDatum.ORTHOMETRIC_MPD)
    assert to_orthometric(ortho) is ortho
