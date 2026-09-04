"""Seed the database with site_alpha. `groma seed --reset`. Build spec 17 (M4).

Turns the authored fixture into an organisation, a venue at the fixture origin, a
facility for the pitch, one complete fixture survey whose structures are all
accepted (authored geometry is truth), and a Baseline scenario carrying the four
golden cameras. Running coverage on that scenario reproduces the T13 figures.
"""

from __future__ import annotations

import math
import secrets
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from groma_api.auth import hash_password
from groma_api.db import models as m
from groma_api.geom import point_to_storage, polygon_to_storage
from groma_contracts.site import SiteFixture, SiteOrigin
from groma_coverage.fixtures import golden_cameras, load_site

PITCH_RING = [(-52.5, -34.0), (52.5, -34.0), (52.5, 34.0), (-52.5, 34.0)]


def reset_schema(db: Session) -> None:
    from groma_api.db.base import Base

    db.execute(
        text(
            "DROP SCHEMA public CASCADE; CREATE SCHEMA public; "
            "CREATE EXTENSION IF NOT EXISTS postgis"
        )
    )
    db.commit()
    Base.metadata.create_all(db.get_bind())
    db.execute(
        text("CREATE TABLE IF NOT EXISTS alembic_version (version_num varchar(32) primary key)")
    )
    db.execute(
        text("DELETE FROM alembic_version; INSERT INTO alembic_version VALUES ('0001_initial')")
    )
    db.commit()


