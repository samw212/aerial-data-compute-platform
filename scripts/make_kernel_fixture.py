"""Export a kernel parity fixture for the TypeScript port. Build spec 17 (M3).

Writes apps/web/src/kernel/__fixtures__/parity.json: three scenes with their
inputs and the Python kernel's per-cell outputs. The browser kernel must match
within the M3 criterion (< 0.5% of cells differ by > 1 px/m), and the count array
must be identical. The scenes are small enough to keep the fixture under 1 MB.

    uv run python scripts/make_kernel_fixture.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from groma_contracts.camera import CameraSpec
from groma_contracts.geometry import BoxPrim, CylinderPrim, ExtrudedPolyline, Vec3
from groma_coverage.fixtures import golden_cameras, load_site, site_occluders, tent_grid
from groma_coverage.kernel import KERNEL_VERSION, compute_coverage
from groma_coverage.types import Grid, Occluder, Terrain

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "apps" / "web" / "src" / "kernel" / "__fixtures__" / "parity.json"


def occ_json(o: Occluder) -> dict[str, Any]:
    return {
        "id": o.id,
        "owner_id": o.owner_id,
        "porosity": o.porosity,
        "prim": o.prim.model_dump(mode="json"),
    }


def grid_json(g: Grid) -> dict[str, Any]:
    return {
        "x_min": g.x_min,
        "x_max": g.x_max,
        "z_min": g.z_min,
        "z_max": g.z_max,
        "spacing": g.spacing,
        "mask": None if g.mask is None else [int(v) for v in g.mask.ravel()],
    }


def terrain_json(t: Terrain | None) -> dict[str, Any] | None:
    if t is None:
        return None
    return {
        "x_min": t.x_min,
        "z_min": t.z_min,
        "spacing": t.spacing,
        "nz": t.nz,
        "nx": t.nx,
        "heights": [round(float(v), 4) for v in t.heights.ravel()],
    }


def scene(name, cams, occ, grid, terrain, eval_h=1.6, foreshorten=True) -> dict[str, Any]:
    r = compute_coverage(cams, occ, grid, terrain, eval_h, foreshorten)
    return {
        "name": name,
        "cameras": [c.model_dump(mode="json") for c in cams],
        "occluders": [occ_json(o) for o in occ],
        "grid": grid_json(grid),
        "terrain": terrain_json(terrain),
        "eval_height_m": eval_h,
        "foreshorten": foreshorten,
        "expected": {
            "ppm": [round(float(v), 3) for v in r.ppm.ravel()],
            "count": [int(v) for v in r.count.ravel()],
            "best_camera": [int(v) for v in r.best_camera.ravel()],
        },
    }


def main() -> None:
    site = load_site(REPO / "fixtures" / "sites" / "site_alpha.json")
    cams = golden_cameras(site)
    scenes = []

    # 1. site_alpha at 1 m with the tents: every primitive kind, porosity, mount exclusion.
    grid = Grid(x_min=site.x_min, x_max=site.x_max, z_min=site.z_min, z_max=site.z_max, spacing=1.0)
    scenes.append(
        scene("site_alpha_1m_tents", cams, site_occluders(site) + tent_grid(), grid, None)
    )

    # 2. Facility mask on the pitch polygon at 1 m (mask + from_facility snapping).
    pitch = [(-52.5, -34.0), (52.5, -34.0), (52.5, 34.0), (-52.5, 34.0)]
    scenes.append(
        scene("pitch_mask_1m", cams, site_occluders(site), Grid.from_facility(pitch, 1.0), None)
    )

    # 3. Terrain: a ridge on a slope, one wide camera, a porous wall, a rotated box, a pole.
    nx, nz = 61, 41
    xs = np.arange(nx) * 1.0 - 10.0
    profile = np.where(np.abs(xs - 20.0) <= 2.0, 3.0, 0.0) + 0.04 * (xs + 10.0)
    heights = np.tile(profile, (nz, 1)).astype(np.float32)
    terrain = Terrain(x_min=-10.0, z_min=-20.0, spacing=1.0, heights=heights)
    cam = CameraSpec(
        id="wide",
        name="wide",
        position=Vec3(x=0.0, y=10.0, z=0.0),
        pan_deg=90.0,
        tilt_deg=8.0,
        sensor_w_mm=5.37,
        sensor_h_mm=4.04,
        focal_mm=2.8,
        res_x=3840,
        res_y=2160,
        near_m=0.5,
        far_m=300.0,
    )
    occ = [
        Occluder(
            id="wall",
            prim=ExtrudedPolyline(
                points=[(30.0, -6.0), (30.0, 6.0)], y0=0.0, y1=4.0, thickness=0.3
            ),
            owner_id="wall",
            porosity=0.5,
        ),
        Occluder(
            id="hut",
            prim=BoxPrim(cx=12.0, cy=1.5, cz=-8.0, hx=2.0, hy=1.5, hz=1.0, yaw=0.6),
            owner_id="hut",
        ),
        Occluder(
            id="pole", prim=CylinderPrim(cx=6.0, cz=5.0, r=0.3, y0=0.0, y1=9.0), owner_id="pole"
        ),
    ]
    grid3 = Grid(x_min=-10.0, x_max=50.0, z_min=-20.0, z_max=20.0, spacing=0.5)
    scenes.append(scene("terrain_ridge_slope", [cam], occ, grid3, terrain))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"kernel_version": KERNEL_VERSION, "scenes": scenes}, separators=(",", ":"))
    )
    print(
        f"wrote {OUT.relative_to(REPO)} ({OUT.stat().st_size / 1024:.0f} KB, {len(scenes)} scenes)"
    )


if __name__ == "__main__":
    main()
