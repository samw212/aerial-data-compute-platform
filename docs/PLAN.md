# ADCP — Delivery Plan  (v3, 2026-09-04 — approved; implementation started)

Aerial Data Compute Platform: drone survey → ODM-style processing → measurable 3D
site model → reviewed structure proxies → CCTV coverage planning. Code name in the
repository: **Groma**.

Plan for taking the system from its current state (M0 skeleton, M1 coverage kernel)
to all milestones, tested to a production standard and deployed on the AutoDL GPU
instance. **Nothing beyond the existing M0/M1 code has been built yet.** This is for
approval; §1 lists the decisions I need from you.

Companion: `FRONTEND-DESIGN.md`. Mockups: the design canvas linked from my message.

What changed from v1: the instance is a new GPU machine (§0), the survey workflow now
mirrors OpenDroneMap/WebODM end to end (Capture → Process → Model → Plan → Report,
with Map, 3D and Review as one Model stage),
reconstruction runs on a native ODM install with NodeODM in front of it, and the
result views integrate Google Maps (basemap, and Photorealistic 3D Tiles as
surroundings). A Gaussian-splat visual layer is added as an optional final milestone.

---

## 0. What exists today (verified 2026-09-04, after your restart)

### The code

GitHub `samw212/aerial-data-compute-platform` (public), `main` at `dd89972`:

| Built | State |
|---|---|
| M0 skeleton | uv workspace, 7 packages + 3 apps, ruff/mypy strict, CI, contracts complete, TS type generation |
| M1 coverage kernel | terrain, porosity, `reference.py`; T1–T16 pass; 188 tests in 3 s; benchmark 505 ms against 800 ms |
| Placeholder service | `apps/api` renders a server-side heatmap page for `site_alpha`; not the frontend |
| Single-service deploy scripts | `deploy/autodl/bootstrap.sh`, `groma-ctl`, supervisord config, beginner runbook |

Not built: `apps/web`, database, migrations, jobs, M2–M15. The `CLAUDE.md` and
`SPEC.md` here are the repo's `CLAUDE.md` and `docs/build-spec.md`, reflowed.

### The AutoDL instance (new machine)

The restart created a **different container in a different region** (`bjb2`, new
host and port in `AUTODL.md`). The previous checkout is gone; the data disk is empty.
Nothing from yesterday's box carries over, which is fine: nothing was deployed there
yet.

| | Measured |
|---|---|
| OS | Ubuntu 22.04.5, x86_64, no systemd (supervisord available), no Docker, user namespaces disabled |
| **GPU** | **NVIDIA GeForce RTX 5090, 32 GB**, driver 595.58, CUDA 13.0 toolkit at `/usr/local/cuda-13.0` |
| CPU / RAM quota | **25 cores** (Xeon Platinum 8470Q), **90 GiB** |
| Disks | system `/` 30 GB (saved with the image), data `/root/autodl-tmp` 50 GB (persists across shutdown, **not** saved with the image) |
| Network | GitHub, PyPI, Ubuntu apt, NodeSource, conda-forge, pixi.sh all reachable via `/etc/network_turbo` |
| Installed | git, curl, miniconda Python 3.12, supervisord. Not installed: Postgres, Redis, nginx, Node, ODM, COLMAP, exiftool, ffmpeg, PDAL |
| apt candidates | postgresql-14 + postgis-3, redis 6, nginx 1.18, colmap 3.7 (CPU), pdal 2.3, ffmpeg 4.4, gdal 3.4 |

Consequences:

1. **ODM can run natively.** Current ODM is built with Pixi (conda-based) and has a
   `prod` environment (CPU) and a `gpu-prod` environment (CUDA 12 SIFT). No Docker is
   needed. NodeODM runs natively on Node 20 and wraps that install, so the spec's
   NodeODM client (§9.2) is used unchanged. This is the primary engine.
2. **The 50 GB data disk is the binding limit**, not compute. ODM intermediates run
   5–10× input size; a 10 GB survey needs 60–100 GB during processing. The plan
   processes on the data disk, keeps only the final artefact set, and lets you enlarge
   the data disk in the AutoDL console when a real survey arrives (`groma-ctl disk`
   tells you what a survey will need before you upload it).
