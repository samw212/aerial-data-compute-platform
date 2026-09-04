/* Parity with the Python kernel, and the closed-form checks that can be read
 * visually in the viewer: pan cardinals (T9) and self-occlusion (T8). */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import fixture from "./__fixtures__/parity.json";
import { computeCoverage, KERNEL_VERSION } from "./kernel";
import { summarise } from "./stats";
import { gridFromFacility, type Camera, type Grid, type Occluder, type Terrain } from "./types";

type Scene = (typeof fixture)["scenes"][number];

function toGrid(g: Scene["grid"]): Grid {
  return { x_min: g.x_min, x_max: g.x_max, z_min: g.z_min, z_max: g.z_max, spacing: g.spacing, mask: g.mask ? Uint8Array.from(g.mask) : null };
}
function toTerrain(t: Scene["terrain"]): Terrain | null {
  if (!t) return null;
  return { x_min: t.x_min, z_min: t.z_min, spacing: t.spacing, nx: t.nx, nz: t.nz, heights: Float32Array.from(t.heights) };
}

describe("kernel parity with packages/coverage", () => {
  it("carries the same KERNEL_VERSION as kernel.py", () => {
    const py = readFileSync(resolve(process.cwd(), "../../packages/coverage/groma_coverage/kernel.py"), "utf8");
    const m = /KERNEL_VERSION: Final\[str\] = "([^"]+)"/.exec(py);
    expect(m?.[1]).toBe(KERNEL_VERSION);
    expect(fixture.kernel_version).toBe(KERNEL_VERSION);
  });

  for (const scene of fixture.scenes) {
    it(`matches the Python kernel on ${scene.name}`, () => {
      const r = computeCoverage(scene.cameras as Camera[], scene.occluders as Occluder[], toGrid(scene.grid), toTerrain(scene.terrain), scene.eval_height_m, scene.foreshorten);
      const exp = scene.expected;
      expect(r.ppm.length).toBe(exp.ppm.length);
      let differ = 0;
      let countMismatch = 0;
      for (let k = 0; k < r.ppm.length; k++) {
        if (Math.abs(r.ppm[k]! - exp.ppm[k]!) > 1.0) differ++;
        if (r.count[k] !== exp.count[k]) countMismatch++;
      }
      // M3 criterion: < 0.5% of cells differ by > 1 px/m; count identical.
      expect(countMismatch).toBe(0);
      expect(differ / r.ppm.length).toBeLessThan(0.005);
      // In practice the port is exact to float32 rounding.
      let maxAbs = 0;
      for (let k = 0; k < r.ppm.length; k++) maxAbs = Math.max(maxAbs, Math.abs(r.ppm[k]! - exp.ppm[k]!));
      expect(maxAbs).toBeLessThan(0.01);
    });
  }
});

const cam = (pan: number, tilt = 10, mount: string | null = null): Camera => ({
  id: "c", position: { x: 0, y: 10, z: 0 }, pan_deg: pan, tilt_deg: tilt, sensor_w_mm: 5.37, sensor_h_mm: 4.04, focal_mm: 2.8, res_x: 3840, res_y: 2160, near_m: 0.5, far_m: 500, mount_structure_id: mount,
});
const grid: Grid = { x_min: -60, x_max: 60, z_min: -60, z_max: 60, spacing: 1, mask: null };

describe("closed-form checks", () => {
  it("T9 pan cardinals: pan 0 covers -Z, 90 +X, 180 +Z, -90 -X", () => {
    const cases: [number, "x" | "z", number][] = [[0, "z", -1], [90, "x", 1], [180, "z", 1], [-90, "x", -1]];
    for (const [pan, axis, sign] of cases) {
      const r = computeCoverage([cam(pan)], [], grid, null);
      let onSide = 0, offSide = 0;
      for (let j = 0; j < r.nz; j++)
        for (let i = 0; i < r.nx; i++) {
          if (!r.count[j * r.nx + i]) continue;
          const v = axis === "x" ? grid.x_min + i : grid.z_min + j;
          if (v * sign > 0) onSide++; else if (v * sign < 0) offSide++;
        }
      expect(onSide).toBeGreaterThan(100);
      expect(offSide).toBe(0);
    }
  });

  it("T8 self-occlusion: the mount structure never blocks its own camera", () => {
    const mast: Occluder = { id: "mast", owner_id: "mast", prim: { kind: "cylinder", cx: 0, cz: 0, r: 0.3, y0: 0, y1: 12 } };
    const withMount = summarise(computeCoverage([cam(45, 15, "mast")], [mast], grid, null));
    const noOcc = summarise(computeCoverage([cam(45, 15, null)], [], grid, null));
    const blinded = summarise(computeCoverage([cam(45, 15, null)], [mast], grid, null));
    expect(withMount.blind_m2).toBe(noOcc.blind_m2);
    expect(blinded.blind_m2).toBeGreaterThan(noOcc.blind_m2 + 0.4 * (noOcc.area_m2 - noOcc.blind_m2) * 0.5);
  });

  it("T16 facility grid area of the pitch is 7,140 m2 within 0.5%", () => {
    const g = gridFromFacility([[-52.5, -34], [52.5, -34], [52.5, 34], [-52.5, 34]], 0.5);
    let cells = 0;
    for (const v of g.mask!) cells += v;
    expect(Math.abs(cells * 0.25 - 7140) / 7140).toBeLessThan(0.005);
  });
});
