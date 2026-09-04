/* The DORI heatmap as pixels. Same palette as apps/api/groma_api/heatmap.py. */

export const DORI_RGB: Record<string, [number, number, number]> = {
  identify: [214, 62, 52],
  recognise: [238, 178, 48],
  observe: [72, 170, 96],
  detect: [64, 118, 196],
  below: [120, 120, 126],
  blind: [38, 38, 42],
};
const THRESH: [string, number][] = [["identify", 250], ["recognise", 125], ["observe", 62], ["detect", 25]];

export function heatmapCanvas(ppm: Float32Array, count: Uint8Array, mask: Uint8Array | null, nx: number, nz: number, alpha = 0.85): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = nx;
  canvas.height = nz;
  const ctx = canvas.getContext("2d")!;
  const img = ctx.createImageData(nx, nz);
  const a = Math.round(alpha * 255);
  for (let k = 0; k < nx * nz; k++) {
    const o = k * 4;
    if (mask && !mask[k]) { img.data[o + 3] = 0; continue; }
    let rgb = DORI_RGB.below!;
    if (count[k] === 0) rgb = DORI_RGB.blind!;
    else for (const [t, th] of THRESH) if (ppm[k]! >= th) { rgb = DORI_RGB[t]!; break; }
    img.data[o] = rgb[0]; img.data[o + 1] = rgb[1]; img.data[o + 2] = rgb[2]; img.data[o + 3] = a;
  }
  ctx.putImageData(img, 0, 0);
  return canvas;
}
