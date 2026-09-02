"""A deliberately slow, obviously-correct coverage implementation. Build spec 6.5.

Plain Python loops, one cell at a time, no vectorisation, no broad phase, no
cleverness. This is not a fallback and it is not an optimisation target; it is the
thing you diff against when a coverage map looks wrong.

    When a coverage map looks wrong, run both on a small grid, diff the arrays,
    find the first differing cell, work backwards. That is far faster than
    reasoning about vectorised NumPy.  -- CLAUDE.md

It must stay readable enough to check by eye against explained 7.2-7.5. If you find
yourself making it faster, you have misunderstood what it is for.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from groma_contracts.camera import CameraSpec
from groma_contracts.geometry import BoxPrim, CylinderPrim, ExtrudedPolyline
from groma_coverage.kernel import KERNEL_VERSION
from groma_coverage.occluders import RAY_EPS_M
from groma_coverage.terrain import march_step_m
from groma_coverage.types import CoverageResult, Grid, Occluder, Terrain
from groma_geo.optics import camera_basis, f_px, hfov_rad, vfov_rad

Vec = tuple[float, float, float]


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _hit_box(o: Vec, d: Vec, prim: BoxPrim, eps: float) -> bool:
    """Slab test in the box's own frame."""
    cos_y = math.cos(prim.yaw)
    sin_y = math.sin(prim.yaw)

    ox, oy, oz = o[0] - prim.cx, o[1] - prim.cy, o[2] - prim.cz
    lo = (cos_y * ox - sin_y * oz, oy, sin_y * ox + cos_y * oz)
    ld = (cos_y * d[0] - sin_y * d[2], d[1], sin_y * d[0] + cos_y * d[2])

    t_near = -math.inf
    t_far = math.inf
    for axis, half in enumerate((prim.hx, prim.hy, prim.hz)):
        origin_a = lo[axis]
        dir_a = ld[axis]
        if abs(dir_a) < 1e-12:
            if abs(origin_a) > half:
                return False
            continue
        t1 = (-half - origin_a) / dir_a
        t2 = (half - origin_a) / dir_a
        if t1 > t2:
            t1, t2 = t2, t1
        t_near = max(t_near, t1)
        t_far = min(t_far, t2)

    return t_far >= t_near and t_far > eps and t_near < 1.0 - eps


def _hit_cylinder(o: Vec, d: Vec, prim: CylinderPrim, eps: float) -> bool:
    """Plan-view circle quadratic, then the height band."""
    y_lo, y_hi = sorted((prim.y0, prim.y1))

    ox = o[0] - prim.cx
    oz = o[2] - prim.cz
    a = d[0] * d[0] + d[2] * d[2]
    b = 2.0 * (ox * d[0] + oz * d[2])
    c = ox * ox + oz * oz - prim.r * prim.r

    if a < 1e-12:
        if c > 0.0:
            return False
        t_near, t_far = -math.inf, math.inf
    else:
        disc = b * b - 4.0 * a * c
        if disc < 0.0:
            return False
        sq = math.sqrt(disc)
        t_near = (-b - sq) / (2.0 * a)
        t_far = (-b + sq) / (2.0 * a)

    if abs(d[1]) < 1e-12:
        if not (y_lo <= o[1] <= y_hi):
            return False
    else:
        ta = (y_lo - o[1]) / d[1]
        tb = (y_hi - o[1]) / d[1]
        if ta > tb:
            ta, tb = tb, ta
        t_near = max(t_near, ta)
        t_far = min(t_far, tb)

    return t_far >= t_near and t_far > eps and t_near < 1.0 - eps


def _hit_polyline(o: Vec, d: Vec, prim: ExtrudedPolyline, eps: float) -> bool:
    """Each segment is a rotated box; see occluders._prepare_polyline for the yaw."""
    y_lo, y_hi = sorted((prim.y0, prim.y1))
    for (x1, z1), (x2, z2) in zip(prim.points, prim.points[1:], strict=False):
        dx = x2 - x1
        dz = z2 - z1
        length = math.hypot(dx, dz)
        if length < 1e-12:
            continue
        box = BoxPrim(
            cx=0.5 * (x1 + x2),
            cy=0.5 * (y_lo + y_hi),
            cz=0.5 * (z1 + z2),
            hx=0.5 * length,
            hy=0.5 * (y_hi - y_lo),
            hz=0.5 * prim.thickness,
            yaw=math.atan2(-dz, dx),
        )
        if _hit_box(o, d, box, eps):
            return True
    return False


def _hit(o: Vec, d: Vec, occ: Occluder, eps: float) -> bool:
    prim = occ.prim
    if isinstance(prim, BoxPrim):
        return _hit_box(o, d, prim, eps)
    if isinstance(prim, CylinderPrim):
        return _hit_cylinder(o, d, prim, eps)
    return _hit_polyline(o, d, prim, eps)


