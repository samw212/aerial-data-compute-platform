"""DORI-coloured heatmap as a PNG, with no imaging dependency.

A PNG is a zlib-compressed byte stream with a few checksummed chunks around it,
which the standard library can produce on its own. Keeping Pillow out of the API
means the deployable service has the same dependency footprint as the kernel.

Row 0 of the coverage grid is z_min, and -Z is north, so row 0 is the top of the
image: the picture is north-up, east-right, the way a site plan is drawn.
"""

from __future__ import annotations

import struct
import zlib

import numpy as np

from groma_contracts.camera import DORI_PX_PER_M, DoriTier
from groma_coverage.types import CoverageResult

# Blind is dark, seen-but-useless is grey, and the four DORI tiers step from
# blue through green and amber to red as the pixel density rises. The palette is
# chosen so that adjacent tiers differ in lightness as well as hue, which keeps
# the map readable when printed in greyscale.
BLIND = (38, 38, 42)
BELOW_DETECT = (120, 120, 126)
TIER_RGB: dict[DoriTier, tuple[int, int, int]] = {
    DoriTier.DETECT: (64, 118, 196),
    DoriTier.OBSERVE: (72, 170, 96),
    DoriTier.RECOGNISE: (238, 178, 48),
    DoriTier.IDENTIFY: (214, 62, 52),
}


def colourise(result: CoverageResult) -> np.ndarray:
    """(nz, nx, 3) uint8 RGB for a coverage result."""
    ppm = result.ppm
    rgb = np.empty((*ppm.shape, 3), dtype=np.uint8)
    rgb[...] = BELOW_DETECT
    rgb[result.count == 0] = BLIND
    # Softest tier first, so each harder tier paints over the one below it.
    for tier in (DoriTier.DETECT, DoriTier.OBSERVE, DoriTier.RECOGNISE, DoriTier.IDENTIFY):
        rgb[ppm >= DORI_PX_PER_M[tier]] = TIER_RGB[tier]
    return rgb


def encode_png(rgb: np.ndarray, scale: int = 1) -> bytes:
    """Encode an (h, w, 3) uint8 array as an 8-bit RGB PNG.

    `scale` repeats each cell as an integer block of pixels so a 264 x 164 grid
    can be served at a size a browser shows legibly, without any resampling that
    would blur the tier boundaries.
    """
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
        raise ValueError("expected an (h, w, 3) uint8 array")
    if scale > 1:
        rgb = np.repeat(np.repeat(rgb, scale, axis=0), scale, axis=1)

    height, width = rgb.shape[:2]
    # One filter byte (0 = None) at the start of every scanline.
    raw = np.concatenate(
        [np.zeros((height, 1), dtype=np.uint8), rgb.reshape(height, width * 3)], axis=1
    ).tobytes()

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", header),
            chunk(b"IDAT", zlib.compress(raw, 6)),
            chunk(b"IEND", b""),
        ]
    )


__all__ = ["BELOW_DETECT", "BLIND", "TIER_RGB", "colourise", "encode_png"]
