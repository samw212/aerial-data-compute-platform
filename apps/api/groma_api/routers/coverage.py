"""Coverage runs over persisted scenarios. Build spec 6, 7, 15.2.

The occlusion model is `structure WHERE state = 'accepted'` (plus seasonal ones
when the run includes them, plus the scenario's tents). Nothing else. The grid is
the facility polygon plus padding, rasterised to a mask, so every percentage is of
the facility. Every number a report prints comes from the persisted run.
"""

from __future__ import annotations

import math
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from groma_api.db import models as m
from groma_api.deps import DB, Cfg, CurrentUser, Surveyor
from groma_api.geom import (
    multipolygon_to_local,
    multipolygon_to_storage,
    origin_of,
    polygon_to_local,
)
from groma_api.heatmap import colourise, encode_png
from groma_api.routers.portfolio import get_facility, get_venue
from groma_api.routers.scenarios import get_scenario, to_camera
from groma_api.settings import Settings
from groma_contracts.camera import CameraSpec
from groma_contracts.coverage import CoverageDelta, CoverageRun, CoverageStats
from groma_contracts.geometry import BoxPrim, Primitive
from groma_coverage.kernel import KERNEL_VERSION, compute_coverage
from groma_coverage.stats import blind_polygons, compare, summarise
from groma_coverage.types import CoverageResult, Grid, Occluder, Terrain

router = APIRouter(prefix="/api", tags=["coverage"])
_prim: TypeAdapter[Primitive] = TypeAdapter(Primitive)


class RunRequest(BaseModel):
    eval_height_m: float = 1.6
    grid_spacing_m: float = 0.5
    include_tents: bool = True
    include_seasonal: bool | None = None
    """None = the scenario's own setting."""
    foreshorten: bool = True
    use_terrain: bool = True


class CompareRequest(BaseModel):
    run_a: uuid.UUID
    run_b: uuid.UUID


class SceneOut(BaseModel):
    """Everything the browser kernel needs to compute the same run locally."""

    cameras: list[CameraSpec]
    occluders: list[dict[str, Any]]
    grid: dict[str, Any]
    terrain_uri: str | None = None
    kernel_version: str = KERNEL_VERSION


# ---- scene assembly ------------------------------------------------------------


def scenario_occluders(
    db: Session, s: m.Scenario, include_seasonal: bool, include_tents: bool
) -> list[Occluder]:
    states = ["accepted", "seasonal"] if include_seasonal else ["accepted"]
    rows = db.scalars(
        select(m.Structure).where(
            m.Structure.survey_id == s.base_survey_id, m.Structure.state.in_(states)
        )
    )
    out = [
        Occluder(
            id=str(r.id),
            prim=_prim.validate_python(r.primitive),
            owner_id=str(r.id),
            porosity=r.porosity,
        )
        for r in rows
    ]
    if include_tents:
        origin = origin_of(get_venue(db, s.venue_id))
        for t in s.tents:
            out.append(
                Occluder(
                    id=str(t.id),
                    prim=tent_box(polygon_to_local(t.footprint, origin), t.height_m),
                    owner_id=str(t.id),
                )
            )
    return out


def tent_box(ring: list[tuple[float, float]], height_m: float) -> BoxPrim:
    """The minimum-area rotated rectangle of a tent footprint as a solid box.

    Rotating-calipers over the polygon's own edge directions, in NumPy, rather
    than Shapely's oriented_envelope: that emits a divide-by-zero warning on an
    axis-aligned square, which is what every tent in the preset is.
    """
    pts = np.asarray(ring, dtype=np.float64)
    if len(pts) < 3:
        raise ValueError("a tent footprint needs at least three points")
    edges = np.roll(pts, -1, axis=0) - pts
    best: tuple[float, float, float, float, float, float] | None = None
    for ex, ez in edges:
        length = math.hypot(ex, ez)
        if length < 1e-9:
            continue
        # Rotate so this edge lies along +X of the box frame (see occluders._prepare_polyline).
        yaw = math.atan2(-ez, ex)
        c, s_ = math.cos(yaw), math.sin(yaw)
        u = c * pts[:, 0] - s_ * pts[:, 1]
        w = s_ * pts[:, 0] + c * pts[:, 1]
        hx = 0.5 * (u.max() - u.min())
        hz = 0.5 * (w.max() - w.min())
        area = 4.0 * hx * hz
        if best is None or area < best[0]:
            cu, cw = 0.5 * (u.max() + u.min()), 0.5 * (w.max() + w.min())
            # Back to world: inverse rotation.
            cx = c * cu + s_ * cw
            cz = -s_ * cu + c * cw
            best = (area, cx, cz, hx, hz, yaw)
    assert best is not None
    _, cx, cz, hx, hz, yaw = best
    return BoxPrim(
        cx=cx, cy=height_m / 2, cz=cz, hx=max(hx, 0.05), hy=height_m / 2, hz=max(hz, 0.05), yaw=yaw
    )


