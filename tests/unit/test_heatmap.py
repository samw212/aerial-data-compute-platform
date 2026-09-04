"""The heatmap encoder: a PNG from a coverage grid, with no imaging dependency."""

from __future__ import annotations

import struct
import zlib

import numpy as np

from groma_api.heatmap import BLIND, TIER_RGB, colourise, encode_png
from groma_contracts.camera import DoriTier
from groma_coverage.fixtures import golden_cameras, load_site, site_grid, site_occluders
from groma_coverage.kernel import compute_coverage


def test_png_round_trips_pixel_for_pixel() -> None:
    """Decode our own encoder's output by hand and compare every byte."""
    rgb = np.zeros((3, 4, 3), dtype=np.uint8)
    rgb[0, 0] = (255, 0, 0)
    rgb[2, 3] = (0, 0, 255)
    png = encode_png(rgb)

    # Walk the chunks, pull out IDAT, inflate, strip the filter bytes.
    pos = 8
    idat = b""
    while pos < len(png):
        (length,) = struct.unpack(">I", png[pos : pos + 4])
        kind = png[pos + 4 : pos + 8]
        payload = png[pos + 8 : pos + 8 + length]
        if kind == b"IDAT":
            idat += payload
        pos += 12 + length
    raw = zlib.decompress(idat)
    rows = np.frombuffer(raw, dtype=np.uint8).reshape(3, 1 + 4 * 3)
    assert np.all(rows[:, 0] == 0)
    assert np.array_equal(rows[:, 1:].reshape(3, 4, 3), rgb)


def test_colourise_maps_tiers_and_blind(site_alpha_path) -> None:
    site = load_site(site_alpha_path)
    cams = golden_cameras(site)
    result = compute_coverage(cams, site_occluders(site), site_grid(site, 1.0), None, 1.6, True)
    rgb = colourise(result)

    blind = result.count == 0
    assert np.all(rgb[blind] == BLIND)
    observe = (result.ppm >= 62.0) & (result.ppm < 125.0)
    assert np.any(observe)
    assert np.all(rgb[observe] == TIER_RGB[DoriTier.OBSERVE])