3. **The data disk is not in the saved image.** Backups are part of the deployment.
4. **GPU mode is billed while the instance is on.** Nothing here needs the GPU except
   ODM's CUDA SIFT and the optional Gaussian-splat and semantic-lift stages; the
   platform also runs in no-GPU mode (tested yesterday), so you can switch modes freely.

---

## 1. Decisions I need from you

| # | Decision | Recommendation |
|---|---|---|
| D1 | Local code location | Make this `ADCP/` folder the git checkout of the repository. |
| D2 | Naming | Product name **ADCP** everywhere a user sees it; `groma_*` stays as package and command names. |
| D3 | Reconstruction engine | **ODM (native, Pixi) + NodeODM** as the primary engine, exactly the WebODM stack without Docker. COLMAP kept as the accuracy cross-check and fallback; fixture backend for tests. Validated by an install spike in Phase 1 (§3). |
| D4 | **Maps** | **Decided 2026-09-04: no Google key.** Basemap, imagery and labels come from the Hong Kong Lands Department GeoData Store (free, no key) through MapLibre. Google Maps and the photorealistic 3D city layer are deferred behind the same `MapProvider` interface; CSDI open 3D building models are the keyless alternative to evaluate for surroundings. |
| D5 | Frontend | Viewport-first workbench: the site fills the screen, the pipeline (Capture → Process → Model → Plan → Report) is the navigation, Map + 3D + Review are one stage. Own design language (graphite surfaces, Archivo + DM Mono, one cyan accent). See `FRONTEND-DESIGN.md`. |
| D6 | Users | Single organisation, local accounts, roles `viewer` / `surveyor` / `admin`, one seeded admin. |
| D7 | Gaussian-splat visual layer (M16) | Include as the final, optional milestone: photorealistic 3D of the site rendered in the browser next to the measurable model. It is a visual layer only; coverage never reads it. |
| D8 | Disk | Enlarge the data disk to 100–200 GB in the AutoDL console before the first real survey. Not needed for the synthetic pipeline. |
| D9 | Instance password | Reset it in the AutoDL console after this session; it was pasted into a file. |

---

## 2. Target architecture on the instance

```
Browser ──► nginx :6006  (the one port AutoDL exposes)
              ├── /            React SPA (static)
              ├── /api/…       uvicorn :8000  FastAPI
              ├── /ws/…        uvicorn :8000  WebSocket (job progress, ODM console stream)
              ├── /tiles/…     static artefact store: 3D Tiles, XYZ ortho/DSM tiles, glTF, splats
              └── /odm/…       NodeODM :3000, admin-only proxy (its own status page)

            uvicorn (API)  ──► PostgreSQL 14 + PostGIS 3   :5432 localhost
                           ──► Redis 6                     :6379 localhost
            arq worker     ──► same; runs ingest, reconstruct (via NodeODM), tile,
                               extract, coverage, optimise, report, splat jobs
            NodeODM :3000  ──► ODM (Pixi env, gpu-prod)  ──► CUDA SIFT on the RTX 5090
            supervisord keeps all seven programs up
```

| Path | Holds |
|---|---|
| `/root/autodl-tmp/groma/app` | repository + `.venv` |
| `/root/autodl-tmp/groma/odm` | ODM checkout + Pixi environment; NodeODM |
| `/root/autodl-tmp/groma/data/pg` | PostgreSQL data |
| `/root/autodl-tmp/groma/artefacts/<survey>` | uploads, ODM outputs, tiles, reports |
| `/root/autodl-tmp/groma/backups` | nightly `pg_dump` + artefact manifest |
| `/root/autodl-tmp/groma/logs` | one rotated log per program |
| `/etc/groma.env` | settings and secrets, root-only, validated at start-up |

Third-party services: Lands Department GeoData Store tiles (browser-side, no key). No
other external dependency at run time.

---

## 3. Build order

