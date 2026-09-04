/* The planner's working copy of a scenario: cameras being edited, toggles, the
 * live preview result from the worker. Local until saved. */

import { create } from "zustand";
import type { CameraSpec } from "../api/contracts";
import type { Stats } from "../kernel/stats";

export interface Preview {
  ppm: Float32Array;
  count: Uint8Array;
  best: Int16Array;
  nx: number;
  nz: number;
  grid: { x_min: number; x_max: number; z_min: number; z_max: number; spacing: number };
  stats: Stats;
  ms: number;
  spacing: number;
}

interface PlannerState {
  scenarioId: string | null;
  cameras: CameraSpec[];
  dirty: Set<string>;
  includeTents: boolean;
  includeSeasonal: boolean;
  foreshorten: boolean;
  evalHeight: number;
  preview: Preview | null;
  computing: boolean;
  load: (scenarioId: string, cameras: CameraSpec[], includeSeasonal: boolean) => void;
  updateCamera: (id: string, patch: Partial<CameraSpec>) => void;
  markClean: (id: string) => void;
  setToggle: (k: "includeTents" | "includeSeasonal" | "foreshorten", v: boolean) => void;
  setPreview: (p: Preview | null) => void;
  setComputing: (c: boolean) => void;
}

export const usePlanner = create<PlannerState>((set) => ({
  scenarioId: null,
  cameras: [],
  dirty: new Set(),
  includeTents: true,
  includeSeasonal: true,
  foreshorten: true,
  evalHeight: 1.6,
  preview: null,
  computing: false,
  load: (scenarioId, cameras, includeSeasonal) => set({ scenarioId, cameras, includeSeasonal, dirty: new Set(), preview: null }),
  updateCamera: (id, patch) =>
    set((s) => ({ cameras: s.cameras.map((c) => (c.id === id ? { ...c, ...patch } : c)), dirty: new Set([...s.dirty, id]) })),
  markClean: (id) => set((s) => { const d = new Set(s.dirty); d.delete(id); return { dirty: d }; }),
  setToggle: (k, v) => set({ [k]: v } as Partial<PlannerState>),
  setPreview: (preview) => set({ preview }),
  setComputing: (computing) => set({ computing }),
}));