def scenario_grid(db: Session, s: m.Scenario, spacing: float) -> Grid:
    v = get_venue(db, s.venue_id)
    origin = origin_of(v)
    if s.facility_id is not None:
        ring = polygon_to_local(get_facility(db, s.facility_id).boundary, origin)
    elif v.boundary is not None:
        ring = polygon_to_local(v.boundary, origin)
    else:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "the scenario has no facility and the venue has no boundary; nothing to compute over",
        )
    return Grid.from_facility(ring, spacing)


def scenario_terrain(db: Session, s: m.Scenario, cfg: Settings) -> Terrain | None:
    art = db.scalar(
        select(m.Artefact).where(
            m.Artefact.survey_id == s.base_survey_id, m.Artefact.kind == "terrain_grid"
        )
    )
    if art is None:
        return None
    path = cfg.artefact_root / art.uri
    if not path.exists():
        return None
    with np.load(path) as z:
        return Terrain(
            x_min=float(z["x_min"]),
            z_min=float(z["z_min"]),
            spacing=float(z["spacing"]),
            heights=z["heights"].astype(np.float32),
        )


def scenario_cameras(db: Session, s: m.Scenario) -> list[CameraSpec]:
    origin = origin_of(get_venue(db, s.venue_id))
    return [to_camera(c, origin) for c in sorted(s.cameras, key=lambda c: c.name)]


# ---- persistence ---------------------------------------------------------------


def stats_from_row(row: m.CoverageRun) -> CoverageStats:
    return CoverageStats.model_validate(row.stats)


def to_run(db: Session, row: m.CoverageRun) -> CoverageRun:
    s = get_scenario(db, row.scenario_id)
    origin = origin_of(get_venue(db, s.venue_id))
    return CoverageRun(
        id=str(row.id),
        scenario_id=str(row.scenario_id),
        eval_height_m=row.eval_height_m,
        grid_spacing_m=row.grid_spacing_m,
        include_tents=row.include_tents,
        foreshorten=row.foreshorten,
        use_terrain=row.use_terrain,
        method=row.method,
        kernel_version=row.kernel_version,
        stats=stats_from_row(row),
        include_seasonal=row.include_seasonal,
        grid_uri=row.grid_uri,
        blind_polygons=multipolygon_to_local(row.blind_polygons, origin),
        computed_at=row.computed_at,
        duration_ms=row.duration_ms,
        created_by=row.created_by,
    )


def save_grid(cfg: Settings, run_id: uuid.UUID, result: CoverageResult) -> str:
    rel = f"coverage/{run_id}.npz"
    path = cfg.artefact_root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    g = result.grid
    np.savez_compressed(
        path,
        ppm=result.ppm,
        count=result.count,
        best_camera=result.best_camera,
        eval_y=result.eval_y,
        mask=g.in_scope(),
        x_min=g.x_min,
        x_max=g.x_max,
        z_min=g.z_min,
        z_max=g.z_max,
        spacing=g.spacing,
        kernel_version=result.kernel_version,
    )
    return rel


def load_result(cfg: Settings, row: m.CoverageRun) -> CoverageResult:
    if not row.grid_uri:
        raise HTTPException(404, "this run has no stored grid")
    path = cfg.artefact_root / row.grid_uri
    if not path.exists():
        raise HTTPException(404, "the stored grid is missing from the artefact store")
    with np.load(path) as z:
        grid = Grid(
            x_min=float(z["x_min"]),
            x_max=float(z["x_max"]),
            z_min=float(z["z_min"]),
            z_max=float(z["z_max"]),
            spacing=float(z["spacing"]),
            mask=z["mask"],
        )
        return CoverageResult(
            ppm=z["ppm"],
            count=z["count"],
            best_camera=z["best_camera"],
            eval_y=z["eval_y"],
            grid=grid,
            kernel_version=str(z["kernel_version"]),
        )


