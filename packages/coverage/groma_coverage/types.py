"""Kernel value types. Build spec 6.1.

Pure data. No I/O, no database, no framework, no logging of user data — this
package has to run identically in the worker, the CLI and the browser via WASM.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

from groma_contracts.geometry import BoxPrim, CylinderPrim, ExtrudedPolyline

Primitive = BoxPrim | CylinderPrim | ExtrudedPolyline

F32 = npt.NDArray[np.float32]
F64 = npt.NDArray[np.float64]
U8 = npt.NDArray[np.uint8]
I16 = npt.NDArray[np.int16]


@dataclass(frozen=True)
class Occluder:
    """One thing that can block or attenuate a sightline.

    `owner_id` is the structure or tent id, and it is what mount exclusion matches
    against: a camera on a mast must not be occluded by that mast (T8).

    `porosity` 0 is solid; 1 is fully transparent. Chain-link fencing sits around
    0.85 — geometrically a solid vertical plane, optically nearly transparent. A
    porous occluder does not block the ray, it multiplies the pixel density behind
    it by `porosity`.

    On the attenuation factor, because the specification contradicts itself.
    Build spec 6.4 step 5 says to accumulate transmission as the product of
    (1 - porosity). That cannot be right alongside the definition of the field,
    which build spec 6.1, build spec 4.4 and the extraction defaults in 12.3 all
    state the same way: 0 is solid, 1 is fully transparent, a mesh fence is 0.85
    and a solid wall is 0. Under (1 - porosity) a solid wall would transmit fully
    and a "fully transparent" fence would be opaque — both backwards — and
    explained 7.8's chain-link fence, described as "nearly transparent", would drop
    the pixel density behind it to 15%.

    So the factor here is `porosity` itself: 0 blocks, 1 has no effect, 0.5 halves.
    That satisfies T12 (which pins only the 0.5 case, and which both readings pass)
    and is consistent with every other statement of what the field means. See
    docs/STATUS.md, "Specification discrepancies".
    """

    id: str
    prim: Primitive
    owner_id: str | None = None
    porosity: float = 0.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.porosity <= 1.0:
            raise ValueError(f"porosity must be in [0, 1], got {self.porosity}")

    @property
    def solid(self) -> bool:
        return self.porosity <= 0.0

    @property
    def transparent(self) -> bool:
        """Fully porous occluders are skipped entirely rather than multiplied by 1."""
        return self.porosity >= 1.0


@dataclass(frozen=True)
class Terrain:
    """The DTM as a heightfield in local ENU. Occludes, and defines eval height.

    `heights[j, i]` is the ground Y at x = x_min + i*spacing, z = z_min + j*spacing.
    Row 0 is z_min and column 0 is x_min, matching Grid.centres().
    """

    x_min: float
    z_min: float
    spacing: float
    heights: F32

    _h64: F64 = field(init=False, repr=False, compare=False)
    _y_max: float = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.heights.ndim != 2:
            raise ValueError(f"heights must be 2-D (nz, nx), got shape {self.heights.shape}")
        if self.spacing <= 0:
            raise ValueError(f"spacing must be positive, got {self.spacing}")
        # The heightfield is stored float32 — a DTM rebased to the site origin has
        # no need of more — but the sampling arithmetic runs in float64. Promoting
        # it here rather than inside height_at matters: that method is called on
        # every step of every ray march, and an astype() there copies the whole
        # grid each time. It cost 1.1 s of a 15 s benchmark run.
        object.__setattr__(self, "_h64", self.heights.astype(np.float64))
        object.__setattr__(self, "_y_max", float(self.heights.max()))

    @property
    def y_max(self) -> float:
        """The highest point in the heightfield.

        A ray that stays above this everywhere cannot be blocked by terrain, which
        is the cheapest exact rejection there is.
        """
        return self._y_max

    @property
    def nz(self) -> int:
        return int(self.heights.shape[0])

    @property
    def nx(self) -> int:
        return int(self.heights.shape[1])

    @property
    def x_max(self) -> float:
        return self.x_min + (self.nx - 1) * self.spacing

    @property
    def z_max(self) -> float:
        return self.z_min + (self.nz - 1) * self.spacing

    def height_at(self, x: npt.ArrayLike, z: npt.ArrayLike) -> F64:
        """Bilinear sample of the heightfield, vectorised.

        Queries outside the grid clamp to the edge rather than returning nodata.
        A coverage grid slightly larger than the DTM is normal — the DTM stops at
        the survey boundary — and clamping keeps the site edge occluding sensibly
        instead of opening a hole in the terrain.
        """
        xs = np.asarray(x, dtype=np.float64)
        zs = np.asarray(z, dtype=np.float64)

        fx = np.clip((xs - self.x_min) / self.spacing, 0.0, self.nx - 1)
        fz = np.clip((zs - self.z_min) / self.spacing, 0.0, self.nz - 1)

        i0 = np.floor(fx).astype(np.intp)
        j0 = np.floor(fz).astype(np.intp)
        i1 = np.minimum(i0 + 1, self.nx - 1)
        j1 = np.minimum(j0 + 1, self.nz - 1)

        tx = fx - i0
        tz = fz - j0

        h = self._h64
        h00 = h[j0, i0]
        h01 = h[j0, i1]
        h10 = h[j1, i0]
        h11 = h[j1, i1]

        top = h00 * (1.0 - tx) + h01 * tx
        bot = h10 * (1.0 - tx) + h11 * tx
        return np.asarray(top * (1.0 - tz) + bot * tz, dtype=np.float64)


def _cell_count(extent: float, spacing: float) -> int:
    """Cells spanning `extent` at `spacing`.

    One cell per `spacing` of extent, so a 132 x 82 m site at 0.25 m is
    528 x 328 = 173,184 cells and covers exactly 10,824 m2 — the figures the
    performance target in build spec 6.4 is quoted against. Rounded rather than
    floored so that 132.0 / 0.25 does not come out as 527 when the division lands
    a machine epsilon low.
    """
    if extent <= 0:
        return 0
    count = round(extent / spacing)
    return max(count, 1)


@dataclass(frozen=True)
class Grid:
    """The sample grid for one coverage run, in local ENU metres.

    `nx * nz` cells of `spacing` square, with cell (0, 0) sampled at
    (x_min, z_min). The sample sits at the cell's lower corner rather than its
    middle, which is what build spec 6.1 pins down: "Row 0 is z_min, column 0 is
    x_min. Never change this ordering; the heatmap texture depends on it."
    """

    x_min: float
    x_max: float
    z_min: float
    z_max: float
    spacing: float

    def __post_init__(self) -> None:
        if self.spacing <= 0:
            raise ValueError(f"spacing must be positive, got {self.spacing}")
        if self.x_max <= self.x_min or self.z_max <= self.z_min:
            raise ValueError("grid extent must be positive in both axes")

    @property
    def nx(self) -> int:
        return _cell_count(self.x_max - self.x_min, self.spacing)

    @property
    def nz(self) -> int:
        return _cell_count(self.z_max - self.z_min, self.spacing)

    @property
    def cells(self) -> int:
        return self.nx * self.nz

    @property
    def cell_area_m2(self) -> float:
        return self.spacing * self.spacing

    def centres(self) -> tuple[F64, F64]:
        """(X, Z) of shape (nz, nx). Row 0 is z_min, column 0 is x_min.

        Never change this ordering; the heatmap texture depends on it.
        """
        xs = self.x_min + np.arange(self.nx, dtype=np.float64) * self.spacing
        zs = self.z_min + np.arange(self.nz, dtype=np.float64) * self.spacing
        return np.meshgrid(xs, zs)


@dataclass
class CoverageResult:
    """One coverage grid.

    `ppm` is the best pixel density any camera achieves at that cell; 0 means no
    sightline from anything. `eval_y` records the absolute height actually
    evaluated at, so a report can state it rather than implying 1.6 m above a
    datum it was never measured from.
    """

    ppm: F32
    count: U8
    best_camera: I16
    eval_y: F32
    grid: Grid
    kernel_version: str

    def __post_init__(self) -> None:
        shape = (self.grid.nz, self.grid.nx)
        for name in ("ppm", "count", "best_camera", "eval_y"):
            arr = getattr(self, name)
            if arr.shape != shape:
                raise ValueError(f"{name} has shape {arr.shape}, expected {shape}")


__all__ = [
    "CoverageResult",
    "Grid",
    "Occluder",
    "Primitive",
    "Terrain",
]
