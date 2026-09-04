/* groma_coverage.stats.summarise, mask-aware. */

import type { Camera, CoverageResult } from "./types";

export const DORI = { identify: 250, recognise: 125, observe: 62, detect: 25 } as const;
export type Tier = keyof typeof DORI;
export const TIERS_HARDEST_FIRST: Tier[] = ["identify", "recognise", "observe", "detect"];

export interface Stats {
  kernel_version: string;
  cells: number;
  cell_area_m2: number;
  area_m2: number;
  tier_area_m2: Record<Tier, number>;
  below_detect_m2: number;
  blind_m2: number;
  redundant_2plus_m2: number;
  per_camera_unique_m2: Record<string, number>;
  mean_ppm: number;
}

export function summarise(r: CoverageResult, cameras: Camera[] = []): Stats {
  const cellArea = r.grid.spacing * r.grid.spacing;
  const mask = r.grid.mask;
  let cells = 0, blind = 0, below = 0, red = 0, sum = 0, seenN = 0;
  const tier: Record<Tier, number> = { identify: 0, recognise: 0, observe: 0, detect: 0 };
  const unique = new Map<number, number>();
  for (let k = 0; k < r.ppm.length; k++) {
    if (mask && !mask[k]) continue;
    cells++;
    const p = r.ppm[k]!, c = r.count[k]!;
    for (const t of TIERS_HARDEST_FIRST) if (p >= DORI[t]) tier[t]++;
    if (c === 0) blind++;
    else {
      seenN++; sum += p;
      if (p < DORI.detect) below++;
      if (c >= 2) red++;
      if (c === 1) unique.set(r.best_camera[k]!, (unique.get(r.best_camera[k]!) ?? 0) + 1);
    }
  }
  const perCam: Record<string, number> = {};
  cameras.forEach((cam, i) => { perCam[cam.id] = (unique.get(i) ?? 0) * cellArea; });
  return {
    kernel_version: r.kernel_version, cells, cell_area_m2: cellArea, area_m2: cells * cellArea,
    tier_area_m2: { identify: tier.identify * cellArea, recognise: tier.recognise * cellArea, observe: tier.observe * cellArea, detect: tier.detect * cellArea },
    below_detect_m2: below * cellArea, blind_m2: blind * cellArea, redundant_2plus_m2: red * cellArea,
    per_camera_unique_m2: perCam, mean_ppm: seenN ? sum / seenN : 0,
  };
}

export function tierPct(s: Stats, t: Tier): number {
  return s.area_m2 > 0 ? (100 * s.tier_area_m2[t]) / s.area_m2 : 0;
}
export function blindPct(s: Stats): number {
  return s.area_m2 > 0 ? (100 * s.blind_m2) / s.area_m2 : 0;
}
export function redundantPct(s: Stats): number {
  return s.area_m2 > 0 ? (100 * s.redundant_2plus_m2) / s.area_m2 : 0;
}