def run_scenario(
    db: Session, cfg: Settings, s: m.Scenario, req: RunRequest, user_email: str | None
) -> m.CoverageRun:
    grid = scenario_grid(db, s, req.grid_spacing_m)
    if grid.cells > cfg.kernel_max_cells:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"a {req.grid_spacing_m} m grid over this facility is {grid.cells} cells; "
            f"the limit is {cfg.kernel_max_cells}. Use a coarser spacing.",
        )
    include_seasonal = s.include_seasonal if req.include_seasonal is None else req.include_seasonal
    cameras = scenario_cameras(db, s)
    occluders = scenario_occluders(db, s, include_seasonal, req.include_tents)
    terrain = scenario_terrain(db, s, cfg) if req.use_terrain else None

    start = time.perf_counter()
    result = compute_coverage(cameras, occluders, grid, terrain, req.eval_height_m, req.foreshorten)
    duration_ms = int((time.perf_counter() - start) * 1000)
    stats = summarise(result, cameras)
    rings = blind_polygons(result, min_area_m2=4.0)
    origin = origin_of(get_venue(db, s.venue_id))

    row = m.CoverageRun(
        scenario_id=s.id,
        eval_height_m=req.eval_height_m,
        grid_spacing_m=req.grid_spacing_m,
        include_tents=req.include_tents,
        include_seasonal=include_seasonal,
        foreshorten=req.foreshorten,
        use_terrain=terrain is not None,
        method="raycast",
        kernel_version=KERNEL_VERSION,
        stats=stats.model_dump(mode="json"),
        blind_polygons=multipolygon_to_storage(rings, origin),
        computed_at=datetime.now(UTC),
        duration_ms=duration_ms,
        created_by=user_email,
    )
    db.add(row)
    db.flush()
    row.grid_uri = save_grid(cfg, row.id, result)
    db.commit()
    return row


# ---- routes --------------------------------------------------------------------


@router.get("/scenarios/{scenario_id}/scene", response_model=SceneOut)
def scene(
    scenario_id: uuid.UUID,
    _: CurrentUser,
    db: DB,
    include_seasonal: bool | None = None,
    include_tents: bool = True,
    grid_spacing_m: float = 0.5,
) -> SceneOut:
    """The inputs of a run, in local ENU, for the browser kernel's live preview."""
    s = get_scenario(db, scenario_id)
    seasonal = s.include_seasonal if include_seasonal is None else include_seasonal
    grid = scenario_grid(db, s, grid_spacing_m)
    occ = scenario_occluders(db, s, seasonal, include_tents)
    return SceneOut(
        cameras=scenario_cameras(db, s),
        occluders=[
            {
                "id": o.id,
                "owner_id": o.owner_id,
                "porosity": o.porosity,
                "prim": o.prim.model_dump(mode="json"),
            }
            for o in occ
        ],
        grid={
            "x_min": grid.x_min,
            "x_max": grid.x_max,
            "z_min": grid.z_min,
            "z_max": grid.z_max,
            "spacing": grid.spacing,
            "mask_rle": rle(grid.in_scope()),
        },
    )


def rle(mask: np.ndarray) -> list[int]:
    """Run lengths of a boolean grid, row-major, starting with a False run."""
    flat = mask.ravel().astype(np.int8)
    if flat.size == 0:
        return []
    change = np.flatnonzero(np.diff(flat)) + 1
    bounds = np.concatenate([[0], change, [flat.size]])
    runs = [int(r) for r in np.diff(bounds)]
    return ([0] if flat[0] else []) + runs


@router.post("/scenarios/{scenario_id}/coverage", response_model=CoverageRun, status_code=201)
def run_coverage(
    scenario_id: uuid.UUID, body: RunRequest, user: Surveyor, db: DB, cfg: Cfg
) -> CoverageRun:
    """Synchronous for spacing >= 0.5 m; finer grids are queued as a job (M5)."""
    s = get_scenario(db, scenario_id)
    if body.grid_spacing_m < 0.5:
        from groma_api.routers.jobs import enqueue

        job = enqueue(db, "coverage", ref_id=s.id, params=body.model_dump(), user=user.email)
        raise HTTPException(
            status.HTTP_202_ACCEPTED,
            {"job_id": str(job.id), "message": "queued: fine grids run in the worker"},
        )
    return to_run(db, run_scenario(db, cfg, s, body, user.email))


