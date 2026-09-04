/* groma_coverage.terrain: the fine march, sample for sample. The coarse pass of
 * the Python kernel is an exact rejection and changes no result, so it is omitted
 * here; the global y_max rejection is kept because it is nearly free. */

import { terrainHeightAt, type Terrain } from "./types";

export const MARCH_SAMPLES_PER_CELL = 1.0;
export const MAX_MARCH_STEPS = 4096;

export function marchStepM(t: Terrain): number {
  return t.spacing / MARCH_SAMPLES_PER_CELL;
}

export function terrainBlocks(t: Terrain, yMax: number, ox: number, oy: number, oz: number, tx: number, ty: number, tz: number, epsT: number): boolean {
  if (Math.min(oy, ty) > yMax) return false;
  const dx = tx - ox, dy = ty - oy, dz = tz - oz;
  const plan = Math.hypot(dx, dz);
  if (plan <= 0) return false;
  const step = marchStepM(t);
  const n = Math.min(Math.ceil(plan / step), MAX_MARCH_STEPS);
  for (let k = 0; k < n; k++) {
    const s = (k + 0.5) * step / plan;
    if (s <= epsT || s >= 1 - epsT) continue;
    const sy = oy + s * dy;
    if (sy < terrainHeightAt(t, ox + s * dx, oz + s * dz)) return true;
  }
  return false;
}
