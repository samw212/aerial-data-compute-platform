/* groma_coverage.occluders: ray-versus-primitive, one segment at a time.
 * Segment O + t(T - O); a hit counts for t strictly inside (eps, 1 - eps). */

import type { Occluder, Primitive } from "./types";

export const RAY_EPS_M = 0.02;
const TINY = 1e-12;

interface Box { kind: "box"; cx: number; cy: number; cz: number; hx: number; hy: number; hz: number; c: number; s: number }
interface Cyl { kind: "cyl"; cx: number; cz: number; r: number; y0: number; y1: number }
type Shape = Box | Cyl;

export interface Prepared {
  id: string;
  ownerId: string | null;
  porosity: number;
  solid: boolean;
  transparent: boolean;
  shapes: Shape[];
  yMin: number;
  yMax: number;
  cx: number;
  cz: number;
  radius: number;
}

function boxOf(cx: number, cy: number, cz: number, hx: number, hy: number, hz: number, yaw: number): Box {
  return { kind: "box", cx, cy, cz, hx, hy, hz, c: Math.cos(yaw), s: Math.sin(yaw) };
}

export function prepare(o: Occluder): Prepared {
  const p: Primitive = o.prim;
  const porosity = o.porosity ?? 0;
  let shapes: Shape[];
  let yMin: number, yMax: number, cx: number, cz: number, radius: number;
  if (p.kind === "box") {
    shapes = [boxOf(p.cx, p.cy, p.cz, p.hx, p.hy, p.hz, p.yaw ?? 0)];
    yMin = p.cy - p.hy; yMax = p.cy + p.hy; cx = p.cx; cz = p.cz; radius = Math.hypot(p.hx, p.hz);
  } else if (p.kind === "cylinder") {
    const lo = Math.min(p.y0, p.y1), hi = Math.max(p.y0, p.y1);
    shapes = [{ kind: "cyl", cx: p.cx, cz: p.cz, r: p.r, y0: lo, y1: hi }];
    yMin = lo; yMax = hi; cx = p.cx; cz = p.cz; radius = p.r;
  } else {
    const lo = Math.min(p.y0, p.y1), hi = Math.max(p.y0, p.y1);
    const halfH = 0.5 * (hi - lo), cy = 0.5 * (lo + hi), halfT = 0.5 * p.thickness;
    shapes = [];
    for (let k = 0; k + 1 < p.points.length; k++) {
      const [x1, z1] = p.points[k]!, [x2, z2] = p.points[k + 1]!;
      const dx = x2 - x1, dz = z2 - z1, len = Math.hypot(dx, dz);
      if (len < TINY) continue;
      shapes.push(boxOf(0.5 * (x1 + x2), cy, 0.5 * (z1 + z2), 0.5 * len, halfH, halfT, Math.atan2(-dz, dx)));
    }
    if (!shapes.length) throw new Error("polyline has no segment with non-zero length");
    const xs = p.points.map((q) => q[0]), zs = p.points.map((q) => q[1]);
    cx = 0.5 * (Math.min(...xs) + Math.max(...xs)); cz = 0.5 * (Math.min(...zs) + Math.max(...zs));
    radius = Math.max(...p.points.map(([x, z]) => Math.hypot(x - cx, z - cz))) + halfT;
    yMin = lo; yMax = hi;
  }
  return { id: o.id, ownerId: o.owner_id ?? null, porosity, solid: porosity <= 0, transparent: porosity >= 1, shapes, yMin, yMax, cx, cz, radius };
}

/** (tNear, tFar) of the segment against a shape; empty when tNear > tFar. */
function slab(sh: Shape, ox: number, oy: number, oz: number, dx: number, dy: number, dz: number): [number, number] {
  if (sh.kind === "box") {
    const px = ox - sh.cx, py = oy - sh.cy, pz = oz - sh.cz;
    const lo = [sh.c * px - sh.s * pz, py, sh.s * px + sh.c * pz];
    const ld = [sh.c * dx - sh.s * dz, dy, sh.s * dx + sh.c * dz];
    const half = [sh.hx, sh.hy, sh.hz];
    let tn = -Infinity, tf = Infinity;
    for (let a = 0; a < 3; a++) {
      let d = ld[a]!;
      if (Math.abs(d) < TINY) d = d < 0 ? -TINY : TINY;
      const inv = 1 / d;
      let t1 = (-half[a]! - lo[a]!) * inv, t2 = (half[a]! - lo[a]!) * inv;
      if (t1 > t2) { const t = t1; t1 = t2; t2 = t; }
      if (t1 > tn) tn = t1;
      if (t2 < tf) tf = t2;
    }
    return [tn, tf];
  }
  // cylinder: plan-view circle, then the height band
  const px = ox - sh.cx, pz = oz - sh.cz;
  const a = dx * dx + dz * dz, b = 2 * (px * dx + pz * dz), c = px * px + pz * pz - sh.r * sh.r;
  let tn: number, tf: number;
  if (a > TINY) {
    const disc = b * b - 4 * a * c;
    if (disc < 0) return [Infinity, -Infinity];
    const sq = Math.sqrt(disc);
    tn = (-b - sq) / (2 * a); tf = (-b + sq) / (2 * a);
  } else {
    if (c > 0) return [Infinity, -Infinity];
    tn = -Infinity; tf = Infinity;
  }
  let sdy = dy;
  if (Math.abs(sdy) < TINY) sdy = sdy < 0 ? -TINY : TINY;
  const ta = (sh.y0 - oy) / sdy, tb = (sh.y1 - oy) / sdy;
  const tyn = Math.min(ta, tb), tyf = Math.max(ta, tb);
  return [Math.max(tn, tyn), Math.min(tf, tyf)];
}

/** Broad phase then exact: does the segment to (tx,ty,tz) pass through this occluder? */
export function hits(pre: Prepared, ox: number, oy: number, oz: number, tx: number, ty: number, tz: number, epsT: number): boolean {
  const yLow = Math.min(oy, ty), yHigh = Math.max(oy, ty);
  if (yLow > pre.yMax || yHigh < pre.yMin) return false;
  const abx = tx - ox, abz = tz - oz;
  const len2 = abx * abx + abz * abz;
  const acx = pre.cx - ox, acz = pre.cz - oz;
  let t = len2 > TINY ? (acx * abx + acz * abz) / len2 : 0;
  if (t < 0) t = 0; else if (t > 1) t = 1;
  const px = t * abx - acx, pz = t * abz - acz;
  if (px * px + pz * pz > pre.radius * pre.radius) return false;
  const dx = tx - ox, dy = ty - oy, dz = tz - oz;
  for (const sh of pre.shapes) {
    const [tn, tf] = slab(sh, ox, oy, oz, dx, dy, dz);
    if (tf >= tn && tf > epsT && tn < 1 - epsT) return true;
  }
  return false;
}
