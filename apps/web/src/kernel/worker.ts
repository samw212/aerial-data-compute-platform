/* The kernel in a Web Worker: the planner posts a scene, gets typed arrays back
 * (transferred, not copied). One request in flight at a time; a newer request
 * supersedes an older one on the main thread side. */

import { computeCoverage } from "./kernel";
import { summarise, type Stats } from "./stats";
import type { Camera, Grid, Occluder, Terrain } from "./types";

export interface KernelRequest {
  seq: number;
  cameras: Camera[];
  occluders: Occluder[];
  grid: Grid;
  terrain: Terrain | null;
  evalHeightM: number;
  foreshorten: boolean;
}

export interface KernelResponse {
  seq: number;
  ppm: Float32Array;
  count: Uint8Array;
  best_camera: Int16Array;
  nx: number;
  nz: number;
  stats: Stats;
  ms: number;
}

self.onmessage = (e: MessageEvent<KernelRequest>) => {
  const req = e.data;
  const t0 = performance.now();
  const r = computeCoverage(req.cameras, req.occluders, req.grid, req.terrain, req.evalHeightM, req.foreshorten);
  const stats = summarise(r, req.cameras);
  const out: KernelResponse = { seq: req.seq, ppm: r.ppm, count: r.count, best_camera: r.best_camera, nx: r.nx, nz: r.nz, stats, ms: performance.now() - t0 };
  (self as unknown as Worker).postMessage(out, [r.ppm.buffer, r.count.buffer, r.best_camera.buffer]);
};
