/* Between local ENU (what the API speaks) and WGS84 (what the basemap speaks).
 * Storage is the venue's projected CRS: E = origin_x + x, N = origin_y - z. */

import proj4 from "proj4";
import type { Venue } from "./api/contracts";

// Hong Kong 1980 Grid System (EPSG:2326).
proj4.defs(
  "EPSG:2326",
  "+proj=tmerc +lat_0=22.3121333333333 +lon_0=114.178555555556 +k=1 +x_0=836694.05 +y_0=819069.8 +ellps=intl +towgs84=-162.619,-276.959,-161.764,0.067753,-2.24365,-1.15883,-1.09425 +units=m +no_defs",
);

export type LngLat = [number, number];

function crs(srid: number): string {
  const key = `EPSG:${srid}`;
  if (!proj4.defs(key)) throw new Error(`no projection definition for ${key}; add it to geo.ts`);
  return key;
}

export function localToLngLat(v: Pick<Venue, "srid" | "origin_x" | "origin_y">, x: number, z: number): LngLat {
  const [lng, lat] = proj4(crs(v.srid), "EPSG:4326", [v.origin_x + x, v.origin_y - z]);
  return [lng!, lat!];
}

export function lngLatToLocal(v: Pick<Venue, "srid" | "origin_x" | "origin_y">, lng: number, lat: number): [number, number] {
  const [e, n] = proj4("EPSG:4326", crs(v.srid), [lng, lat]);
  return [e! - v.origin_x, -(n! - v.origin_y)];
}

export function ringToLngLat(v: Pick<Venue, "srid" | "origin_x" | "origin_y">, ring: [number, number][]): LngLat[] {
  const out = ring.map(([x, z]) => localToLngLat(v, x, z));
  if (out.length && (out[0]![0] !== out[out.length - 1]![0] || out[0]![1] !== out[out.length - 1]![1])) out.push(out[0]!);
  return out;
}

/** Storage (E, N) polygon straight to WGS84 — for boundaries the API returns in storage. */
export function storageRingToLngLat(srid: number, ring: [number, number][]): LngLat[] {
  const out = ring.map(([e, n]) => proj4(crs(srid), "EPSG:4326", [e, n]) as LngLat);
  if (out.length) out.push(out[0]!);
  return out;
}

export function storageRingToLocal(v: Pick<Venue, "origin_x" | "origin_y">, ring: [number, number][]): [number, number][] {
  return ring.map(([e, n]) => [e - v.origin_x, -(n - v.origin_y)]);
}
