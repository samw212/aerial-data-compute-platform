"""The ADCP HTTP service. Build spec 7, 19.

FastAPI over PostGIS. nginx sits in front on the instance and serves the SPA; in
development the SPA is served by Vite. `/api/health` reports what an operator
needs to know first: is the database reachable, is the worker alive, which
versions are running.
"""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from groma_api.db import SessionLocal
from groma_api.routers import (
    auth,
    coverage,
    jobs,
    measurements,
    portfolio,
    scenarios,
    structures,
    surveys,
)
from groma_api.settings import get_settings
from groma_contracts.version import CONTRACTS_VERSION
from groma_coverage.kernel import KERNEL_VERSION

APP_VERSION = os.environ.get("GROMA_VERSION", "0.2.0-dev")


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    settings = get_settings()  # fails fast on a bad environment
    settings.artefact_root.mkdir(parents=True, exist_ok=True)
    app.state.started = time.time()
    yield


app = FastAPI(
    title="ADCP",
    version=APP_VERSION,
    description="Aerial Data Compute Platform: drone survey to CCTV coverage planning.",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

for r in (auth, portfolio, surveys, structures, scenarios, coverage, measurements, jobs):
    app.include_router(r.router)


@app.get("/api/health")
def health() -> JSONResponse:
    settings = get_settings()
    checks: dict[str, Any] = {}
    ok = True
    try:
        db = SessionLocal()()
        try:
            db.execute(text("select 1"))
            queued = db.execute(text("select count(*) from job where status = 'queued'")).scalar()
            running = db.execute(text("select count(*) from job where status = 'running'")).scalar()
            checks["database"] = {"ok": True, "jobs_queued": queued, "jobs_running": running}
        finally:
            db.close()
    except Exception as exc:
        ok = False
        checks["database"] = {"ok": False, "error": str(exc)[:200]}
    try:
        from redis import Redis

        r = Redis.from_url(settings.redis_url, socket_connect_timeout=1)
        r.ping()
        beat = r.get("groma:worker:heartbeat")
        checks["redis"] = {"ok": True}
        last = beat.decode() if isinstance(beat, bytes) else None
        checks["worker"] = {"ok": last is not None, "last_heartbeat": last}
    except Exception as exc:
        checks["redis"] = {"ok": False, "error": str(exc)[:200]}
        checks["worker"] = {"ok": False}
    try:
        import shutil

        usage = shutil.disk_usage(settings.artefact_root)
        checks["disk"] = {
            "ok": usage.free > 5 * 1024**3,
            "free_gb": round(usage.free / 1024**3, 1),
            "total_gb": round(usage.total / 1024**3, 1),
        }
    except Exception as exc:
        checks["disk"] = {"ok": False, "error": str(exc)[:200]}
    body = {
        "status": "ok" if ok else "degraded",
        "version": APP_VERSION,
        "kernel_version": KERNEL_VERSION,
        "contracts_version": CONTRACTS_VERSION,
        "checks": checks,
    }
    return JSONResponse(body, status_code=200 if ok else 503)


@app.get("/api/config")
def config() -> dict[str, Any]:
    """What the browser needs before sign-in: map provider and versions."""
    s = get_settings()
    return {
        "version": APP_VERSION,
        "kernel_version": KERNEL_VERSION,
        "maps": {
            "provider": s.maps_provider,
            "key": s.maps_key if s.maps_provider == "google" else None,
        },
        "default_srid": s.default_srid,
    }


@app.get("/api/kernel")
def kernel_info() -> dict[str, str]:
    return {"kernel_version": KERNEL_VERSION, "contracts_version": CONTRACTS_VERSION}


# ---- static SPA (production: nginx serves it; this is the fallback) -------------

WEB_DIST = Path(os.environ.get("GROMA_WEB_DIST", "apps/web/dist"))
if WEB_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str, request: Request) -> FileResponse:
        target = WEB_DIST / path
        if path and target.is_file():
            return FileResponse(target)
        return FileResponse(WEB_DIST / "index.html")


__all__ = ["app"]
