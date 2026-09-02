"""The Groma HTTP service.

What this serves today is the M1 coverage kernel over the authored site fixture:
a health endpoint, the kernel version, coverage statistics, and a DORI-coloured
heatmap. It is deliberately stateless and reads no database, because there is no
database until M4. The surface in build-spec 7 (sites, surveys, scenarios,
coverage runs) replaces these routes when that milestone lands; nothing here is
meant to survive it except the heatmap encoder.

Configuration is by environment variable, validated at start-up so a missing or
broken value fails immediately rather than on the first request (build-spec 19.3):

    GROMA_SITE_FIXTURE      path to the authored site JSON
    GROMA_KERNEL_MAX_CELLS  refuse grids larger than this (guards a 0.05 m request)
"""

from __future__ import annotations

import html
import os
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response

from groma_api.heatmap import colourise, encode_png
from groma_contracts.camera import DORI_TIERS_HARDEST_FIRST
from groma_contracts.coverage import CoverageStats
from groma_contracts.site import SiteFixture
from groma_contracts.version import CONTRACTS_VERSION
from groma_coverage.fixtures import (
    golden_cameras,
    load_site,
    site_grid,
    site_occluders,
    tent_grid,
)
from groma_coverage.kernel import KERNEL_VERSION, compute_coverage
from groma_coverage.stats import summarise
from groma_coverage.types import CoverageResult

DEFAULT_FIXTURE = "fixtures/sites/site_alpha.json"
DEFAULT_MAX_CELLS = 2_000_000


@dataclass(frozen=True)
class Settings:
    site_fixture: Path
    kernel_max_cells: int

    @classmethod
    def from_env(cls) -> Settings:
        fixture = Path(os.environ.get("GROMA_SITE_FIXTURE", DEFAULT_FIXTURE))
        if not fixture.is_file():
            raise RuntimeError(
                f"GROMA_SITE_FIXTURE points at {fixture}, which does not exist. Run the "
                "service from the repository root, or set the variable to the fixture's path."
            )
        raw = os.environ.get("GROMA_KERNEL_MAX_CELLS", str(DEFAULT_MAX_CELLS))
        try:
            max_cells = int(raw)
        except ValueError as exc:
            raise RuntimeError(f"GROMA_KERNEL_MAX_CELLS must be an integer, got {raw!r}") from exc
        if max_cells <= 0:
            raise RuntimeError("GROMA_KERNEL_MAX_CELLS must be positive")
        return cls(site_fixture=fixture, kernel_max_cells=max_cells)


@dataclass(frozen=True)
class RunParams:
    spacing: float
    eval_height: float
    tents: bool
    seasonal: bool
    foreshorten: bool


@dataclass
class Run:
    params: RunParams
    result: CoverageResult
    stats: CoverageStats
    duration_ms: float


class Service:
    """The loaded site plus a small cache of recent runs.

    The HTML page requests the statistics and then the image for the same
    parameters; without the cache that is two kernel runs for one page view.
    """

    def __init__(self, settings: Settings, cache_size: int = 16) -> None:
        self.settings = settings
        self.site: SiteFixture = load_site(settings.site_fixture)
        self.cameras = golden_cameras(self.site)
        self._cache: OrderedDict[RunParams, Run] = OrderedDict()
        self._cache_size = cache_size

    def run(self, params: RunParams) -> Run:
        cached = self._cache.get(params)
        if cached is not None:
            self._cache.move_to_end(params)
            return cached

        grid = site_grid(self.site, params.spacing)
        if grid.cells > self.settings.kernel_max_cells:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"a {params.spacing} m grid over this site is {grid.cells} cells; the "
                    f"limit is {self.settings.kernel_max_cells}. Use a coarser spacing."
                ),
            )

        occluders = site_occluders(self.site, include_seasonal=params.seasonal)
        if params.tents:
            occluders = occluders + tent_grid()

        start = time.perf_counter()
        result = compute_coverage(
            self.cameras, occluders, grid, None, params.eval_height, params.foreshorten
        )
        duration_ms = (time.perf_counter() - start) * 1000.0
        run = Run(params, result, summarise(result, self.cameras), duration_ms)

        self._cache[params] = run
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return run


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    app.state.service = Service(Settings.from_env())
    yield


