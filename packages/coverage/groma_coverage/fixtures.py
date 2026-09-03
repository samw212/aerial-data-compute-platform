"""Building a coverage scene from an authored site fixture.

This is the one place that turns fixtures/sites/*.json into cameras, occluders and
a grid, so the golden test, the CLI and the benchmark all build the same scene. A
second copy of this arrangement would let the golden drift away from what the
benchmark measures without either failing.

Reading a file is I/O, and the kernel is meant to be pure — so nothing in
kernel.py, occluders.py, terrain.py or stats.py imports this module. It is a
convenience for callers, not part of the kernel.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from groma_contracts.camera import CameraSpec
from groma_contracts.geometry import Vec3
from groma_contracts.site import SiteFixture
from groma_coverage.types import Grid, Occluder

# The T13 golden camera: 8 mm lens on a 1/2.8" sensor, 4K, mounted at 14 m with
# 18 degrees of downtilt, aimed at the centre of the site (build spec 6.6).
GOLDEN_SENSOR_W_MM = 5.37
GOLDEN_SENSOR_H_MM = 4.04
GOLDEN_FOCAL_MM = 8.0
GOLDEN_RES_X = 3840
GOLDEN_RES_Y = 2160
GOLDEN_MOUNT_HEIGHT_M = 14.0
GOLDEN_TILT_DEG = 18.0
GOLDEN_BRACKET_M = 0.75
GOLDEN_FAR_M = 200.0

GOLDEN_CAMERA_MASTS = ("mast_sw", "mast_se", "mast_ne", "mast_nw")


def load_site(path: str | Path) -> SiteFixture:
    with Path(path).open(encoding="utf-8") as fh:
        return SiteFixture.model_validate(json.load(fh))


def pan_towards(from_x: float, from_z: float, to_x: float, to_z: float) -> float:
    """Pan in degrees that points from one plan position to another.

    The convention is pan 0 along -Z, increasing clockwise from above, so the
    plan-view forward direction is (sin pan, -cos pan). Matching that to
    (dx, dz) gives pan = atan2(dx, -dz).
    """
    return math.degrees(math.atan2(to_x - from_x, -(to_z - from_z)))


def site_occluders(
    site: SiteFixture,
    include_seasonal: bool = True,
) -> list[Occluder]:
    """Occluders for every authored structure.

    An authored fixture is truth, so every structure counts as accepted. Reading
    from the database instead, the query is
    `structure WHERE state = 'accepted'` and nothing else.
    """
    out: list[Occluder] = []
    for s in site.structures:
        if s.seasonal and not include_seasonal:
            continue
        out.append(
            Occluder(
                id=s.name,
                prim=s.primitive,
                owner_id=s.name,
                porosity=s.porosity,
            )
        )
    return out


def golden_cameras(site: SiteFixture) -> list[CameraSpec]:
    """The four corner-mast cameras of the T13 layout.

    Each sits on its mast at 14 m, offset along the bracket towards the site
    centre, and is aimed at (0, 0). `mount_structure_id` is set to its own mast:
    without it the mast occludes the camera it carries, and half the site goes
    dark for a reason that looks like anything but the real one (T8).
    """
    by_name = {s.name: s for s in site.structures}
    cameras: list[CameraSpec] = []

    for mast in GOLDEN_CAMERA_MASTS:
        s = by_name[mast]
        prim = s.primitive
        if prim.kind != "cylinder":  # pragma: no cover - fixture is authored
            raise TypeError(f"{mast} is a {prim.kind}, expected a cylinder")

        pan = pan_towards(prim.cx, prim.cz, 0.0, 0.0)

        # Push the lens off the centreline, towards where it is looking.
        rad = math.radians(pan)
        offset = prim.r + GOLDEN_BRACKET_M
        lens_x = prim.cx + offset * math.sin(rad)
        lens_z = prim.cz - offset * math.cos(rad)

        cameras.append(
            CameraSpec(
                id=f"cam_{mast}",
                name=f"Camera on {mast}",
                position=Vec3(x=lens_x, y=GOLDEN_MOUNT_HEIGHT_M, z=lens_z),
                pan_deg=pan,
                tilt_deg=GOLDEN_TILT_DEG,
                sensor_w_mm=GOLDEN_SENSOR_W_MM,
                sensor_h_mm=GOLDEN_SENSOR_H_MM,
                focal_mm=GOLDEN_FOCAL_MM,
                res_x=GOLDEN_RES_X,
                res_y=GOLDEN_RES_Y,
                near_m=1.0,
                far_m=GOLDEN_FAR_M,
                mount_structure_id=mast,
                bracket_offset_m=GOLDEN_BRACKET_M,
            )
        )

    return cameras


def site_grid(site: SiteFixture, spacing: float = 0.5) -> Grid:
    return Grid(
        x_min=site.x_min,
        x_max=site.x_max,
        z_min=site.z_min,
        z_max=site.z_max,
        spacing=spacing,
    )


def tent_grid(
    rows: int = 3,
    cols: int = 4,
    size_m: float = 8.0,
    height_m: float = 3.2,
    spacing_x_m: float = 20.0,
    spacing_z_m: float = 14.0,
) -> list[Occluder]:
    """The event-tent scenario from build spec 6.6.

    A 3 x 4 grid of 8 x 8 x 3.2 m tents at 20 m and 14 m spacing, centred on the
    pitch. Tents are solid: marquee fabric is not chain-link.
    """
    from groma_contracts.geometry import BoxPrim

    half = 0.5 * size_m
    out: list[Occluder] = []
    for row in range(rows):
        for col in range(cols):
            cx = (col - (cols - 1) / 2.0) * spacing_x_m
            cz = (row - (rows - 1) / 2.0) * spacing_z_m
            name = f"tent_r{row}c{col}"
            out.append(
                Occluder(
                    id=name,
                    prim=BoxPrim(
                        cx=cx,
                        cy=0.5 * height_m,
                        cz=cz,
                        hx=half,
                        hy=0.5 * height_m,
                        hz=half,
                    ),
                    owner_id=name,
                    porosity=0.0,
                )
            )
    return out


__all__ = [
    "golden_cameras",
    "load_site",
    "pan_towards",
    "site_grid",
    "site_occluders",
    "tent_grid",
]
