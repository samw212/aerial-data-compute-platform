"""The groma command line: coverage over a fixture, migrations, seeding, users."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated

import typer

from groma_contracts.camera import DORI_TIERS_HARDEST_FIRST
from groma_coverage.fixtures import golden_cameras, load_site, site_grid, site_occluders, tent_grid
from groma_coverage.kernel import KERNEL_VERSION, compute_coverage
from groma_coverage.stats import blind_polygons, compare, summarise

app = typer.Typer(add_completion=False, help="ADCP / Groma: drone survey to CCTV coverage.")
users_app = typer.Typer(help="Manage users.")
app.add_typer(users_app, name="users")

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
        f"{len(cameras)} cameras, {len(occluders)} occluders  {elapsed_ms:.0f} ms\n"
    )
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
    typer.echo(f"\n{len(blind_polygons(result, min_area_m2=4.0))} blind region(s) above 4 m2")


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
    before, after = summarise(base, cameras), summarise(with_tents, cameras)
    typer.echo(f"{fixture.name}  kernel {KERNEL_VERSION}")
    typer.echo(f"  blind before {before.blind_pct:6.2f}%   after {after.blind_pct:6.2f}%")
    typer.echo(f"  newly blind  {delta.newly_blind_m2:8.1f} m2")
    typer.echo(f"  newly seen   {delta.newly_covered_m2:8.1f} m2")
    for tier in DORI_TIERS_HARDEST_FIRST:
        typer.echo(f"  {tier.value:10s} {delta.tier_area_delta_m2[tier]:+9.1f} m2")


@app.command()
def migrate() -> None:
    """Apply database migrations (alembic upgrade head)."""
    from alembic import command
    from alembic.config import Config

    from groma_api.settings import get_settings

    cfg = Config(str(Path("migrations/alembic.ini")))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    command.upgrade(cfg, "head")
    typer.echo("migrations applied")


@app.command()
def seed(
    reset: Annotated[bool, typer.Option(help="Drop and recreate the schema first")] = False,
    site: Annotated[Path, typer.Option(help="Authored site fixture")] = DEFAULT_SITE,
    admin_email: Annotated[str, typer.Option(help="First admin account")] = "admin@adcp.local",
    admin_password: Annotated[str | None, typer.Option(help="Leave unset to generate one")] = None,
) -> None:
    """Load site_alpha into the database as a venue, survey, structures and a scenario."""
    from groma_api.db import SessionLocal
    from groma_api.seed import reset_schema
    from groma_api.seed import seed as do_seed

    db = SessionLocal()()
    try:
        if reset:
            reset_schema(db)
        out = do_seed(db, site, admin_email, admin_password)
    finally:
        db.close()
    for k, v in out.items():
        typer.echo(f"{k:16s} {v}")
    typer.echo(
        "\nSign in with the admin email and password above. Change the password after first login."
    )


@users_app.command("add")
def users_add(
    email: str,
    name: str,
    role: str = "viewer",
    password: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Create a user. Roles: viewer | surveyor | admin."""
    import secrets

    from sqlalchemy import select

    from groma_api.auth import hash_password
    from groma_api.db import SessionLocal
    from groma_api.db import models as m

    db = SessionLocal()()
    try:
        org = db.scalar(select(m.Organisation).limit(1))
        if org is None:
            raise typer.BadParameter("no organisation yet; run `groma seed` first")
        if db.scalar(select(m.User).where(m.User.email == email.lower())):
            raise typer.BadParameter("a user with that email exists")
        pw = password or secrets.token_urlsafe(12)
        db.add(
            m.User(
                org_id=org.id,
                email=email.lower(),
                name=name,
                role=role,
                password_hash=hash_password(pw),
            )
        )
        db.commit()
    finally:
        db.close()
    typer.echo(f"created {email} ({role}); password: {pw}")


@users_app.command("passwd")
def users_passwd(email: str, password: Annotated[str | None, typer.Option()] = None) -> None:
    """Reset a user's password."""
    import secrets

    from sqlalchemy import select

    from groma_api.auth import hash_password
    from groma_api.db import SessionLocal
    from groma_api.db import models as m

    db = SessionLocal()()
    try:
        u = db.scalar(select(m.User).where(m.User.email == email.lower()))
        if u is None:
            raise typer.BadParameter("no such user")
        pw = password or secrets.token_urlsafe(12)
        u.password_hash = hash_password(pw)
        db.commit()
    finally:
        db.close()
    typer.echo(f"password for {email}: {pw}")


@users_app.command("role")
def users_role(email: str, role: str) -> None:
    """Change a user's role."""
    from sqlalchemy import select

    from groma_api.db import SessionLocal
    from groma_api.db import models as m

    if role not in ("viewer", "surveyor", "admin"):
        raise typer.BadParameter("role must be viewer, surveyor or admin")
    db = SessionLocal()()
    try:
        u = db.scalar(select(m.User).where(m.User.email == email.lower()))
        if u is None:
            raise typer.BadParameter("no such user")
        u.role = role
        db.commit()
    finally:
        db.close()
    typer.echo(f"{email} is now {role}")


@users_app.command("list")
def users_list() -> None:
    from sqlalchemy import select

    from groma_api.db import SessionLocal
    from groma_api.db import models as m

    db = SessionLocal()()
    try:
        for u in db.scalars(select(m.User).order_by(m.User.email)):
            typer.echo(f"{u.email:36s} {u.role:9s} {u.name}")
    finally:
        db.close()


if __name__ == "__main__":
    app()