Five phases plus one optional. Every phase ends **deployed on the instance and
smoke-tested through the browser**.

### Phase 1 — Frontend shell, platform core, engine spike   (M3, M4, M5, deploy v2)

1. `apps/web`: the viewport shell (top bar with the stage stepper, tool rail, layer
   chips, dock, strip, HUD), Portfolio on the Google venue map, the unified scene with
   Plan ⇄ 3D view modes, the TS kernel and parity test, the Plan stage. Map provider
   abstraction with Google and fallback basemaps.
2. `apps/api`: Alembic `0001_initial`, models, auth and roles, portfolio / venue /
   facility / scenario / camera / tent / coverage / measurement endpoints, seed.
3. Jobs: arq + Redis, WebSocket progress, persisted `coverage_run`, clone and
   compare, PDF report.
4. Deploy v2: Postgres/PostGIS, Redis, nginx, Node 20, supervisord for all programs,
   `groma-ctl` with `backup / restore / smoke / users / disk / gpu`; operator guide.
5. **ODM install spike** (runs on the box in parallel): Pixi install of ODM at a pinned
   commit in `gpu-prod`, NodeODM natively, process the ODM sample dataset, record
   timings and disk use. Outcome decides whether Phase 3 uses `gpu-prod` or `prod`.

Done when: M3–M5 criteria pass; SPA served on 6006; `groma-ctl smoke` passes; the
spike report is in `docs/engine-spike.md`.

### Phase 2 — Synthetic ground truth and capture ingest   (M2, M6)

Synthesised point cloud / DSM / DTM / ortho / `truth.json`; rendered flight with
`poses_truth.json`; upload, EXIF/XMP, `sensors.yaml`, quality scoring, overlap,
video keyframes, QA gate. Frontend: **Capture stage live** — footprints stacked over the
basemap, flight line, gallery strip, QA dock, GCP marking in Photo view.

### Phase 3 — Reconstruction, georeferencing, tiling   (M7, M8, M9)

`ReconstructionBackend` with fixture, NodeODM and COLMAP; re-attach on restart;
artefact validation; GCP marking UI; RTK path; check-point residuals; scale check;
acceptance gates; 3D Tiles / glTF / terrain grid / XYZ tiling. Frontend:
**Process stage** (live ODM console, stages, gates, assets) and the **Model stage**
layers (ortho, DSM, DTM, contours, point cloud, mesh, shots, Photo view, Google
Photorealistic 3D Tiles surroundings).

### Phase 4 — Extraction, review, measurement   (M10, M11, M12)

Segmentation pipeline, review UI with evidence crops, camera-drag mount placement,
proposed masts, measurement with uncertainty. Frontend: the Model stage's **Structures** and
**Measure** tabs, evidence strip, mount points.

### Phase 5 — Optimisation, semantic lift, hardening   (M14, M13, M15 final)

Greedy optimiser; YOLO-seg semantic lift on the GPU; runbook entries each tested by
causing the failure; backup restore drill; soak test with a 1,000-image survey.

### Phase 6 (optional) — Visual fidelity layer   (M16)

Gaussian splatting (gsplat / nerfstudio) trained from the ODM poses on the RTX 5090;
`.ply`/`.splat` artefact streamed into the 3D tab as a toggleable layer. Coverage
never reads it; it is for the reader of the report.

### Effort

| Phase | Sessions | Notes |
|---|---|---|
| 1 | 5–6 | includes the ODM spike (mostly machine time) |
| 2 | 2–3 | |
| 3 | 4–5 | first real ODM runs; disk enlargement before real data |
| 4 | 3–4 | |
| 5 | 2–3 | |
| 6 | 1–2 | optional |

---

## 4. Quality bar