@router.get("/scenarios/{scenario_id}/coverage-runs", response_model=list[CoverageRun])
def list_runs(scenario_id: uuid.UUID, _: CurrentUser, db: DB) -> list[CoverageRun]:
    get_scenario(db, scenario_id)
    rows = db.scalars(
        select(m.CoverageRun)
        .where(m.CoverageRun.scenario_id == scenario_id)
        .order_by(m.CoverageRun.computed_at.desc())
    )
    return [to_run(db, r) for r in rows]


def get_run(db: Session, run_id: uuid.UUID) -> m.CoverageRun:
    r = db.get(m.CoverageRun, run_id)
    if r is None:
        raise HTTPException(404, "no such coverage run")
    return r


@router.get("/coverage-runs/{run_id}", response_model=CoverageRun)
def read_run(run_id: uuid.UUID, _: CurrentUser, db: DB) -> CoverageRun:
    return to_run(db, get_run(db, run_id))


@router.get("/coverage-runs/{run_id}/grid.npz")
def run_grid(run_id: uuid.UUID, _: CurrentUser, db: DB, cfg: Cfg) -> Response:
    row = get_run(db, run_id)
    path = cfg.artefact_root / (row.grid_uri or "")
    if not row.grid_uri or not path.exists():
        raise HTTPException(404, "no stored grid")
    return Response(
        content=path.read_bytes(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="coverage-{run_id}.npz"'},
    )


@router.get("/coverage-runs/{run_id}/grid.png")
def run_png(
    run_id: uuid.UUID, _: CurrentUser, db: DB, cfg: Cfg, scale: int = Query(default=2, ge=1, le=8)
) -> Response:
    result = load_result(cfg, get_run(db, run_id))
    rgb = colourise(result)
    # Out-of-scope cells are transparent in spirit; paint them the canvas colour.
    rgb[~result.grid.in_scope()] = (14, 17, 22)
    return Response(content=encode_png(rgb, scale=scale), media_type="image/png")


@router.get("/coverage-runs/{run_id}/tiles.json")
def run_tile_meta(run_id: uuid.UUID, _: CurrentUser, db: DB) -> dict[str, Any]:
    """Where the heatmap image sits in local ENU, for draping on the map/scene."""
    row = get_run(db, run_id)
    s = get_scenario(db, row.scenario_id)
    grid = scenario_grid(db, s, row.grid_spacing_m)
    return {
        "x_min": grid.x_min,
        "x_max": grid.x_max,
        "z_min": grid.z_min,
        "z_max": grid.z_max,
        "spacing": grid.spacing,
        "nx": grid.nx,
        "nz": grid.nz,
    }


@router.post("/coverage/compare", response_model=CoverageDelta)
def compare_runs(body: CompareRequest, _: CurrentUser, db: DB, cfg: Cfg) -> CoverageDelta:
    a = load_result(cfg, get_run(db, body.run_a))
    b = load_result(cfg, get_run(db, body.run_b))
    try:
        return compare(a, b, run_a=str(body.run_a), run_b=str(body.run_b))
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/coverage/compare.png")
def compare_png(
    run_a: uuid.UUID,
    run_b: uuid.UUID,
    _: CurrentUser,
    db: DB,
    cfg: Cfg,
    scale: int = Query(default=2, ge=1, le=8),
) -> Response:
    """Delta map: newly blind in red, newly covered in green, unchanged dimmed."""
    a = load_result(cfg, get_run(db, run_a))
    b = load_result(cfg, get_run(db, run_b))
    if a.grid != b.grid:
        raise HTTPException(status.HTTP_409_CONFLICT, "runs are on different grids")
    seen_a, seen_b = a.count > 0, b.count > 0
    rgb = np.full((*a.ppm.shape, 3), (40, 44, 52), dtype=np.uint8)
    rgb[seen_a & seen_b] = (60, 70, 84)
    rgb[seen_a & ~seen_b] = (255, 92, 92)
    rgb[~seen_a & seen_b] = (61, 220, 132)
    rgb[~a.grid.in_scope()] = (14, 17, 22)
    return Response(content=encode_png(rgb, scale=scale), media_type="image/png")


__all__ = [
    "get_run",
    "load_result",
    "router",
    "run_scenario",
    "scenario_cameras",
    "scenario_grid",
    "scenario_occluders",
    "to_run",
]