def seed(
    db: Session, fixture: Path, admin_email: str, admin_password: str | None = None
) -> dict[str, str]:
    site: SiteFixture = load_site(fixture)
    origin = SiteOrigin(
        srid=site.origin.srid,
        x=site.origin.x,
        y=site.origin.y,
        z=site.origin.z,
        height_datum=site.origin.height_datum,
    )

    org = m.Organisation(name="EMSD MunSD", default_srid=site.srid)
    db.add(org)
    db.flush()

    password = admin_password or secrets.token_urlsafe(12)
    admin = m.User(
        org_id=org.id,
        email=admin_email.lower(),
        name="Administrator",
        role="admin",
        password_hash=hash_password(password),
    )
    db.add(admin)

    # Sha Tin Sports Ground is the WGS84 centroid of Hong Kong Grid (833000, 817000).
    venue = m.Venue(
        org_id=org.id,
        name="Sha Tin Sports Ground",
        reference="SAMPLE-001",
        srid=site.srid,
        origin_x=site.origin.x,
        origin_y=site.origin.y,
        origin_z=site.origin.z,
        height_datum=site.origin.height_datum.value,
        boundary=polygon_to_storage(
            [
                (site.x_min, site.z_min),
                (site.x_max, site.z_min),
                (site.x_max, site.z_max),
                (site.x_min, site.z_max),
            ],
            origin,
        ),
        survey_interval_months=24,
    )
    from geoalchemy2.shape import from_shape
    from shapely.geometry import Point

    venue.centroid_wgs = from_shape(Point(114.2029, 22.3823), srid=4326)
    db.add(venue)
    db.flush()

    pitch = m.Facility(
        venue_id=venue.id,
        name="Main pitch",
        kind="football",
        boundary=polygon_to_storage(PITCH_RING, origin),
        nominal_dims={"length": 105.0, "width": 68.0},
        target_tier="detect",
        target_pct=95.0,
    )
    db.add(pitch)
    db.flush()

    survey = m.Survey(
        venue_id=venue.id,
        name="Survey 2025-11 (synthetic)",
        flown_at=date(2025, 11, 14),
        platform="synthetic",
        georef="gcp",
        status="complete",
        engine="fixture",
        immutable=True,
        created_by=admin.email,
        accuracy={
            "reproj_rmse_px": 0.71,
            "gcp_rmse_h_m": 0.009,
            "gcp_rmse_v_m": 0.016,
            "check_rmse_h_m": 0.021,
            "check_rmse_v_m": 0.034,
            "check_point_count": 3,
            "gsd_m": 0.012,
            "scale_error_pct": 0.08,
            "registered_images": 612,
            "total_images": 618,
        },
        capture_qa={
            "image_count": 618,
            "accepted_count": 612,
            "rejected": {},
            "sharpness_p10": 312.0,
            "estimated_gsd_m": 0.012,
            "estimated_front_overlap": 0.81,
            "estimated_side_overlap": 0.72,
            "nadir_count": 456,
            "oblique_count": 162,
            "rtk_fraction": 0.97,
            "warnings": [],
            "blocking": [],
        },
    )
    db.add(survey)
    db.flush()
    db.add(m.SurveyFacility(survey_id=survey.id, facility_id=pitch.id))

    ids: dict[str, m.Structure] = {}
    now = datetime.now(UTC)
    for s in site.structures:
        row = m.Structure(
            survey_id=survey.id,
            cls=s.cls,
            name=s.name,
            confidence=1.0,
            state="seasonal" if s.seasonal else "accepted",
            primitive=s.primitive.model_dump(mode="json"),
            porosity=s.porosity,
            mountable=s.mountable,
            fit_rmse_m=0.012 if s.cls == "pole" else 0.03,
            point_count=1800 if s.cls == "pole" else 9000,
            view_count=31,
            mean_incidence_deg=33.0,
            accuracy_m=0.04 if s.cls == "pole" else 0.08,
            origin="extracted",
            reviewed_by=admin.email,
            reviewed_at=now,
        )
        db.add(row)
        ids[s.name] = row
    db.flush()

    # Mount points at head - 1 m on every mast (build spec 12.6).
    for s in site.structures:
        if s.cls != "pole" or s.primitive.kind != "cylinder":
            continue
        p = s.primitive
        for k, (dx, dz) in enumerate(((1, 0), (0, 1), (-1, 0), (0, -1))):
            db.add(
                m.MountPoint(
                    venue_id=venue.id,
                    structure_id=ids[s.name].id,
                    position=point_to_storage(
                        _vec(p.cx + dx * p.r, p.y1 - 1.0, p.cz + dz * p.r), origin
                    ),
                    normal={"x": float(dx), "y": 0.0, "z": float(dz)},
                    origin="extracted",
                    mounting_type="pole_clamp",
                    height_agl_m=p.y1 - 1.0,
                    accuracy_m=0.04,
                    confidence=0.95,
                    state="accepted",
                    label=f"{s.name} head {['E', 'S', 'W', 'N'][k]}",
                )
            )

    scenario = m.Scenario(
        venue_id=venue.id,
        facility_id=pitch.id,
        base_survey_id=survey.id,
        name="Baseline · 4 corner masts",
        include_seasonal=True,
        created_by=admin.email,
    )
    db.add(scenario)
    db.flush()
    for cam in golden_cameras(site):
        mast = cam.mount_structure_id
        db.add(
            m.Camera(
                scenario_id=scenario.id,
                mount_structure_id=ids[mast].id if mast else None,
                name=cam.name,
                position=point_to_storage(cam.position, origin),
                pan_deg=cam.pan_deg,
                tilt_deg=cam.tilt_deg,
                roll_deg=0.0,
                bracket_offset_m=cam.bracket_offset_m,
                sensor_w_mm=cam.sensor_w_mm,
                sensor_h_mm=cam.sensor_h_mm,
                focal_mm=cam.focal_mm,
                res_x=cam.res_x,
                res_y=cam.res_y,
                near_m=cam.near_m,
                far_m=cam.far_m,
                model_name='8 mm · 1/2.8" · 4 MP',
                enabled=True,
            )
        )
    db.commit()
    return {
        "org_id": str(org.id),
        "venue_id": str(venue.id),
        "facility_id": str(pitch.id),
        "survey_id": str(survey.id),
        "scenario_id": str(scenario.id),
        "admin_email": admin.email,
        "admin_password": password,
    }


def _vec(x: float, y: float, z: float):  # type: ignore[no-untyped-def]
    from groma_contracts.geometry import Vec3

    return Vec3(x=x, y=y, z=z)


_ = math
