import { create } from "zustand";

export type ViewMode = "plan" | "3d" | "photo";

interface UiState {
  view: ViewMode;
  setView: (v: ViewMode) => void;
  layers: Record<string, boolean>;
  toggleLayer: (k: string) => void;
  setLayer: (k: string, on: boolean) => void;
  tool: string;
  setTool: (t: string) => void;
  selection: string | null;
  select: (id: string | null) => void;
  stripOpen: boolean;
  toggleStrip: () => void;
}

export const useUi = create<UiState>((set) => ({
  view: "plan",
  setView: (view) => set({ view }),
  layers: { basemap: true, imagery: false, labels: true, ortho: true, structures: true, shots: false, mounts: false, coverage: true, frusta: true, blind: false, tents: true, seasonal: true },
  toggleLayer: (k) => set((s) => ({ layers: { ...s.layers, [k]: !s.layers[k] } })),
  setLayer: (k, on) => set((s) => ({ layers: { ...s.layers, [k]: on } })),
  tool: "select",
  setTool: (tool) => set({ tool }),
  selection: null,
  select: (selection) => set({ selection }),
  stripOpen: true,
  toggleStrip: () => set((s) => ({ stripOpen: !s.stripOpen })),
}));
