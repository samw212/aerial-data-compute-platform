"""Ray-versus-primitive intersection. Build spec 6.4 step 5; explained 7.2-7.4.

Every test here answers one question, vectorised over many targets at once: does
the segment from the camera to this target pass through this primitive?

The segment is parameterised as O + t*(T - O), with t = 0 at the camera and t = 1
at the target. A hit counts only for t strictly inside (eps, 1 - eps), where eps
corresponds to RAY_EPS_M along the ray. Without the lower bound a camera bracketed
onto a wall shadows itself; without the upper bound an occluder that the target
sits against blocks the target from being seen at all.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from groma_contracts.geometry import BoxPrim, CylinderPrim, ExtrudedPolyline
from groma_coverage.types import F64, Occluder, Primitive

RAY_EPS_M = 0.02
"""Ray start/end offset in metres. Build spec 6.4: 'Start rays at t = eps
corresponding to 2 cm.'"""

_TINY = 1e-12


@dataclass(frozen=True)
class _Box:
    """An oriented box, reduced to centre + half extents + yaw about Y."""

    cx: float
    cy: float
    cz: float
    hx: float
    hy: float
    hz: float
    cos_yaw: float
    sin_yaw: float

    def slab_interval(self, origin: F64, targets: F64) -> tuple[F64, F64]:
        """Return (t_enter, t_exit) of the ray against this box.

        An empty interval comes back as t_enter > t_exit; the caller does not need
        a separate miss flag.
        """
        # Into the box frame: translate to the centre, then rotate by -yaw about Y.
        ox = origin[0] - self.cx
        oy = origin[1] - self.cy
        oz = origin[2] - self.cz
        o = np.array(
            [
                self.cos_yaw * ox - self.sin_yaw * oz,
                oy,
                self.sin_yaw * ox + self.cos_yaw * oz,
            ]
        )

        dx = targets[:, 0] - origin[0]
        dy = targets[:, 1] - origin[1]
        dz = targets[:, 2] - origin[2]
        d = np.empty_like(targets)
        d[:, 0] = self.cos_yaw * dx - self.sin_yaw * dz
        d[:, 1] = dy
        d[:, 2] = self.sin_yaw * dx + self.cos_yaw * dz

        half = np.array([self.hx, self.hy, self.hz])

        # A direction component of exactly zero would divide by zero. Nudging it to
        # a signed tiny value sends both slab bounds to the same infinity, which
        # correctly yields an empty interval when the origin is outside the slab
        # and an unbounded one when it is inside.
        safe = np.where(np.abs(d) < _TINY, np.copysign(_TINY, d), d)
        inv = 1.0 / safe

        t_lo = (-half - o) * inv
        t_hi = (half - o) * inv

        t_near = np.minimum(t_lo, t_hi)
        t_far = np.maximum(t_lo, t_hi)

        return t_near.max(axis=1), t_far.min(axis=1)


@dataclass(frozen=True)
class _Cylinder:
    """A vertical circular cylinder: a plan-view circle intersected with a Y band."""

    cx: float
    cz: float
    r: float
    y0: float
    y1: float

    def slab_interval(self, origin: F64, targets: F64) -> tuple[F64, F64]:
        n = targets.shape[0]

        ox = origin[0] - self.cx
        oz = origin[2] - self.cz
        dx = targets[:, 0] - origin[0]
        dz = targets[:, 2] - origin[2]

        # Plan-view circle: |o2 + t*d2|^2 = r^2.
        a = dx * dx + dz * dz
        b = 2.0 * (ox * dx + oz * dz)
        c = ox * ox + oz * oz - self.r * self.r

        t_near = np.full(n, np.inf)
        t_far = np.full(n, -np.inf)

        # General case: the ray moves in plan view, so the quadratic is real.
        moving = a > _TINY
        disc = b * b - 4.0 * a * c
        real = moving & (disc >= 0.0)
        if np.any(real):
            sq = np.sqrt(disc[real])
            two_a = 2.0 * a[real]
            t_near[real] = (-b[real] - sq) / two_a
            t_far[real] = (-b[real] + sq) / two_a

        # Degenerate case: the ray is vertical in plan view. It is inside the
        # column for all t, or for none.
        vertical = ~moving
        if np.any(vertical):
            inside = c <= 0.0
            hit = vertical & inside
            t_near[hit] = -np.inf
            t_far[hit] = np.inf

        # Intersect with the height band.
        dy = targets[:, 1] - origin[1]
        oy = origin[1]
        safe_dy = np.where(np.abs(dy) < _TINY, np.copysign(_TINY, dy), dy)
        ty_a = (self.y0 - oy) / safe_dy
        ty_b = (self.y1 - oy) / safe_dy
        ty_near = np.minimum(ty_a, ty_b)
        ty_far = np.maximum(ty_a, ty_b)

        return np.maximum(t_near, ty_near), np.minimum(t_far, ty_far)


