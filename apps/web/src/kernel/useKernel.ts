/* The worker, from React: post a scene, receive the newest result only. */

import { useEffect, useRef } from "react";
import { usePlanner } from "../state/planner";
import type { KernelRequest, KernelResponse } from "./worker";
import type { Camera, Grid, Occluder, Terrain } from "./types";

export function useKernel() {
  const worker = useRef<Worker | null>(null);
  const seq = useRef(0);
  const setPreview = usePlanner((s) => s.setPreview);
  const setComputing = usePlanner((s) => s.setComputing);

  useEffect(() => {
    const w = new Worker(new URL("./worker.ts", import.meta.url), { type: "module" });
    w.onmessage = (e: MessageEvent<KernelResponse>) => {
      const r = e.data;
      if (r.seq !== seq.current) return; // superseded
      setComputing(false);
      setPreview({ ppm: r.ppm, count: r.count, best: r.best_camera, nx: r.nx, nz: r.nz, grid: lastGrid.current!, stats: r.stats, ms: r.ms, spacing: lastGrid.current!.spacing });
    };
    worker.current = w;
    return () => w.terminate();
  }, [setPreview, setComputing]);

  const lastGrid = useRef<Grid | null>(null);

  return (cameras: Camera[], occluders: Occluder[], grid: Grid, terrain: Terrain | null, evalHeightM: number, foreshorten: boolean) => {
    if (!worker.current) return;
    seq.current += 1;
    lastGrid.current = grid;
    setComputing(true);
    const req: KernelRequest = { seq: seq.current, cameras, occluders, grid, terrain, evalHeightM, foreshorten };
    worker.current.postMessage(req);
  };
}

/** Undo the run-length encoding the API uses for the facility mask. */
export function rleToMask(rle: number[], n: number): Uint8Array | null {
  if (!rle.length) return null;
  const out = new Uint8Array(n);
  let pos = 0;
  let value = 0;
  for (const run of rle) {
    if (value) out.fill(1, pos, pos + run);
    pos += run;
    value ^= 1;
  }
  return out;
}
