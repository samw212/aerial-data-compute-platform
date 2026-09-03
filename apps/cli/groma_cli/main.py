"""The groma command line.

Only the commands that M0 and M1 can honestly serve are implemented. `seed` needs
a database (M4) and is stubbed with an explicit message rather than a traceback:
a command that fails obscurely is worse than one that says which milestone it
arrives with.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated

import typer

from groma_contracts.camera import DORI_TIERS_HARDEST_FIRST
from groma_coverage.fixtures import (
    golden_cameras,
    load_site,
    site_grid,
    site_occluders,
    tent_grid,
)
from groma_coverage.kernel import KERNEL_VERSION, compute_coverage
from groma_coverage.stats import blind_polygons, compare, summarise

app = typer.Typer(add_completion=False, help="Groma: drone survey to CCTV coverage.")

DEFAULT_SITE = Path("fixtures/sites/site_alpha.json")


@app.command()
def coverage(
    site: Annotated[Path, typer.Option(help="Authored site fixture")] = DEFAULT_SITE,
    spacing: Annotated[float, typer.Option(help="Grid spacing in metres")] = 0.5,
    eval_height: Annotated[float, typer.Option(help="Metres above local terrain")] = 1.6,
    tents: Annotated[bool, typer.Option(help="Erect the 3x4 event tent grid")] = False,
    seasonal: Annotated[bool, typer.Option(help="Include seasonal structures")] = True,
    foreshorten: Annotated[bool, typer.Option(help="Apply foreshortening")] = True,
) -> None:
    """Compute coverage over an authored site and print the statistics."""
    fixture = load_site(site)
    cameras = golden_cameras(fixture)
    occluders = site_occluders(fixture, include_seasonal=seasonal)
    if tents:
        occluders = occluders + tent_grid()
    grid = site_grid(fixture, spacing)

    start = time.perf_counter()
    result = compute_coverage(cameras, occluders, grid, None, eval_height, foreshorten)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    stats = summarise(result, cameras)

    typer.echo(f"{fixture.name}  kernel {KERNEL_VERSION}")
    typer.echo(
        f"{stats.cells} cells at {spacing} m  ({stats.area_m2:.0f} m2)  "
        f"{len(cameras)} cameras, {len(occluders)} occluders  {elapsed_ms:.0f} ms"
    )
    typer.echo("")
    for tier in DORI_TIERS_HARDEST_FIRST:
        typer.echo(
            f"  {tier.value:10s} {stats.tier_pct(tier):6.2f}%  {stats.tier_area_m2[tier]:9.1f} m2"
        )
    typer.echo(f"  {'blind':10s} {stats.blind_pct:6.2f}%  {stats.blind_m2:9.1f} m2")
    typer.echo(
        f"  {'2+ cams':10s} {stats.redundant_2plus_pct:6.2f}%  {stats.redundant_2plus_m2:9.1f} m2"
    )
    typer.echo(f"  mean {stats.mean_ppm:.1f} px/m")

    typer.echo("\nunique area per camera (the number that justifies each one):")
    for camera_id, area in stats.per_camera_unique_m2.items():
        typer.echo(f"  {camera_id:16s} {area:8.1f} m2")

    rings = blind_polygons(result, min_area_m2=4.0)
    typer.echo(f"\n{len(rings)} blind region(s) above 4 m2")


@app.command("compare-tents")
def compare_tents(
    site: Annotated[Path, typer.Option(help="Authored site fixture")] = DEFAULT_SITE,
    spacing: Annotated[float, typer.Option(help="Grid spacing in metres")] = 0.5,
) -> None:
    """Show what erecting the event tents costs, the way a report states it."""
    fixture = load_site(site)
    cameras = golden_cameras(fixture)
    occluders = site_occluders(fixture)
    grid = site_grid(fixture, spacing)

    base = compute_coverage(cameras, occluders, grid, None, 1.6, True)
    with_tents = compute_coverage(cameras, occluders + tent_grid(), grid, None, 1.6, True)
    delta = compare(base, with_tents, run_a="base", run_b="tents")

    before = summarise(base, cameras)
    after = summarise(with_tents, cameras)

    typer.echo(f"{fixture.name}  kernel {KERNEL_VERSION}")
    typer.echo(f"  blind before {before.blind_pct:6.2f}%   after {after.blind_pct:6.2f}%")
    typer.echo(f"  newly blind  {delta.newly_blind_m2:8.1f} m2")
    typer.echo(f"  newly seen   {delta.newly_covered_m2:8.1f} m2")
    for tier in DORI_TIERS_HARDEST_FIRST:
        typer.echo(f"  {tier.value:10s} {delta.tier_area_delta_m2[tier]:+9.1f} m2")


@app.command()
def seed(
    reset: Annotated[bool, typer.Option(help="Drop and recreate the schema")] = False,
) -> None:
    """Load the site_alpha fixture into the dev database. Lands with M4."""
    _ = reset
    typer.echo(
        "seed needs the database layer, which lands with M4 (build spec 17).\n"
        "Until then, `groma coverage` runs the same fixture straight from "
        "fixtures/sites/site_alpha.json."
    )
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
