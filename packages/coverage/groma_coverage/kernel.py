"""The coverage kernel. Build spec 6.3, 6.4.

Pure. NumPy in, NumPy out. No I/O, no database, no framework, no logging of user
data, so that it runs identically in the worker, the CLI and the browser via WASM.

KERNEL_VERSION is recorded on every coverage_run and printed in every report,
because these numbers end up in tender documents. Bump it for ANY behavioural
change, and explain the movement in the commit message before touching a golden
file.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import numpy as np

from groma_contracts.camera import CameraSpec
from groma_coverage.occluders import (
    RAY_EPS_M,
    PreparedOccluder,
    SegmentBatch,
    prepare,
)
from groma_coverage.terrain import eval_heights, terrain_blocks
from groma_coverage.types import CoverageResult, Grid, Occluder, Terrain
from groma_geo.optics import camera_basis, f_px, hfov_rad, vfov_rad

KERNEL_VERSION: Final[str] = "1.1.0"


def compute_coverage(
    cameras: Sequence[CameraSpec],
    occluders: Sequence[Occluder],
    grid: Grid,
    terrain: Terrain | None = None,
    eval_height_m: float = 1.6,
    foreshorten: bool = True,
) -> CoverageResult:
    """Best achievable pixel density per grid cell, across all enabled cameras.

    `eval_height_m` is above the local terrain surface, not above the datum. Where
    `terrain` is None the ground is the plane y = 0. The height actually used is
    recorded per cell in `CoverageResult.eval_y`, so a report can state it.

    Cameras are indexed by their position in `cameras`, including disabled ones, so
    that `best_camera` indices stay stable when a camera is toggled in the UI.
    """
    nz, nx = grid.nz, grid.nx

    xs, zs = grid.centres()
    ys = eval_heights(xs, zs, terrain, eval_height_m)

    # (cells, 3) targets. Flattened once; every per-camera pass reuses this.
    targets = np.stack([xs.ravel(), ys.ravel(), zs.ravel()], axis=1)
    n_cells = targets.shape[0]

    ppm = np.zeros(n_cells, dtype=np.float64)
    count = np.zeros(n_cells, dtype=np.uint8)
    best = np.full(n_cells, -1, dtype=np.int16)

    prepared = [prepare(o) for o in occluders]

    for index, cam in enumerate(cameras):
        if not cam.enabled:
            continue
        if cam.roll_deg != 0.0:
            raise NotImplementedError(
                f"camera {cam.id!r} has roll_deg={cam.roll_deg}; the frustum test is "
                "roll-free (groma_geo.optics.camera_basis). Rolled frusta need the "
                "basis rotated about forward and the analytic tests extended."
            )

        cam_ppm, cam_seen = _coverage_one_camera(cam, prepared, targets, terrain, foreshorten)

        improved = cam_seen & (cam_ppm > ppm)
        ppm = np.where(improved, cam_ppm, ppm)
        best = np.where(improved, np.int16(index), best)
        count += cam_seen.astype(np.uint8)

    return CoverageResult(
        ppm=ppm.reshape(nz, nx).astype(np.float32),
        count=count.reshape(nz, nx),
        best_camera=best.reshape(nz, nx),
        eval_y=ys.reshape(nz, nx).astype(np.float32),
        grid=grid,
        kernel_version=KERNEL_VERSION,
    )


def _coverage_one_camera(
    cam: CameraSpec,
    prepared: Sequence[PreparedOccluder],
    targets: np.ndarray,
    terrain: Terrain | None,
    foreshorten: bool,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (ppm, seen) over all cells for one camera.

    `seen` is the camera-count contribution: a cell is seen if it is in range, in
    the frustum, and not fully blocked. A cell behind a porous occluder is seen,
    at a reduced pixel density.
    """
    n_cells = targets.shape[0]
    ppm = np.zeros(n_cells, dtype=np.float64)
    seen = np.zeros(n_cells, dtype=bool)

    origin = np.array([cam.position.x, cam.position.y, cam.position.z], dtype=np.float64)

    # Step 1: V = P - camera.position, and squared range.
    v = targets - origin
    d2 = np.einsum("ij,ij->i", v, v)

    # Step 2: range gate.
    mask = (d2 >= cam.near_m * cam.near_m) & (d2 <= cam.far_m * cam.far_m)
    if not np.any(mask):
        return ppm, seen

    # Step 3: frustum, in the camera basis.
    forward, right, up = camera_basis(cam.pan_deg, cam.tilt_deg)
    tan_h = np.tan(hfov_rad(cam.sensor_w_mm, cam.focal_mm) / 2.0)
    tan_v = np.tan(vfov_rad(cam.sensor_h_mm, cam.focal_mm) / 2.0)

    zc = v @ forward
    mask &= zc > 0.0
    if not np.any(mask):
        return ppm, seen
    xc = v @ right
    yc = v @ up
    mask &= (np.abs(xc) <= zc * tan_h) & (np.abs(yc) <= zc * tan_v)

    # Step 4: reduce to surviving candidates. Typically 10-40% of cells, and every
    # occlusion test below is proportional to this count.
    cand = np.flatnonzero(mask)
    if cand.size == 0:
        return ppm, seen

    cand_targets = targets[cand]
    d = np.sqrt(d2[cand])
    eps_t = np.minimum(RAY_EPS_M / np.maximum(d, RAY_EPS_M), 0.49)

    # Step 5: occlusion. Solid occluders block; porous ones attenuate.
    transmission = np.ones(cand.size, dtype=np.float64)
    blocked = np.zeros(cand.size, dtype=bool)
    batch = SegmentBatch.build(origin, cand_targets)

    for occ in prepared:
        # Exclusion: a camera is never occluded by the structure it is mounted on.
        # Half of the self-occlusion fix; the other half is the bracket offset,
        # already applied to cam.position (explained 7.7, T8).
        if cam.mount_structure_id is not None and occ.owner_id == cam.mount_structure_id:
            continue
        if occ.transmission >= 1.0:
            continue

        near = occ.broad_phase(batch)
        live = near & ~blocked
        if not np.any(live):
            continue

        idx = np.flatnonzero(live)
        hit = occ.hits(origin, cand_targets[idx], eps_t[idx])
        if not np.any(hit):
            continue

        struck = idx[hit]
        if occ.solid:
            blocked[struck] = True
        else:
            transmission[struck] *= occ.transmission

    # Step 6: terrain occlusion.
    if terrain is not None:
        live = ~blocked
        if np.any(live):
            idx = np.flatnonzero(live)
            ground_hit = terrain_blocks(origin, cand_targets[idx], terrain, eps_t[idx])
            blocked[idx[ground_hit]] = True

    visible = ~blocked
    if not np.any(visible):
        return ppm, seen

    # Step 7: pixel density.
    f = f_px(cam.focal_mm, cam.res_y, cam.sensor_h_mm)
    value = f / d
    if foreshorten:
        # cos of the depression angle: the target is a vertical surface, so a ray
        # arriving steeply from above sees a foreshortened face.
        sin_dep = np.abs(v[cand, 1]) / d
        value = value * np.sqrt(np.maximum(0.0, 1.0 - sin_dep * sin_dep))
    value = value * transmission

    out_idx = cand[visible]
    ppm[out_idx] = value[visible]
    seen[out_idx] = True
    return ppm, seen


__all__ = ["KERNEL_VERSION", "compute_coverage"]
