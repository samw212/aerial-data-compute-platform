/* groma_geo.optics, verbatim. The only place the pan/tilt convention is code. */

export function hfovRad(sensorW: number, focal: number): number {
  return 2 * Math.atan(sensorW / (2 * focal));
}
export function vfovRad(sensorH: number, focal: number): number {
  return 2 * Math.atan(sensorH / (2 * focal));
}
export function fPx(focal: number, resY: number, sensorH: number): number {
  return (focal * resY) / sensorH;
}
export function doriRangeM(fpx: number, pxPerM: number): number {
  return fpx / pxPerM;
}

export type Basis = { forward: [number, number, number]; right: [number, number, number]; up: [number, number, number] };

/**
 *   pan   0 deg points along -Z, increasing clockwise viewed from above
 *   tilt  positive = downward
 *   forward = ( sin(pan)*cos(tilt), -sin(tilt), -cos(pan)*cos(tilt) )
 *   right   = normalise( forward x (0,1,0) )
 *   up      = right x forward
 */
export function cameraBasis(panDeg: number, tiltDeg: number): Basis {
  const pan = (panDeg * Math.PI) / 180;
  const tilt = (tiltDeg * Math.PI) / 180;
  const ct = Math.cos(tilt);
  let f: [number, number, number] = [Math.sin(pan) * ct, -Math.sin(tilt), -Math.cos(pan) * ct];
  const fn = Math.hypot(f[0], f[1], f[2]);
  f = [f[0] / fn, f[1] / fn, f[2] / fn];
  // forward x (0,1,0) = (-f.z, 0, f.x)
  let r: [number, number, number] = [-f[2], 0, f[0]];
  let rn = Math.hypot(r[0], r[1], r[2]);
  if (rn < 1e-9) {
    r = [Math.cos(pan), 0, Math.sin(pan)];
    rn = Math.hypot(r[0], r[1], r[2]);
  }
  r = [r[0] / rn, r[1] / rn, r[2] / rn];
  // up = right x forward
  let u: [number, number, number] = [r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]];
  const un = Math.hypot(u[0], u[1], u[2]);
  u = [u[0] / un, u[1] / un, u[2] / un];
  return { forward: f, right: r, up: u };
}
