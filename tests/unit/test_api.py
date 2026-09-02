"""The HTTP service. What it serves must be exactly what the kernel computes.

The point of these tests is not that the endpoints respond; it is that the
numbers on the page are the numbers `summarise` produces for the same inputs,
because a service that quietly disagrees with the CLI is how two people end up
in a meeting with two different coverage figures for one site.
"""

from __future__ import annotations

import struct
import zlib

import numpy as np
import pytest
from fastapi.testclient import TestClient

from groma_api.heatmap import BLIND, TIER_RGB, colourise, encode_png
from groma_api.main import app
from groma_contracts.camera import DoriTier
from groma_coverage.fixtures import golden_cameras, load_site, site_grid, site_occluders
from groma_coverage.kernel import KERNEL_VERSION, compute_coverage
from groma_coverage.stats import summarise


@pytest.fixture(scope="module")
def client(site_alpha_path, tmp_path_factory) -> TestClient:
    import os

    os.environ["GROMA_SITE_FIXTURE"] = str(site_alpha_path)
    with TestClient(app) as c:
        yield c


def test_health_reports_the_kernel(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["kernel_version"] == KERNEL_VERSION
    assert body["site"] == "site_alpha"
    assert body["cameras"] == 4


def test_coverage_matches_the_kernel_exactly(client: TestClient, site_alpha_path) -> None:
    """The JSON is `summarise` over `compute_coverage`, nothing more or less."""
    site = load_site(site_alpha_path)
    cams = golden_cameras(site)
    result = compute_coverage(cams, site_occluders(site), site_grid(site, 1.0), None, 1.6, True)
    expected = summarise(result, cams)

    body = client.get("/api/coverage", params={"spacing": 1.0}).json()
    assert body["cells"] == expected.cells
    assert body["blind_m2"] == expected.blind_m2
    for tier in DoriTier:
        assert body["tier_area_m2"][tier.value] == expected.tier_area_m2[tier]
    assert body["per_camera_unique_m2"] == expected.per_camera_unique_m2


def test_tents_change_the_answer(client: TestClient) -> None:
    without = client.get("/api/coverage", params={"spacing": 1.0, "tents": "false"}).json()
    with_tents = client.get("/api/coverage", params={"spacing": 1.0, "tents": "true"}).json()
    assert with_tents["blind_m2"] > without["blind_m2"]


def test_oversized_grid_is_refused(client: TestClient) -> None:
    """A 0.01 m request is 108 million cells. It gets a 422, not a dead worker."""
    r = client.get("/api/coverage", params={"spacing": 0.01})
    assert r.status_code == 422


def test_heatmap_is_a_png_of_the_grid(client: TestClient, site_alpha_path) -> None:
    r = client.get("/api/coverage/heatmap.png", params={"spacing": 1.0, "scale": 2})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    data = r.content
    assert data[:8] == b"\x89PNG\r\n\x1a\n"

    grid = site_grid(load_site(site_alpha_path), 1.0)
    width, height = struct.unpack(">II", data[16:24])
    assert (width, height) == (grid.nx * 2, grid.nz * 2)


def test_index_page_renders(client: TestClient) -> None:
    r = client.get("/", params={"spacing": 1.0})
    assert r.status_code == 200
    assert "heatmap.png" in r.text
    assert "Blind" in r.text


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
