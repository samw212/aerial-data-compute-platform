"""Groma contracts: the single source of truth for data shapes.

This package depends on nothing else in Groma. TypeScript types are generated from
it by `make contracts-ts`; never hand-write a duplicate (CLAUDE.md, Architecture).
"""

from groma_contracts.camera import (
    DORI_PX_PER_M,
    DORI_TIERS_HARDEST_FIRST,
    CameraSpec,
    DoriTier,
)
from groma_contracts.coverage import (
    CoverageDelta,
    CoverageRequest,
    CoverageRun,
    CoverageStats,
)
from groma_contracts.geometry import (
    BoxPrim,
    CylinderPrim,
    ExtrudedPolyline,
    Primitive,
    Vec3,
)
from groma_contracts.imagery import CaptureQA, ImageState, SensorSpec, SourceImage
from groma_contracts.jobs import Job, JobKind, JobProgress, JobStatus
from groma_contracts.measurement import (
    Measurement,
    MeasurementKind,
    SnapMode,
    format_measurement,
)
from groma_contracts.scenario import Scenario, Tent
from groma_contracts.site import (
    AuthoredStructure,
    HeightDatum,
    Site,
    SiteFixture,
    SiteOrigin,
)
from groma_contracts.structure import (
    MountPoint,
    RejectReason,
    ReviewState,
    Structure,
    StructureClass,
)
from groma_contracts.survey import (
    AccuracyReport,
    Artefact,
    Gcp,
    GcpObservation,
    GeorefMethod,
    Survey,
    SurveyStatus,
)
from groma_contracts.version import CONTRACTS_VERSION

__all__ = [
    "CONTRACTS_VERSION",
    "DORI_PX_PER_M",
    "DORI_TIERS_HARDEST_FIRST",
    "AccuracyReport",
    "Artefact",
    "AuthoredStructure",
    "BoxPrim",
    "CameraSpec",
    "CaptureQA",
    "CoverageDelta",
    "CoverageRequest",
    "CoverageRun",
    "CoverageStats",
    "CylinderPrim",
    "DoriTier",
    "ExtrudedPolyline",
    "Gcp",
    "GcpObservation",
    "GeorefMethod",
    "HeightDatum",
    "ImageState",
    "Job",
    "JobKind",
    "JobProgress",
    "JobStatus",
    "Measurement",
    "MeasurementKind",
    "MountPoint",
    "Primitive",
    "RejectReason",
    "ReviewState",
    "Scenario",
    "SensorSpec",
    "Site",
    "SiteFixture",
    "SiteOrigin",
    "SnapMode",
    "SourceImage",
    "Structure",
    "StructureClass",
    "Survey",
    "SurveyStatus",
    "Tent",
    "Vec3",
    "format_measurement",
]
