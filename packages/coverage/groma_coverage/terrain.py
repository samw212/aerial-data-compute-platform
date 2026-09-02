"""Terrain occlusion and evaluation height. Build spec 6.4 step 6.

The terrain grid does two jobs, and conflating them is a bug worth naming:

1. It occludes. A camera behind a ridge cannot see over it, and that shadow obeys
   the same formula as a wall shadow (T10).
2. It sets the evaluation height. Targets are 1.6 m above the local ground, not
   1.6 m above the datum. On a 5% slope those differ by metres across a pitch
   (T11).

The march samples the heightfield along the segment's plan-view projection at
roughly one sample per terrain cell, and asks whether the ray ever dips below the
ground between the camera and the target. Sampling at the grid resolution is what
makes a ridge occlude at the place the ridge actually is; a coarser march steps
over narrow ridges entirely.
"""

from __future__ import annotations

import numpy as np

from groma_coverage.types import F64, Terrain

MARCH_SAMPLES_PER_CELL = 1.0
"""Samples per terrain cell along the ray. Raising this costs time linearly and
changes results only for terrain with features narrower than one cell, which the
DTM cannot represent anyway."""

MAX_MARCH_STEPS = 4096
"""Hard cap, so a pathological far plane cannot allocate an unbounded array."""


def march_step_m(terrain: Terrain) -> float:
    """Distance between samples, measured along the ray's plan-view projection.

    Defined in metres rather than as a count so that a ray's sample positions
    depend only on its own length. A step count shared across a whole grid would
    put the samples in different places for the fast kernel and for reference.py,
    and T5 would fail on sloped terrain for a reason that is not a bug in either.
    """
    return terrain.spacing / MARCH_SAMPLES_PER_CELL


def terrain_blocks(
    origin: F64,
    targets: F64,
    terrain: Terrain,
    eps_t: F64,
) -> np.ndarray:
    """Boolean mask: does the ground interrupt the sightline to each target?

    Samples at k = 0, 1, 2, ... along the plan-view projection, at distances
    (k + 0.5) * march_step_m, for as long as that distance is inside the segment.

    Tested strictly inside (eps, 1 - eps). The endpoints are excluded on purpose:
    a target evaluated 1.6 m above the ground sits directly over terrain that is,
    by construction, at its own height, and including t = 1 would make every cell
    on a slope shadow itself.
    """
    n = targets.shape[0]
    blocked = np.zeros(n, dtype=bool)
    if n == 0:
        return blocked

    dx = targets[:, 0] - origin[0]
    dz = targets[:, 2] - origin[2]
    dy = targets[:, 1] - origin[1]
    plan_len = np.hypot(dx, dz)

    # Exact rejection, and by far the cheapest thing in this function. The segment
    # is a straight line, so its lowest point is at one end or the other; a ray
    # that stays above the highest ground in the whole heightfield cannot be
    # interrupted by any of it. On flat or gently sloping terrain — which is most
    # sports grounds — this rejects every ray and the march never runs. It took
    # the benchmark from 12.4 s to under the budget.
    lowest = np.minimum(origin[1], targets[:, 1])
    candidate = (lowest <= terrain.y_max) & (plan_len > 0.0)
    if not np.any(candidate):
        return blocked

    idx = np.flatnonzero(candidate)
    dx = dx[idx]
    dz = dz[idx]
    dy = dy[idx]
    plan_len = plan_len[idx]
    sub_eps = eps_t[idx]

    step = march_step_m(terrain)
    longest = float(plan_len.max())
    n_steps = min(int(np.ceil(longest / step)), MAX_MARCH_STEPS)
    if n_steps <= 0:
        # Every surviving ray is vertical in plan view; no ground to march through.
        return blocked

    offsets = (np.arange(n_steps, dtype=np.float64) + 0.5) * step

    n = idx.size
    sub_blocked = np.zeros(n, dtype=bool)

    # Chunked so that a large grid times a long march does not allocate one huge
    # (n, steps) array. The kernel is pure and single-threaded; memory is the only
    # resource it can exhaust.
    chunk = max(1, min(n, 4_000_000 // n_steps))
    for start in range(0, n, chunk):
        stop = min(start + chunk, n)
        sl = slice(start, stop)

        length = plan_len[sl, None]
        t = offsets[None, :] / length

        sx = origin[0] + t * dx[sl, None]
        sz = origin[2] + t * dz[sl, None]
        sy = origin[1] + t * dy[sl, None]

        ground = terrain.height_at(sx, sz)

        inside = (t > sub_eps[sl, None]) & (t < 1.0 - sub_eps[sl, None])
        sub_blocked[sl] = ((sy < ground) & inside).any(axis=1)

    blocked[idx] = sub_blocked
    return blocked


def eval_heights(
    x: F64,
    z: F64,
    terrain: Terrain | None,
    eval_height_m: float,
) -> F64:
    """Absolute Y at which each cell is evaluated.

    With no terrain the ground is the plane y = 0, so this is just the eval height.
    """
    if terrain is None:
        return np.full(np.shape(x), float(eval_height_m), dtype=np.float64)
    return terrain.height_at(x, z) + eval_height_m


__all__ = ["MARCH_SAMPLES_PER_CELL", "eval_heights", "terrain_blocks"]