app = FastAPI(
    title="Groma",
    version=KERNEL_VERSION,
    description="Drone photogrammetry to CCTV coverage planning. M1 kernel service.",
    lifespan=lifespan,
)

Spacing = Annotated[float, Query(gt=0.0, le=10.0, description="Grid spacing, metres")]
EvalHeight = Annotated[float, Query(ge=0.0, le=5.0, description="Metres above local terrain")]


def _params(
    spacing: Spacing = 0.5,
    eval_height: EvalHeight = 1.6,
    tents: bool = False,
    seasonal: bool = True,
    foreshorten: bool = True,
) -> RunParams:
    return RunParams(spacing, eval_height, tents, seasonal, foreshorten)


def _service(request: Request) -> Service:
    service: Service = request.app.state.service
    return service


@app.get("/api/health")
def health(request: Request) -> dict[str, Any]:
    service = _service(request)
    return {
        "status": "ok",
        "kernel_version": KERNEL_VERSION,
        "contracts_version": CONTRACTS_VERSION,
        "site": service.site.name,
        "cameras": len(service.cameras),
        "structures": len(service.site.structures),
    }


@app.get("/api/kernel")
def kernel_info() -> dict[str, str]:
    return {"kernel_version": KERNEL_VERSION, "contracts_version": CONTRACTS_VERSION}


def _stats_payload(run: Run) -> dict[str, Any]:
    stats = run.stats
    return {
        "kernel_version": stats.kernel_version,
        "parameters": {
            "grid_spacing_m": run.params.spacing,
            "eval_height_m": run.params.eval_height,
            "include_tents": run.params.tents,
            "include_seasonal": run.params.seasonal,
            "foreshorten": run.params.foreshorten,
        },
        "duration_ms": round(run.duration_ms, 1),
        "cells": stats.cells,
        "area_m2": stats.area_m2,
        "tier_pct": {t.value: round(stats.tier_pct(t), 3) for t in DORI_TIERS_HARDEST_FIRST},
        "tier_area_m2": {t.value: stats.tier_area_m2[t] for t in DORI_TIERS_HARDEST_FIRST},
        "blind_pct": round(stats.blind_pct, 3),
        "blind_m2": stats.blind_m2,
        "below_detect_m2": stats.below_detect_m2,
        "redundant_2plus_pct": round(stats.redundant_2plus_pct, 3),
        "per_camera_unique_m2": stats.per_camera_unique_m2,
        "mean_ppm": round(stats.mean_ppm, 2),
    }


@app.get("/api/coverage")
def coverage(
    request: Request,
    spacing: Spacing = 0.5,
    eval_height: EvalHeight = 1.6,
    tents: bool = False,
    seasonal: bool = True,
    foreshorten: bool = True,
) -> dict[str, Any]:
    run = _service(request).run(_params(spacing, eval_height, tents, seasonal, foreshorten))
    return _stats_payload(run)


