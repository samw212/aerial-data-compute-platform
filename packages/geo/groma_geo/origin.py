"""Rebasing between the Storage and Compute frames. Build spec 3; explained 3.3.

Storage is projected CRS metres (site.srid). Compute is local ENU metres relative
to site.origin, Y up. The rebase happens once, on load.

Why this module exists at all: Hong Kong Grid eastings are around 830,000 m. In
float32 the gap between consecutive representable values there is about 6 cm, so a
model that is nominally accurate to 2 cm loses a third of its precision the moment
it reaches a renderer or any float32 array. Rebasing to a local origin first keeps
coordinates near zero, where float32 resolves sub-millimetre.

Axis mapping, stated once. Storage is (easting, northing, height). Compute is
(x, y, z) with Y up, so:

    x =  easting  - origin_x        east
    y =  height   - origin_z        up
    z = -(northing - origin_y)      south

The negated northing is what makes -Z point north, which is what pan = 0 means.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from groma_contracts.site import SiteOrigin

FloatArray = npt.NDArray[np.float64]


def to_local(points: npt.ArrayLike, origin: SiteOrigin) -> FloatArray:
    """Storage (easting, northing, height) -> Compute (x, y, z), Y up.

    Accepts (3,) or (..., 3). Always returns float64: the whole point is to do the
    subtraction in double precision before anything downcasts.
    """
    arr = np.asarray(points, dtype=np.float64)
    if arr.shape[-1] != 3:
        raise ValueError(f"expected trailing axis of 3, got shape {arr.shape}")
    out = np.empty_like(arr)
    out[..., 0] = arr[..., 0] - origin.x
    out[..., 1] = arr[..., 2] - origin.z
    out[..., 2] = -(arr[..., 1] - origin.y)
    return out


def to_storage(points: npt.ArrayLike, origin: SiteOrigin) -> FloatArray:
    """Compute (x, y, z) -> Storage (easting, northing, height). Inverse of to_local."""
    arr = np.asarray(points, dtype=np.float64)
    if arr.shape[-1] != 3:
        raise ValueError(f"expected trailing axis of 3, got shape {arr.shape}")
    out = np.empty_like(arr)
    out[..., 0] = arr[..., 0] + origin.x
    out[..., 1] = origin.y - arr[..., 2]
    out[..., 2] = arr[..., 1] + origin.z
    return out


def assert_local(points: npt.ArrayLike, limit_m: float = 100_000.0) -> None:
    """Fail loudly if projected coordinates reached code that expects local ENU.

    A Hong Kong Grid easting is ~830,000; a local ENU x is a few hundred at most.
    Call this at the boundary of anything that will downcast to float32.
    """
    arr = np.asarray(points, dtype=np.float64)
    worst = float(np.abs(arr).max()) if arr.size else 0.0
    if worst > limit_m:
        raise ValueError(
            f"coordinate magnitude {worst:.1f} m exceeds {limit_m:.0f} m: these look "
            "like projected coordinates that were never rebased to the site origin "
            "(CLAUDE.md, 'Coordinate frames')"
        )


__all__ = ["assert_local", "to_local", "to_storage"]
