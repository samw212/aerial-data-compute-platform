/* Structures, cameras, tents and masks as GeoJSON in WGS84, from local ENU. */

import type { CameraSpec, Structure } from "../api/contracts";
import { localToLngLat, ringToLngLat, type LngLat } from "../geo";
import { hfovRad } from "../kernel/optics";

type V = { srid: number; origin_x: number; origin_y: number };

export function primitiveRing(p: Structure["primitive"] | { kind: string; [k: string]: unknown }, n = 24): [number, number][] {
  if (p.kind === "cylinder") {
    const c = p as { cx: number; cz: number; r: number };
    return Array.from({ length: n }, (_, k) => [c.cx + c.r * Math.cos((2 * Math.PI * k) / n), c.cz + c.r * Math.sin((2 * Math.PI * k) / n)] as [number, number]);
  }
  if (p.kind === "box") {
    const b = p as { cx: number; cz: number; hx: number; hz: number; yaw?: number };
    const yaw = b.yaw ?? 0;
    const c = Math.cos(yaw), s = Math.sin(yaw);
    return ([[-1, -1], [1, -1], [1, 1], [-1, 1]] as [number, number][]).map(([u, w]) => {
      const lx = u * b.hx, lz = w * b.hz;
      return [b.cx + c * lx + s * lz, b.cz - s * lx + c * lz];
    });
  }
  const pl = p as { points: [number, number][]; thickness: number };
  const t = Math.max(pl.thickness, 0.3) / 2;
  const left: [number, number][] = [], right: [number, number][] = [];
  for (let i = 0; i < pl.points.length; i++) {
    const a = pl.points[Math.max(0, i - 1)]!, b = pl.points[Math.min(pl.points.length - 1, i + 1)]!;
    const dx = b[0] - a[0], dz = b[1] - a[1], len = Math.hypot(dx, dz) || 1;
    const nx = -dz / len, nz = dx / len;
    const [x, z] = pl.points[i]!;
    left.push([x + nx * t, z + nz * t]);
    right.push([x - nx * t, z - nz * t]);
  }
  return [...left, ...right.reverse()];
}

export const STATE_COLOR: Record<string, string> = { accepted: "#5ee7ff", pending: "#98a2b3", rejected: "#ff5c5c", seasonal: "#3ddc84", proposed: "#c084fc" };

export function structuresFC(v: V, structures: Structure[], selected: string | null): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: structures.map((s) => ({
      type: "Feature",
      id: s.id,
      properties: { id: s.id, name: s.name, cls: s.cls, state: s.origin === "manual" && s.name.startsWith("proposed") ? "proposed" : s.state, color: STATE_COLOR[s.origin === "manual" && s.name.startsWith("proposed") ? "proposed" : s.state] ?? "#98a2b3", selected: s.id === selected ? 1 : 0, porous: (s.porosity ?? 0) > 0.5 ? 1 : 0 },
      geometry: { type: "Polygon", coordinates: [ringToLngLat(v, primitiveRing(s.primitive))] },
    })),
  };
}

export function camerasFC(v: V, cameras: CameraSpec[], selected: string | null, frustumM = 60): { points: GeoJSON.FeatureCollection; frusta: GeoJSON.FeatureCollection } {
  const points: GeoJSON.Feature[] = [], frusta: GeoJSON.Feature[] = [];
  for (const c of cameras) {
    const pos = localToLngLat(v, c.position.x, c.position.z);
    points.push({ type: "Feature", id: c.id, properties: { id: c.id, name: c.name, selected: c.id === selected ? 1 : 0, enabled: c.enabled === false ? 0 : 1 }, geometry: { type: "Point", coordinates: pos } });
    const half = hfovRad(c.sensor_w_mm, c.focal_mm) / 2;
    const pan = (c.pan_deg * Math.PI) / 180;
    const pts: LngLat[] = [pos];
    for (const a of [-half, half]) {
      pts.push(localToLngLat(v, c.position.x + frustumM * Math.sin(pan + a), c.position.z - frustumM * Math.cos(pan + a)));
    }
    pts.push(pos);
    frusta.push({ type: "Feature", id: c.id, properties: { id: c.id, selected: c.id === selected ? 1 : 0, enabled: c.enabled === false ? 0 : 1 }, geometry: { type: "Polygon", coordinates: [pts] } });
  }
  return { points: { type: "FeatureCollection", features: points }, frusta: { type: "FeatureCollection", features: frusta } };
}

export function ringsFC(v: V, rings: [number, number][][], props: Record<string, unknown> = {}): GeoJSON.FeatureCollection {
  return { type: "FeatureCollection", features: rings.map((r, i) => ({ type: "Feature", id: i, properties: { ...props }, geometry: { type: "Polygon", coordinates: [ringToLngLat(v, r)] } })) };
}

/** Image corners for a grid extent: row 0 is z_min, which is north, so top-left = (x_min, z_min). */
export function gridCorners(v: V, g: { x_min: number; x_max: number; z_min: number; z_max: number }): [number, number][] {
  return [localToLngLat(v, g.x_min, g.z_min), localToLngLat(v, g.x_max, g.z_min), localToLngLat(v, g.x_max, g.z_max), localToLngLat(v, g.x_min, g.z_max)];
}
