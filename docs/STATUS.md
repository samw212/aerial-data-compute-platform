# Status

What is built, what is stubbed, and where the next session starts.
Last verified 2026-09-04 (all suites green locally and on the instance).

## Milestones

| | Milestone | State |
| --- | --- | --- |
| M0 | Skeleton | **Done.** Layout, uv workspace, docker-compose, Makefile, ruff/mypy/pytest, CI, contracts complete (§4), TS generation. |
| M1 | Coverage kernel | **Done.** `geo/optics.py`, `coverage/*` including terrain and `reference.py`. T1–T16 pass; benchmark 166 ms against an 800 ms budget. |
| M3 | Web app | **Done for Phase 1.** Viewport-first workbench (`apps/web`): Portfolio, Venue, Capture, Process, Model (Plan / 3D / Review), Plan (live browser kernel, camera drag, run on server), Report (persisted runs, A/B compare), Jobs, Admin. MapLibre on Lands Department tiles; TypeScript kernel with a parity fixture generated from the Python kernel. Playwright e2e and a visual sweep over every stage. |
| M4 | API and database | **Done.** PostGIS schema (`apps/api/groma_api/db/models.py`, Alembic `0001_initial`), auth and roles, the build-spec 7 API for orgs, venues, facilities, surveys, structures, mount points, scenarios, coverage runs, measurements; seed; 15 integration tests against real PostGIS. |
| M5 | Jobs and reporting | **Partial.** `apps/worker` pops jobs from Redis, sweeps the job table, streams progress and console lines over `/ws/jobs/{id}`; fine coverage grids are the one job kind. PDF report and scenario clone are not written (the Report stage's Export PDF is disabled). |
| M15 | Deployment | **Done for Phase 1.** `deploy/autodl/bootstrap.sh` installs PostgreSQL 14 + PostGIS, Redis, nginx, Node 20, the uv env, builds the SPA, migrates, runs every suite, starts five supervisord programs, seeds, installs the nightly backup. `groma-ctl` covers status/health/logs/update/smoke/backup/restore/users/disk/gpu. `docs/OPERATOR-GUIDE.md` is the operator's guide. |
| M2 | Synthetic ground truth | **Next.** `fixtures/sites/site_alpha.json` is authored; `scripts/synthesise_site.py` and `scripts/render_survey.py` are not written. |
| M6–M14, M16 | | Not started. Package skeletons (`capture`, `recon`, `segment`, `tiles`) exist so the import graph is enforced from the start. The ODM Pixi install spike is running on the instance (`/root/autodl-tmp/groma/logs/odm-spike.log`). |

The build order follows `docs/PLAN.md`: Phase 1 (M3, M4, M5, deploy) is what is
here. Phase 2 is M2 + M6.

## What the suites cover

| Command | What | Count |
| --- | --- | --- |
| `make test` | kernel analytic cases T1–T16, contracts, golden, TS generation, parity fixture | 188 in ~1.3 s |
| `make test-integration` | the API against real PostGIS: auth, roles, the 409 gates, immutability, pagination, terrain drop | 15 |
| `make test-web` | TypeScript kernel parity against the Python kernel on three scenes | 7 |
| `make test-e2e` | Playwright: sign-in, portfolio, review by keyboard, live coverage vs the golden, run on server, report, 3D | 4 + a visual sweep of 19 screens with console errors and failed requests asserted empty |
| `make kernel-bench` | 173k cells × 6 cameras × terrain | 166 ms |

## Where things run

- **The AutoDL instance** (`AUTODL.md` has the login line; it changes on every
  restart). nginx on port 6006 serves the SPA and proxies `/api` and `/ws`.
  `groma-ctl status | health | smoke`. The app directory is a git clone of `main`,
  so `groma-ctl update` works.
- **Locally**: `make dev`, `make api`, `make web`, `make seed`. Playwright expects
  the Vite dev server on 5173 and the admin password `local-dev-password`
  (`groma seed --reset --admin-password local-dev-password`).

## Decisions and corrections worth knowing about

### The fixture's compass, corrected 2026-09-04

The compute frame is Y-up and right-handed with X east, so **north is −Z**: pan 0°
points along −Z and `apps/web/src/geo.ts` maps N = origin_y − z. The first
authoring of `site_alpha` placed its "south" structures at negative z, which put the
stand on the north touchline and the "south-west" camera in the north-west on every
map. `scripts/author_site_alpha.py` now mirrors z; names, inventory and camera pans
(derived by `pan_towards`) are unchanged.

The T13 golden moved by less than 0.1 pp (detect 92.24 → 92.32 %, blind 7.75 →
7.66 %) because `Grid.centres()` samples at `x_min + i·h`, the cell's corner rather
than its centre, so a mirror of the site is not a mirror of the sample points. That
is the sampling rule the spec describes (§6.1, "column 0 is x_min") and the kernel
is unchanged (`KERNEL_VERSION` 1.1.0); the golden and the parity fixture were
regenerated together and the movement is recorded here rather than absorbed.

### Map rendering rules learned the hard way

- `line-dasharray` cannot be data-driven in MapLibre; a layer that tries is
  rejected silently and everything in it vanishes. Rejected structures get their own
  dashed layer.
- The default glyph stack (`Open Sans Regular,Arial Unicode MS Regular`) makes the
  OpenMapTiles font server answer with an HTML page, which the PBF parser rejects,
  and every label disappears. `GeoLayer` pins `text-font` to `Open Sans Regular`.
- Polygon labels are placed once per tile the polygon crosses; labels go on a
  centroid point source.
- The map follows a `center` prop until a `bounds` fit takes over, because every
  stage computes its centre from data that arrives after the map is built; and a
  `ResizeObserver` calls `map.resize()` because the dock and strip resize the
  container without a window event.

### Earlier decisions (M0/M1)

- **Porosity is the attenuation factor, not its complement.** §6.4 step 5 says
  `∏(1 − porosity)`; every other statement of the field (§6.1, §4.4, §12.3) defines
  0 = solid, 1 = transparent. The kernel uses `porosity` itself as the factor.
- **The T13 reference table belongs to a fixture that was not supplied.** The
  fixture here is re-authored from explained §4.1; the acceptance criterion is
  regression against the committed golden at ±0.3 pp, and a corroboration test
  records the distance from the spec's table at ±2.5 pp.
- **`docs/design.md` was not supplied**; see `docs/README.md`.
- **Grid cell count** is `extent / spacing` (528 × 328 for 132 × 82 m at 0.25 m).
- **Roll is refused, not ignored**; **terrain march step is in metres**;
  **`blind_polygons` traces cell boundaries**; **optional dependencies are
  per-milestone extras.**

## Deployment notes

- `groma-ctl start postgres redis` used to abort `bootstrap.sh`: supervisorctl's
  status listing exits 3 whenever any program is stopped, and the installer runs
  under `set -e`. Two installs died at that line before it was found.
- `groma-ctl smoke` used an f-string with a backslash, which Python 3.10 (the
  instance's system interpreter) rejects. `backup-install` failed under `pipefail`
  on an empty crontab, and the `cron` package was not in the apt list.
- pytest already has `-q` in `pyproject.toml`; passing it again suppressed the
  "N passed" line the installer greps for.

## Where the next session starts

Phase 2 of `docs/PLAN.md`: M2, `docs/build-spec.md` §16. `scripts/synthesise_site.py`
reads the committed `fixtures/sites/site_alpha.json` and writes a point cloud,
DSM/DTM, ortho with regulation pitch markings, and `truth.json`;
`scripts/render_survey.py` renders the simulated flight and `poses_truth.json`.
Then M6 capture ingest, which makes the Capture stage live.

Also outstanding from Phase 1: the PDF report and scenario clone (M5), and the
ODM spike report (`docs/engine-spike.md`) once the Pixi install on the instance
finishes.

`make test` at the start and end of the session.
