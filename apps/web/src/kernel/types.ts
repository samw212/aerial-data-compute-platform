/* The coverage kernel, ported module for module from packages/coverage.
 * KERNEL_VERSION must equal the Python one; kernel.test.ts reads both files.
 * Pure: no DOM, no fetch, no logging. Runs in a Web Worker. */

export type BoxPrim = { kind: "box"; cx: number; cy: number; cz: number; hx: number; hy: number; hz: number; yaw?: number };
export type CylinderPrim = { kind: "cylinder"; cx: number; cz: number; r: number; y0: number; y1: number };
export type ExtrudedPolyline = { kind: "polyline"; points: [number, number][]; y0: number; y1: number; thickness: number };
export type Primitive = BoxPrim | CylinderPrim | ExtrudedPolyline;

export interface Camera {
  id: string;
  position: { x: number; y: number; z: number };
  pan_deg: number;
  tilt_deg: number;
  roll_deg?: number;
  sensor_w_mm: number;
  sensor_h_mm: number;
  focal_mm: number;
  res_x: number;
  res_y: number;
  near_m?: number;
  far_m?: number;
  mount_structure_id?: string | null;
  enabled?: boolean;
}

export interface Occluder {
  id: string;
  prim: Primitive;
  owner_id?: string | null;
  /** 0 = solid, 1 = fully transparent. The factor a surviving ray is multiplied by. */
  porosity?: number;
}

export interface Terrain {
  x_min: number;
  z_min: number;
  spacing: number;
  nx: number;
  nz: number;
  /** row-major (nz, nx); row 0 is z_min */
  heights: Float32Array;
}

export interface Grid {
  x_min: number;
  x_max: number;
  z_min: number;
  z_max: number;
  spacing: number;
  /** row-major (nz, nx) 1 = in scope; null = every cell */
  mask: Uint8Array | null;
}

export interface CoverageResult {
  ppm: Float32Array;
  count: Uint8Array;
  best_camera: Int16Array;
  eval_y: Float32Array;
  nx: number;
  nz: number;
  grid: Grid;
  kernel_version: string;
}

/** One cell per `spacing` of extent, rounded (types.py _cell_count). */
export function cellCount(extent: number, spacing: number): number {
  if (extent <= 0) return 0;
  return Math.max(Math.round(extent / spacing), 1);
}

export function gridNx(g: Grid): number {
  return cellCount(g.x_max - g.x_min, g.spacing);
}
export function gridNz(g: Grid): number {
  return cellCount(g.z_max - g.z_min, g.spacing);
}

/** Even-odd point-in-polygon, identical to types.rasterise_polygon. */
export function rasterisePolygon(ring: [number, number][], xs: Float64Array, zs: Float64Array): Uint8Array {
  let pts = ring.map(([x, z]) => [x, z] as [number, number]);
  if (pts.length >= 2 && pts[0]![0] === pts[pts.length - 1]![0] && pts[0]![1] === pts[pts.length - 1]![1]) pts = pts.slice(0, -1);
  if (pts.length < 3) throw new Error("a polygon needs at least three distinct vertices");
  const n = xs.length;
  const inside = new Uint8Array(n);
  const m = pts.length;
  for (let k = 0; k < m; k++) {
    const [x1, z1] = pts[k]!;
    const [x2, z2] = pts[(k + 1) % m]!;
    if (z1 === z2) continue;
    for (let i = 0; i < n; i++) {
      const z = zs[i]!;
      const crosses = z1 > z !== z2 > z;
      if (!crosses) continue;
      const xAt = x1 + ((z - z1) * (x2 - x1)) / (z2 - z1);
      if (xs[i]! < xAt) inside[i] = inside[i]! ^ 1;
    }
  }
  return inside;
}

/** Grid.from_facility: extent snapped outwards to whole cells, mask sampled at cell middles. */
export function gridFromFacility(ring: [number, number][], spacing: number, padM = 2.0): Grid {
  const xs = ring.map((p) => p[0]);
  const zs = ring.map((p) => p[1]);
  const x_min = Math.floor((Math.min(...xs) - padM) / spacing) * spacing;
  const z_min = Math.floor((Math.min(...zs) - padM) / spacing) * spacing;
  const x_max = Math.ceil((Math.max(...xs) + padM) / spacing) * spacing;
  const z_max = Math.ceil((Math.max(...zs) + padM) / spacing) * spacing;
  const g: Grid = { x_min, x_max, z_min, z_max, spacing, mask: null };
  const nx = gridNx(g);
  const nz = gridNz(g);
  const cx = new Float64Array(nx * nz);
  const cz = new Float64Array(nx * nz);
  for (let j = 0; j < nz; j++)
    for (let i = 0; i < nx; i++) {
      cx[j * nx + i] = x_min + i * spacing + 0.5 * spacing;
      cz[j * nx + i] = z_min + j * spacing + 0.5 * spacing;
    }
  g.mask = rasterisePolygon(ring, cx, cz);
  return g;
}

export function terrainHeightAt(t: Terrain, x: number, z: number): number {
  const fx = Math.min(Math.max((x - t.x_min) / t.spacing, 0), t.nx - 1);
  const fz = Math.min(Math.max((z - t.z_min) / t.spacing, 0), t.nz - 1);
  const i0 = Math.floor(fx);
  const j0 = Math.floor(fz);
  const i1 = Math.min(i0 + 1, t.nx - 1);
  const j1 = Math.min(j0 + 1, t.nz - 1);
  const tx = fx - i0;
  const tz = fz - j0;
  const h = t.heights;
  const h00 = h[j0 * t.nx + i0]!;
  const h01 = h[j0 * t.nx + i1]!;
  const h10 = h[j1 * t.nx + i0]!;
  const h11 = h[j1 * t.nx + i1]!;
  const top = h00 * (1 - tx) + h01 * tx;
  const bot = h10 * (1 - tx) + h11 * tx;
  return top * (1 - tz) + bot * tz;
}

export function terrainMax(t: Terrain): number {
  let m = -Infinity;
  for (let i = 0; i < t.heights.length; i++) if (t.heights[i]! > m) m = t.heights[i]!;
  return m;
}
