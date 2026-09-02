# Groma

Drone photogrammetry → 3D site model → CCTV coverage planning.

Fly a drone over a sports ground, and end up with a tool where you can click on a
light mast, say "put a 4-megapixel camera here, pointing that way, with this lens",
and see a coloured map of exactly which parts of the site that camera can usefully
see — and how that changes when twelve event tents go up in the middle of the pitch.

## The idea the system rests on

Coverage is never computed against the raw photogrammetric mesh. It is computed
against a small set of fitted primitives — cylinders for masts, thin boxes for fence
runs, boxes for buildings, plus a terrain grid — each of which a person has
explicitly accepted, rejected or reclassified.

That proxy model is the product. The photogrammetry is a cheap way to obtain it. It
is also what makes a coverage map auditable: every dark cell traces to a named,
reviewed object, rather than to "some triangles are there".

## State

**M0 (skeleton) and M1 (coverage kernel) are complete.** The kernel computes
173,184 cells × 6 cameras × 30 occluders + terrain in 505 ms against an 800 ms
budget, and all fourteen specified tests pass. M2 onward is not built; the package
skeletons exist so the dependency graph is enforced from the start.

See [`docs/STATUS.md`](docs/STATUS.md) for the detail, including three places where
the supplied specification contradicts itself and how each was resolved.

## Quick start

```sh
make install          # uv sync --all-extras --dev
make test             # unit + golden suite, under five seconds
make lint             # ruff + mypy strict
make kernel-bench     # the 800 ms performance target

uv run groma coverage                  # coverage over site_alpha
uv run groma coverage --tents          # with the event tents up
uv run groma compare-tents             # what the tents cost
make serve                             # the same, as a web page on http://127.0.0.1:6006
```

To put it on an AutoDL instance, see [`docs/runbook-autodl.md`](docs/runbook-autodl.md).
It is one command on the instance, and the guide assumes no prior experience with
servers or terminals.

`uv run groma coverage` prints:

```
site_alpha  kernel 1.0.0
43296 cells at 0.5 m  (10824 m2)  4 cameras, 14 occluders  91 ms

  identify     0.00%        0.0 m2
  recognise    5.67%      613.8 m2
  observe     37.86%     4098.2 m2
  detect      92.24%     9984.0 m2
  blind        7.75%      838.8 m2
  2+ cams     49.00%     5303.2 m2
  mean 61.4 px/m
```

## Layout

```
packages/contracts   the single source of truth for data shapes; depends on nothing
packages/geo         coordinate frames, height datums, optics
packages/coverage    the kernel: pure NumPy, no I/O, runs in worker, CLI and WASM
packages/capture     M6    packages/recon    M7
packages/tiles       M9    packages/segment  M10
apps/api  M4   apps/worker  M5   apps/cli   apps/web  M3
fixtures/sites/site_alpha.json   the authored proxy model everything is measured against
tests/unit  tests/golden  tests/integration  tests/e2e
```

Dependency direction is `apps/* → packages/* → packages/contracts`, never the
reverse, and it is enforced by a test rather than by convention.

## Documents

[`CLAUDE.md`](CLAUDE.md) holds the conventions to read before changing anything —
the pan/tilt convention in particular, which is the source of most geometry bugs
this system can have. [`docs/`](docs/) holds the build specification and the
first-principles explainer.

## Why the tests look the way they do

This system produces arrays and percentages that look plausible whether or not they
are correct. A coverage assertion like "the array has the right shape and some
non-zero values" passes for nearly every bug the codebase can have.

So every expected value comes from somewhere other than the code under test: from
arithmetic (a wall of height 3 m at 20 m from a camera at 10 m casts a shadow ending
at exactly 24.0 m), from `reference.py` — a deliberately slow, obviously-correct
second implementation — or from a committed golden file. Tests that could pass over
an all-zero array assert first that the scene is live.
