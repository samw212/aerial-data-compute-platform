/* groma_coverage.kernel. Bump KERNEL_VERSION together with the Python one. */

import { hits, prepare, RAY_EPS_M, type Prepared } from "./occluders";
import { cameraBasis, fPx, hfovRad, vfovRad } from "./optics";
import { terrainBlocks } from "./terrain";
import { gridNx, gridNz, terrainHeightAt, terrainMax, type Camera, type CoverageResult, type Grid, type Occluder, type Terrain } from "./types";

export const KERNEL_VERSION = "1.1.0";

export function computeCoverage(
  cameras: Camera[],
  occluders: Occluder[],
  grid: Grid,
  terrain: Terrain | null,
  evalHeightM = 1.6,
  foreshorten = true,
): CoverageResult {
  const nx = gridNx(grid), nz = gridNz(grid), n = nx * nz;
  const xs = new Float64Array(n), ys = new Float64Array(n), zs = new Float64Array(n);
  for (let j = 0; j < nz; j++)
    for (let i = 0; i < nx; i++) {
      const k = j * nx + i;
      const x = grid.x_min + i * grid.spacing, z = grid.z_min + j * grid.spacing;
      xs[k] = x; zs[k] = z;
      ys[k] = (terrain ? terrainHeightAt(terrain, x, z) : 0) + evalHeightM;
    }
  const ppm = new Float64Array(n);
  const count = new Uint8Array(n);
  const best = new Int16Array(n).fill(-1);
  const prepared: Prepared[] = occluders.map(prepare);
  const yMax = terrain ? terrainMax(terrain) : -Infinity;

  cameras.forEach((cam, index) => {
    if (cam.enabled === false) return;
    if ((cam.roll_deg ?? 0) !== 0) throw new Error(`camera ${cam.id} has roll; the frustum test is roll-free`);
    const ox = cam.position.x, oy = cam.position.y, oz = cam.position.z;
    const near = cam.near_m ?? 1, far = cam.far_m ?? 200;
    const near2 = near * near, far2 = far * far;
    const { forward: f, right: r, up: u } = cameraBasis(cam.pan_deg, cam.tilt_deg);
    const tanH = Math.tan(hfovRad(cam.sensor_w_mm, cam.focal_mm) / 2);
    const tanV = Math.tan(vfovRad(cam.sensor_h_mm, cam.focal_mm) / 2);
    const fpx = fPx(cam.focal_mm, cam.res_y, cam.sensor_h_mm);
    const mount = cam.mount_structure_id ?? null;
    const occ = prepared.filter((p) => !p.transparent && !(mount !== null && p.ownerId === mount));

    for (let k = 0; k < n; k++) {
      const vx = xs[k]! - ox, vy = ys[k]! - oy, vz = zs[k]! - oz;
      const d2 = vx * vx + vy * vy + vz * vz;
      if (d2 < near2 || d2 > far2) continue;
      const zc = vx * f[0] + vy * f[1] + vz * f[2];
      if (zc <= 0) continue;
      const xc = vx * r[0] + vy * r[1] + vz * r[2];
      if (Math.abs(xc) > zc * tanH) continue;
      const yc = vx * u[0] + vy * u[1] + vz * u[2];
      if (Math.abs(yc) > zc * tanV) continue;
      const d = Math.sqrt(d2);
      const epsT = Math.min(RAY_EPS_M / Math.max(d, RAY_EPS_M), 0.49);
      let transmission = 1;
      let blocked = false;
      for (const p of occ) {
        if (!hits(p, ox, oy, oz, xs[k]!, ys[k]!, zs[k]!, epsT)) continue;
        if (p.solid) { blocked = true; break; }
        transmission *= p.porosity;
      }
      if (blocked) continue;
      if (terrain && terrainBlocks(terrain, yMax, ox, oy, oz, xs[k]!, ys[k]!, zs[k]!, epsT)) continue;
      let value = fpx / d;
      if (foreshorten) {
        const sinDep = Math.abs(vy) / d;
        value *= Math.sqrt(Math.max(0, 1 - sinDep * sinDep));
      }
      value *= transmission;
      count[k] = count[k]! + 1;
      if (value > ppm[k]!) { ppm[k] = value; best[k] = index; }
    }
  });

  return { ppm: Float32Array.from(ppm), count, best_camera: best, eval_y: Float32Array.from(ys), nx, nz, grid, kernel_version: KERNEL_VERSION };
}
