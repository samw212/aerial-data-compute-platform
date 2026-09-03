"""Recompute the site_alpha golden coverage statistics.

    Never update a golden file to make a test pass without understanding what
    changed. Explain the movement in the commit message first.  -- CLAUDE.md

Run with `make golden`. The output records the kernel version that produced it, so
a golden and the kernel that wrote it can never be silently mismatched.
"""

from __future__ import annotations

import json
from pathlib import Path

from groma_contracts.camera import DORI_TIERS_HARDEST_FIRST
from groma_coverage.fixtures import (
    golden_cameras,
    load_site,
    site_grid,
    site_occluders,
    tent_grid,
)
from groma_coverage.kernel import KERNEL_VERSION, compute_coverage
from groma_coverage.stats import compare, summarise

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE = REPO_ROOT / "fixtures" / "sites" / "site_alpha.json"
GOLDEN = REPO_ROOT / "tests" / "golden" / "site_alpha_coverage.json"

# The T13 parameters, from build spec 6.6: 0.5 m grid, 1.6 m eval, foreshortening
# on, flat terrain, no tents, all structures accepted, four corner-mast cameras.
GRID_SPACING_M = 0.5
EVAL_HEIGHT_M = 1.6


def main() -> None:
    site = load_site(SITE)
    cameras = golden_cameras(site)
    occluders = site_occluders(site, include_seasonal=True)
    grid = site_grid(site, GRID_SPACING_M)

    base = compute_coverage(cameras, occluders, grid, None, EVAL_HEIGHT_M, foreshorten=True)
    base_stats = summarise(base, cameras)

    tents = tent_grid()
    with_tents = compute_coverage(
        cameras, occluders + tents, grid, None, EVAL_HEIGHT_M, foreshorten=True
    )
    tent_stats = summarise(with_tents, cameras)
    delta = compare(base, with_tents, run_a="base", run_b="tents")

    payload = {
        "kernel_version": KERNEL_VERSION,
        "site": site.name,
        "parameters": {
            "grid_spacing_m": GRID_SPACING_M,
            "eval_height_m": EVAL_HEIGHT_M,
            "foreshorten": True,
            "terrain": "flat",
            "include_seasonal": True,
            "cameras": len(cameras),
        },
        "cells": base_stats.cells,
        "area_m2": base_stats.area_m2,
        "base": {
            "tier_pct": {
                tier.value: round(base_stats.tier_pct(tier), 4) for tier in DORI_TIERS_HARDEST_FIRST
            },
            "blind_pct": round(base_stats.blind_pct, 4),
            "redundant_2plus_pct": round(base_stats.redundant_2plus_pct, 4),
            "mean_ppm": round(base_stats.mean_ppm, 4),
            "per_camera_unique_m2": {
                k: round(v, 3) for k, v in base_stats.per_camera_unique_m2.items()
            },
        },
        "with_tents": {
            "tier_pct": {
                tier.value: round(tent_stats.tier_pct(tier), 4) for tier in DORI_TIERS_HARDEST_FIRST
            },
            "blind_pct": round(tent_stats.blind_pct, 4),
            "newly_blind_m2": round(delta.newly_blind_m2, 3),
        },
    }

    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {GOLDEN.relative_to(REPO_ROOT)} (kernel {KERNEL_VERSION})")
    for tier in DORI_TIERS_HARDEST_FIRST:
        print(f"  {tier.value:10s} {base_stats.tier_pct(tier):6.2f}%")
    print(f"  blind      {base_stats.blind_pct:6.2f}%")
    print(f"  2+ cameras {base_stats.redundant_2plus_pct:6.2f}%")
    print(f"  with tents, blind {tent_stats.blind_pct:6.2f}%")


if __name__ == "__main__":
    main()