@dataclass(frozen=True)
class SegmentBatch:
    """The camera-to-target segments for one camera, in the form the broad phase wants.

    All of this depends on the camera and the candidate cells, not on the occluder,
    so it is computed once per camera rather than once per occluder. With thirty
    occluders that is the difference between thirty passes over fifty thousand
    cells and one.
    """

    origin: F64
    targets: F64
    ax: float
    az: float
    abx: F64
    abz: F64
    inv_len2: F64
    y_low: F64
    y_high: F64

    @classmethod
    def build(cls, origin: F64, targets: F64) -> SegmentBatch:
        abx = targets[:, 0] - origin[0]
        abz = targets[:, 2] - origin[2]
        len2 = abx * abx + abz * abz
        inv_len2 = np.where(len2 > _TINY, 1.0 / np.where(len2 > _TINY, len2, 1.0), 0.0)
        ty = targets[:, 1]
        return cls(
            origin=origin,
            targets=targets,
            ax=float(origin[0]),
            az=float(origin[2]),
            abx=abx,
            abz=abz,
            inv_len2=inv_len2,
            y_low=np.minimum(origin[1], ty),
            y_high=np.maximum(origin[1], ty),
        )


@dataclass(frozen=True)
class PreparedOccluder:
    """An occluder reduced to shapes the ray tests understand, plus broad-phase bounds.

    A polyline becomes one rotated box per segment, which is why `shapes` is a
    list: a perimeter fence is one occluder with four or more boxes, not four
    occluders, so mount exclusion and porosity stay attached to the structure.
    """

    id: str
    owner_id: str | None
    porosity: float
    shapes: list[_Box | _Cylinder]
    y_min: float
    y_max: float
    centre_x: float
    centre_z: float
    radius_xz: float
    transmission: float = field(init=False)
    """The factor a surviving ray's pixel density is multiplied by. Equal to
    `porosity`: 0 blocks, 1 has no effect. See types.Occluder for why this is not
    (1 - porosity) as build spec 6.4 step 5 writes it."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "transmission", self.porosity)

    @property
    def solid(self) -> bool:
        return self.porosity <= 0.0

    def broad_phase(self, batch: SegmentBatch) -> np.ndarray:
        """Cheap rejection: which targets could possibly be blocked by this occluder.

        Two tests, both from explained 7.4. Vertical extent first, because cameras
        are high and targets are at 1.6 m, so a 2.4 m fence is below most of the
        path. Then plan-view distance from the occluder's bounding circle to the
        segment, which is one clamped dot product.
        """
        possible = ~((batch.y_low > self.y_max) | (batch.y_high < self.y_min))
        if not np.any(possible):
            return possible

        # Plan-view distance from the occluder centre to the segment. The segment
        # terms come precomputed from the batch; only the occluder centre is new.
        acx = self.centre_x - batch.ax
        acz = self.centre_z - batch.az
        t = (acx * batch.abx + acz * batch.abz) * batch.inv_len2
        np.clip(t, 0.0, 1.0, out=t)
        px = t * batch.abx
        px -= acx
        pz = t * batch.abz
        pz -= acz
        dist2 = px * px + pz * pz

        return possible & (dist2 <= self.radius_xz * self.radius_xz)

    def hits(self, origin: F64, targets: F64, eps_t: F64) -> np.ndarray:
        """Boolean mask: does the segment to each target pass through this occluder?

        `eps_t` is the per-target ray epsilon expressed in t, so that the 2 cm
        offset is constant in metres regardless of how far the target is.
        """
        hit = np.zeros(targets.shape[0], dtype=bool)
        for shape in self.shapes:
            t_near, t_far = shape.slab_interval(origin, targets)
            overlap = (t_far >= t_near) & (t_far > eps_t) & (t_near < 1.0 - eps_t)
            hit |= overlap
        return hit


def _prepare_box(prim: BoxPrim) -> tuple[list[_Box | _Cylinder], float, float, float, float, float]:
    box = _Box(
        cx=prim.cx,
        cy=prim.cy,
        cz=prim.cz,
        hx=prim.hx,
        hy=prim.hy,
        hz=prim.hz,
        cos_yaw=math.cos(prim.yaw),
        sin_yaw=math.sin(prim.yaw),
    )
    radius = math.hypot(prim.hx, prim.hz)
    return (
        [box],
        prim.cy - prim.hy,
        prim.cy + prim.hy,
        prim.cx,
        prim.cz,
        radius,
    )


def _prepare_cylinder(
    prim: CylinderPrim,
) -> tuple[list[_Box | _Cylinder], float, float, float, float, float]:
    y_lo, y_hi = sorted((prim.y0, prim.y1))
    cyl = _Cylinder(cx=prim.cx, cz=prim.cz, r=prim.r, y0=y_lo, y1=y_hi)
    return [cyl], y_lo, y_hi, prim.cx, prim.cz, prim.r


def _prepare_polyline(
    prim: ExtrudedPolyline,
) -> tuple[list[_Box | _Cylinder], float, float, float, float, float]:
    """One rotated box per segment.

    The box's local +X runs along the segment. R_y(yaw) maps local +X to
    (cos yaw, 0, -sin yaw), so aligning that with the segment direction
    (dx, dz)/L gives yaw = atan2(-dz, dx).
    """
    y_lo, y_hi = sorted((prim.y0, prim.y1))
    half_h = 0.5 * (y_hi - y_lo)
    cy = 0.5 * (y_lo + y_hi)
    half_t = 0.5 * prim.thickness

    shapes: list[_Box | _Cylinder] = []
    for (x1, z1), (x2, z2) in zip(prim.points, prim.points[1:], strict=False):
        dx = x2 - x1
        dz = z2 - z1
        length = math.hypot(dx, dz)
        if length < _TINY:
            continue
        yaw = math.atan2(-dz, dx)
        shapes.append(
            _Box(
                cx=0.5 * (x1 + x2),
                cy=cy,
                cz=0.5 * (z1 + z2),
                hx=0.5 * length,
                hy=half_h,
                hz=half_t,
                cos_yaw=math.cos(yaw),
                sin_yaw=math.sin(yaw),
            )
        )

    if not shapes:
        raise ValueError("polyline has no segment with non-zero length")

    xs = [p[0] for p in prim.points]
    zs = [p[1] for p in prim.points]
    centre_x = 0.5 * (min(xs) + max(xs))
    centre_z = 0.5 * (min(zs) + max(zs))
    radius = max(math.hypot(x - centre_x, z - centre_z) for x, z in prim.points) + half_t

    return shapes, y_lo, y_hi, centre_x, centre_z, radius


def prepare(occluder: Occluder) -> PreparedOccluder:
    """Reduce an Occluder to the form the ray tests consume.

    Done once per coverage run, not once per camera, because the reduction depends
    only on the geometry.
    """
    prim: Primitive = occluder.prim
    if isinstance(prim, BoxPrim):
        shapes, y_min, y_max, cx, cz, radius = _prepare_box(prim)
    elif isinstance(prim, CylinderPrim):
        shapes, y_min, y_max, cx, cz, radius = _prepare_cylinder(prim)
    elif isinstance(prim, ExtrudedPolyline):
        shapes, y_min, y_max, cx, cz, radius = _prepare_polyline(prim)
    else:  # pragma: no cover - the union is closed
        raise TypeError(f"unsupported primitive {type(prim).__name__}")

    return PreparedOccluder(
        id=occluder.id,
        owner_id=occluder.owner_id,
        porosity=occluder.porosity,
        shapes=shapes,
        y_min=y_min,
        y_max=y_max,
        centre_x=cx,
        centre_z=cz,
        radius_xz=radius,
    )


__all__ = ["RAY_EPS_M", "PreparedOccluder", "prepare"]
