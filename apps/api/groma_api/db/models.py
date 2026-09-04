"""SQLAlchemy models. Build spec 5, with the user table of 19.5.

Geometry columns are PostGIS, in the venue's projected CRS (SRID 0 in the column
definition, as the spec writes it: the SRID is per venue, not per column). The
API layer rebases to the venue origin before anything reaches a float32 or the
renderer (CLAUDE.md, "Coordinate frames").
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Double,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from groma_api.db.base import Base


def new_id() -> uuid.UUID:
    return uuid.uuid4()


class Organisation(Base):
    __tablename__ = "organisation"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    default_srid: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class User(Base):
    __tablename__ = "app_user"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisation.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="viewer")
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Venue(Base):
    __tablename__ = "venue"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisation.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    reference: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    srid: Mapped[int] = mapped_column(Integer, nullable=False)
    origin_x: Mapped[float] = mapped_column(Double, nullable=False)
    origin_y: Mapped[float] = mapped_column(Double, nullable=False)
    origin_z: Mapped[float] = mapped_column(Double, nullable=False)
    height_datum: Mapped[str] = mapped_column(Text, nullable=False)
    boundary = mapped_column(Geometry("POLYGON", srid=0), nullable=True)
    centroid_wgs = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    survey_interval_months: Mapped[int] = mapped_column(Integer, default=24)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    facilities: Mapped[list[Facility]] = relationship(back_populates="venue")

    __table_args__ = (Index("ix_venue_centroid", "centroid_wgs", postgresql_using="gist"),)


class Facility(Base):
    __tablename__ = "facility"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    venue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("venue.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    boundary = mapped_column(Geometry("POLYGON", srid=0), nullable=False)
    nominal_dims: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    target_tier: Mapped[str] = mapped_column(Text, nullable=False, default="detect")
    target_pct: Mapped[float] = mapped_column(Float, nullable=False, default=95.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    venue: Mapped[Venue] = relationship(back_populates="facilities")

    __table_args__ = (Index("ix_facility_boundary", "boundary", postgresql_using="gist"),)


class Survey(Base):
    __tablename__ = "survey"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    venue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("venue.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    flown_at: Mapped[date | None] = mapped_column(Date)
    platform: Mapped[str | None] = mapped_column(Text)
    georef: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    engine: Mapped[str | None] = mapped_column(Text)
    capture_qa: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    qa_acknowledged_by: Mapped[str | None] = mapped_column(Text)
    qa_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accuracy: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    immutable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("survey.id"))
    created_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_survey_venue_flown", "venue_id", "flown_at"),)


class SurveyFacility(Base):
    __tablename__ = "survey_facility"
    survey_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("survey.id", ondelete="CASCADE"), primary_key=True
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facility.id", ondelete="CASCADE"), primary_key=True
    )


class SourceImage(Base):
    __tablename__ = "source_image"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    survey_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("survey.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    uri: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    focal_mm: Mapped[float | None] = mapped_column(Float)
    sensor_w_mm: Mapped[float | None] = mapped_column(Float)
    sensor_h_mm: Mapped[float | None] = mapped_column(Float)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gps = mapped_column(Geometry("POINTZ", srid=0), nullable=True)
    gps_accuracy_m: Mapped[float | None] = mapped_column(Float)
    rtk_fixed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    gimbal_pitch_deg: Mapped[float | None] = mapped_column(Float)
    gimbal_yaw_deg: Mapped[float | None] = mapped_column(Float)
    sharpness: Mapped[float | None] = mapped_column(Float)
    clipped_fraction: Mapped[float | None] = mapped_column(Float)
    state: Mapped[str] = mapped_column(Text, nullable=False, default="accepted")
    source: Mapped[str] = mapped_column(Text, nullable=False, default="still")
    video_frame_index: Mapped[int | None] = mapped_column(Integer)
    pose: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint("survey_id", "filename"),
        Index(
            "ix_source_image_survey_accepted", "survey_id", postgresql_where="state = 'accepted'"
        ),
        Index("ix_source_image_gps", "gps", postgresql_using="gist"),
    )


class Gcp(Base):
    __tablename__ = "gcp"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    survey_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("survey.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    position = mapped_column(Geometry("POINTZ", srid=0), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="control")
    residual_h_m: Mapped[float | None] = mapped_column(Float)
    residual_v_m: Mapped[float | None] = mapped_column(Float)


class GcpObservation(Base):
    __tablename__ = "gcp_observation"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    gcp_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("gcp.id", ondelete="CASCADE"), nullable=False
    )
    image_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_image.id", ondelete="CASCADE"), nullable=False
    )
    px: Mapped[float] = mapped_column(Float, nullable=False)
    py: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (UniqueConstraint("gcp_id", "image_id"),)


class Artefact(Base):
    __tablename__ = "artefact"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    survey_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("survey.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    uri: Mapped[str] = mapped_column(Text, nullable=False)
    bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (UniqueConstraint("survey_id", "kind"),)


class Structure(Base):
    __tablename__ = "structure"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    survey_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("survey.id", ondelete="CASCADE"), nullable=False
    )
    cls: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    reject_reason: Mapped[str | None] = mapped_column(Text)
    primitive: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    """Local ENU metres, Y up, relative to the venue origin."""
    porosity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    mountable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fit_rmse_m: Mapped[float | None] = mapped_column(Float)
    point_count: Mapped[int | None] = mapped_column(Integer)
    view_count: Mapped[int | None] = mapped_column(Integer)
    mean_incidence_deg: Mapped[float | None] = mapped_column(Float)
    accuracy_m: Mapped[float | None] = mapped_column(Float)
    origin: Mapped[str] = mapped_column(Text, nullable=False, default="extracted")
    footprint = mapped_column(Geometry("POLYGONZ", srid=0), nullable=True)
    evidence: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    reviewed_by: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def insufficient_for_mount_design_flag(self) -> bool:
        """Build spec 10.10, mirrored from the contract so the API can refuse."""
        return (self.view_count is not None and self.view_count < 20) or (
            self.accuracy_m is not None and self.accuracy_m > 0.10
        )

    __table_args__ = (
        Index("ix_structure_footprint", "footprint", postgresql_using="gist"),
        Index("ix_structure_survey_accepted", "survey_id", postgresql_where="state = 'accepted'"),
    )


class MountPoint(Base):
    __tablename__ = "mount_point"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    venue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("venue.id", ondelete="CASCADE"), nullable=False
    )
    structure_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("structure.id", ondelete="CASCADE")
    )
    position = mapped_column(Geometry("POINTZ", srid=0), nullable=False)
    normal: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    mounting_type: Mapped[str | None] = mapped_column(Text)
    height_agl_m: Mapped[float] = mapped_column(Float, nullable=False)
    max_load_kg: Mapped[float | None] = mapped_column(Float)
    cable_run_m: Mapped[float | None] = mapped_column(Float)
    accuracy_m: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    label: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_mount_point_venue_accepted", "venue_id", postgresql_where="state = 'accepted'"),
    )


class Scenario(Base):
    __tablename__ = "scenario"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    venue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("venue.id", ondelete="CASCADE"), nullable=False
    )
    facility_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("facility.id"))
    base_survey_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("survey.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    include_seasonal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    cameras: Mapped[list[Camera]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan"
    )
    tents: Mapped[list[Tent]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan"
    )


class Camera(Base):
    __tablename__ = "camera"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenario.id", ondelete="CASCADE"), nullable=False
    )
    mount_point_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("mount_point.id"))
    mount_structure_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("structure.id"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    position = mapped_column(Geometry("POINTZ", srid=0), nullable=False)
    pan_deg: Mapped[float] = mapped_column(Float, nullable=False)
    tilt_deg: Mapped[float] = mapped_column(Float, nullable=False)
    roll_deg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    bracket_offset_m: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sensor_w_mm: Mapped[float] = mapped_column(Float, nullable=False)
    sensor_h_mm: Mapped[float] = mapped_column(Float, nullable=False)
    focal_mm: Mapped[float] = mapped_column(Float, nullable=False)
    res_x: Mapped[int] = mapped_column(Integer, nullable=False)
    res_y: Mapped[int] = mapped_column(Integer, nullable=False)
    near_m: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    far_m: Mapped[float] = mapped_column(Float, nullable=False, default=200.0)
    model_name: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    scenario: Mapped[Scenario] = relationship(back_populates="cameras")


class Tent(Base):
    __tablename__ = "tent"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenario.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    footprint = mapped_column(Geometry("POLYGON", srid=0), nullable=False)
    height_m: Mapped[float] = mapped_column(Float, nullable=False)
    yaw_deg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    scenario: Mapped[Scenario] = relationship(back_populates="tents")


class CoverageRun(Base):
    __tablename__ = "coverage_run"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenario.id", ondelete="CASCADE"), nullable=False
    )
    eval_height_m: Mapped[float] = mapped_column(Float, nullable=False)
    grid_spacing_m: Mapped[float] = mapped_column(Float, nullable=False)
    include_tents: Mapped[bool] = mapped_column(Boolean, nullable=False)
    include_seasonal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    foreshorten: Mapped[bool] = mapped_column(Boolean, nullable=False)
    use_terrain: Mapped[bool] = mapped_column(Boolean, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    kernel_version: Mapped[str] = mapped_column(Text, nullable=False)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    grid_uri: Mapped[str | None] = mapped_column(Text)
    blind_polygons = mapped_column(Geometry("MULTIPOLYGON", srid=0), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[str | None] = mapped_column(Text)


class Measurement(Base):
    __tablename__ = "measurement"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    venue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("venue.id", ondelete="CASCADE"), nullable=False
    )
    survey_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("survey.id"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    geom = mapped_column(Geometry("GEOMETRYZ", srid=0), nullable=False)
    value: Mapped[float] = mapped_column(Double, nullable=False)
    uncertainty: Mapped[float] = mapped_column(Double, nullable=False)
    """Deliberately NOT NULL (CLAUDE.md, Data rules)."""
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    snap_mode: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Job(Base):
    __tablename__ = "job"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stage: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(Text)
    seed: Mapped[int | None] = mapped_column(Integer)
    params: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobLog(Base):
    """Console lines from a job, persisted so the stream survives a reload."""

    __tablename__ = "job_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job.id", ondelete="CASCADE"), nullable=False, index=True
    )
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    line: Mapped[str] = mapped_column(Text, nullable=False)