| Area | Standard | Check |
|---|---|---|
| Correctness | expected values independent of the code (§18); kernel parity Python↔TS; golden ±0.3 pp | `make test` < 5 s; `make test-all` with real PostGIS; CI on every push |
| Types and lint | ruff, mypy strict, tsc strict, eslint; secret scan | `make lint`; CI blocks merge |
| API | every endpoint integration-tested; the 409 gates; keyset pagination at 5 000 rows | `tests/integration` |
| Engine | NodeODM client tested against a recorded mock; real ODM run on the rendered synthetic set recovers poses within 3× GSD; empty-output rejection tested with a truncated LAZ | `tests/integration`, spike report |
| Frontend | Playwright e2e over upload → QA → process (fixture) → map → 3D → review → plan → PDF; browser kernel parity; map provider fallback tested with the key absent | `tests/e2e` |
| Jobs | restart mid-job re-attaches to the NodeODM task; cancel; monotonic progress | `test_jobs.py` |
| Security | DB/Redis/NodeODM localhost-only; auth on every mutating route; role checks; uploads validated, never executed; Google key referrer-restricted and never in the repo; secrets in root-only `/etc/groma.env` | auth tests, lint |
| Reproducibility | seed, `kernel_version`, engine version, ODM options and commit recorded per job | schema + tests |
| Deployment | idempotent installer; health checks DB, Redis, worker, NodeODM, GPU; `groma-ctl smoke` end to end through nginx | every deploy |
| Data safety | nightly backups; restore drilled; surveys immutable once complete; disk pre-check before processing | Phase 5 drill |
| Observability | JSON logs with request ids; per-program rotated logs; ODM console captured per task; `/api/health` with versions, queue depth, disk and GPU | operator guide |
| Performance | coverage 173k cells < 800 ms; planner drag < 100 ms preview; 3D tab first frame < 3 s on the synthetic cloud; initial bundle < 1.5 MB gzip | benchmarks in CI, Lighthouse in e2e |

Branching: `claude/<phase>` → PR → green CI → `groma-ctl update` deploys `main`.
Tags `v0.<phase>.<n>`, shown in the health endpoint and every PDF.

---

## 5. Operating the system (deliverables for you)

- **`docs/OPERATOR-GUIDE.md`** — for someone with no server background: connecting
  from Mac and Windows, the AutoDL console (start / stop / GPU vs no-GPU mode /
  enlarging the data disk / custom-service link / resetting the password / what the
  disks are), the `groma-ctl` commands, reading logs, updating, backup and restore,
  users, disk and GPU checks, what to do when the SSH line changes, a one-page
  cheat-sheet.
- **`docs/runbook-autodl.md`** — symptom → diagnosis → fix for every §19.4 entry
  plus ODM-specific ones (task stuck in `opensfm`, disk full mid-task, NodeODM down,
  GPU not detected after a mode switch), each tested by causing the failure.

```
groma-ctl status | health | logs [program] | follow [program]
groma-ctl start | stop | restart [program]
groma-ctl update              fetch main, migrate, build, test, restart, smoke
groma-ctl smoke               end-to-end check through nginx
groma-ctl backup | restore <file>
groma-ctl users add|passwd|role
groma-ctl disk [survey-size]  free space and what a survey of that size needs
groma-ctl gpu                 what ODM will use
groma-ctl odm status|log <task>
```

---

## 6. Risks

| Risk | Handling |
|---|---|
| ODM Pixi install on Ubuntu 22.04 fails or CUDA 12 SIFT does not run on the RTX 5090 (Blackwell) | Phase 1 spike settles it early; `prod` (CPU SIFT on 25 cores) is the fallback and is still fast; COLMAP fallback exists |
| 50 GB data disk | disk pre-check; keep final artefacts only; enlarge before real data (D8) |
| New instance on every restart from a saved image | installer is one command; backups restore the database and artefacts; guide covers it |
| Lands Department tile service availability or terms change | provider interface; OpenStreetMap raster as a second keyless fallback; our own layers do not depend on the basemap |
| Data disk not in the saved image | nightly backups; restore drilled |
| No systemd, no Docker | supervisord for everything; native ODM |
| Kernel parity drift | CI parity test; source-hash test forces a `KERNEL_VERSION` bump |
| Spec ambiguities already resolved in M1 | kept as documented in `docs/STATUS.md` |