@app.get("/api/coverage/heatmap.png")
def heatmap(
    request: Request,
    spacing: Spacing = 0.5,
    eval_height: EvalHeight = 1.6,
    tents: bool = False,
    seasonal: bool = True,
    foreshorten: bool = True,
    scale: Annotated[int, Query(ge=1, le=8)] = 3,
) -> Response:
    run = _service(request).run(_params(spacing, eval_height, tents, seasonal, foreshorten))
    png = encode_png(colourise(run.result), scale=scale)
    return Response(content=png, media_type="image/png")


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    spacing: Spacing = 0.5,
    tents: bool = False,
    seasonal: bool = True,
) -> str:
    service = _service(request)
    run = service.run(_params(spacing, 1.6, tents, seasonal, True))
    stats = run.stats
    query = f"spacing={spacing}&tents={str(tents).lower()}&seasonal={str(seasonal).lower()}"

    rows = "".join(
        f"<tr><td>{t.value.capitalize()} or better</td>"
        f"<td>{stats.tier_pct(t):.1f}%</td><td>{stats.tier_area_m2[t]:,.0f} m²</td></tr>"
        for t in DORI_TIERS_HARDEST_FIRST
    )
    cameras = "".join(
        f"<tr><td>{html.escape(k)}</td><td>{v:,.0f} m²</td></tr>"
        for k, v in stats.per_camera_unique_m2.items()
    )
    toggle_tents = (
        f"?spacing={spacing}&tents={str(not tents).lower()}&seasonal={str(seasonal).lower()}"
    )
    toggle_seasonal = (
        f"?spacing={spacing}&tents={str(tents).lower()}&seasonal={str(not seasonal).lower()}"
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Groma — {html.escape(service.site.name)}</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:2rem;max-width:64rem;color:#222}}
 table{{border-collapse:collapse;margin:.5rem 0 1.5rem}} td{{padding:.2rem .8rem;border-bottom:1px solid #ddd}}
 img{{max-width:100%;border:1px solid #999;image-rendering:pixelated}}
 .legend span{{display:inline-block;padding:.1rem .5rem;margin-right:.4rem;color:#fff;border-radius:3px}}
 a{{color:#1a5fb4}} small{{color:#666}}
</style></head><body>
<h1>Groma — {html.escape(service.site.name)}</h1>
<p>Kernel {KERNEL_VERSION} · {stats.cells:,} cells at {spacing} m · {stats.area_m2:,.0f} m² ·
 computed in {run.duration_ms:.0f} ms ·
 <a href="/api/coverage?{query}">JSON</a> · <a href="/docs">API docs</a></p>
<p>
 <a href="{toggle_tents}">{"Take the event tents down" if tents else "Erect the 3 x 4 event tents"}</a> ·
 <a href="{toggle_seasonal}">{"Winter (no vegetation)" if seasonal else "Summer (vegetation in leaf)"}</a> ·
 spacing <a href="?spacing=1.0&tents={str(tents).lower()}&seasonal={str(seasonal).lower()}">1 m</a>
 <a href="?spacing=0.5&tents={str(tents).lower()}&seasonal={str(seasonal).lower()}">0.5 m</a>
 <a href="?spacing=0.25&tents={str(tents).lower()}&seasonal={str(seasonal).lower()}">0.25 m</a>
</p>
<img src="/api/coverage/heatmap.png?{query}&scale=3" alt="DORI coverage heatmap, north up">
<p class="legend">
 <span style="background:#d63e34">Identify ≥250 px/m</span><span style="background:#eeb230">Recognise ≥125</span>
 <span style="background:#48aa60">Observe ≥62</span><span style="background:#4076c4">Detect ≥25</span>
 <span style="background:#78787e">Seen, below Detect</span><span style="background:#26262a">Blind</span>
</p>
<h2>Coverage</h2>
<table>{rows}
<tr><td>Blind (no sightline)</td><td>{stats.blind_pct:.1f}%</td><td>{stats.blind_m2:,.0f} m²</td></tr>
<tr><td>Seen by two or more cameras</td><td>{stats.redundant_2plus_pct:.1f}%</td><td>{stats.redundant_2plus_m2:,.0f} m²</td></tr>
</table>
<h2>Area only one camera covers</h2>
<small>The number that justifies each camera: what would go dark if it failed.</small>
<table>{cameras}</table>
<small>Targets evaluated 1.6 m above local ground with foreshortening on, per IEC EN 62676-4.
Coverage is computed against reviewed primitives, never against the raw mesh.</small>
</body></html>"""


__all__ = ["Service", "Settings", "app"]