def _ground_at(terrain: Terrain, x: float, z: float) -> float:
    """Bilinear sample of the heightfield, in plain Python.

    Mirrors Terrain.height_at exactly, including the edge clamp. Written out here
    rather than calling the vectorised version because this file is the thing the
    vectorised version is checked against; sharing the sampler would hide a bug in
    it from T5, which is the one test that would catch it.
    """
    nx, nz = terrain.nx, terrain.nz
    fx = min(max((x - terrain.x_min) / terrain.spacing, 0.0), nx - 1)
    fz = min(max((z - terrain.z_min) / terrain.spacing, 0.0), nz - 1)

    i0 = math.floor(fx)
    j0 = math.floor(fz)
    i1 = min(i0 + 1, nx - 1)
    j1 = min(j0 + 1, nz - 1)

    tx = fx - i0
    tz = fz - j0

    h = terrain.heights
    h00 = float(h[j0, i0])
    h01 = float(h[j0, i1])
    h10 = float(h[j1, i0])
    h11 = float(h[j1, i1])

    top = h00 * (1.0 - tx) + h01 * tx
    bot = h10 * (1.0 - tx) + h11 * tx
    return top * (1.0 - tz) + bot * tz


def _terrain_blocks(o: Vec, d: Vec, terrain: Terrain, eps: float) -> bool:
    """March the heightfield along the plan-view projection.

    Sample k sits (k + 0.5) * march_step_m along the projection. Same rule as
    terrain.terrain_blocks, deliberately: the two must agree sample for sample or
    T5 measures the marches disagreeing rather than the kernels.
    """
    plan = math.hypot(d[0], d[2])
    if plan <= 0.0:
        return False
    step = march_step_m(terrain)
    n_steps = math.ceil(plan / step)
    for k in range(n_steps):
        t = (k + 0.5) * step / plan
        if t <= eps or t >= 1.0 - eps:
            continue
        sx = o[0] + t * d[0]
        sz = o[2] + t * d[2]
        sy = o[1] + t * d[1]
        if sy < _ground_at(terrain, sx, sz):
            return True
    return False


def compute_coverage_reference(
    cameras: Sequence[CameraSpec],
    occluders: Sequence[Occluder],
    grid: Grid,
    terrain: Terrain | None = None,
    eval_height_m: float = 1.6,
    foreshorten: bool = True,
) -> CoverageResult:
    """Same contract as kernel.compute_coverage, computed one cell at a time."""
    nz, nx = grid.nz, grid.nx
    ppm = np.zeros((nz, nx), dtype=np.float64)
    count = np.zeros((nz, nx), dtype=np.uint8)
    best = np.full((nz, nx), -1, dtype=np.int16)
    eval_y = np.zeros((nz, nx), dtype=np.float64)

    for j in range(nz):
        for i in range(nx):
            px = grid.x_min + i * grid.spacing
            pz = grid.z_min + j * grid.spacing
            ground = 0.0 if terrain is None else _ground_at(terrain, px, pz)
            py = ground + eval_height_m
            eval_y[j, i] = py
            target: Vec = (px, py, pz)

            for index, cam in enumerate(cameras):
                if not cam.enabled:
                    continue
                origin: Vec = (cam.position.x, cam.position.y, cam.position.z)
                v = _sub(target, origin)
                dist = math.sqrt(_dot(v, v))
                if dist < cam.near_m or dist > cam.far_m:
                    continue

                forward, right, up = camera_basis(cam.pan_deg, cam.tilt_deg)
                fwd: Vec = (float(forward[0]), float(forward[1]), float(forward[2]))
                rgt: Vec = (float(right[0]), float(right[1]), float(right[2]))
                upv: Vec = (float(up[0]), float(up[1]), float(up[2]))

                zc = _dot(v, fwd)
                if zc <= 0.0:
                    continue
                xc = _dot(v, rgt)
                yc = _dot(v, upv)
                tan_h = math.tan(hfov_rad(cam.sensor_w_mm, cam.focal_mm) / 2.0)
                tan_v = math.tan(vfov_rad(cam.sensor_h_mm, cam.focal_mm) / 2.0)
                if abs(xc) > zc * tan_h or abs(yc) > zc * tan_v:
                    continue

                eps = min(RAY_EPS_M / max(dist, RAY_EPS_M), 0.49)

                transmission = 1.0
                blocked = False
                for occ in occluders:
                    if (
                        cam.mount_structure_id is not None
                        and occ.owner_id == cam.mount_structure_id
                    ):
                        continue
                    if occ.porosity >= 1.0:
                        continue
                    if not _hit(origin, v, occ, eps):
                        continue
                    if occ.porosity <= 0.0:
                        blocked = True
                        break
                    # Factor is porosity itself, not (1 - porosity). See
                    # types.Occluder for why the spec's formula is inverted.
                    transmission *= occ.porosity

                if blocked:
                    continue
                if terrain is not None and _terrain_blocks(origin, v, terrain, eps):
                    continue

                value = f_px(cam.focal_mm, cam.res_y, cam.sensor_h_mm) / dist
                if foreshorten:
                    sin_dep = abs(v[1]) / dist
                    value *= math.sqrt(max(0.0, 1.0 - sin_dep * sin_dep))
                value *= transmission

                count[j, i] += 1
                if value > ppm[j, i]:
                    ppm[j, i] = value
                    best[j, i] = index

    return CoverageResult(
        ppm=ppm.astype(np.float32),
        count=count,
        best_camera=best,
        eval_y=eval_y.astype(np.float32),
        grid=grid,
        kernel_version=KERNEL_VERSION,
    )


__all__ = ["compute_coverage_reference"]
