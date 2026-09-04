"""Capture ingest: EXIF and XMP, quality gating, overlap estimation, the QA gate.

Build spec 8. Everything here runs before reconstruction is permitted; its job is to
refuse a flight that cannot reconstruct, before an operator waits an hour to be told
the same thing by ODM.
"""

from groma_capture.classify import CaptureSplit, classify
from groma_capture.exif import ExifRecord, parse_exiftool_json, read_directory
from groma_capture.ingest import IngestResult, ingest_directory, ingest_records
from groma_capture.overlap import Shot, estimate_overlaps
from groma_capture.qa import AssessedImage, apply_gates, build_qa
from groma_capture.quality import clipped_fraction, laplacian_variance, sharpness_threshold
from groma_capture.sensors import SensorTable, default_table, resolve_sensor

__all__ = [
    "AssessedImage",
    "CaptureSplit",
    "ExifRecord",
    "IngestResult",
    "SensorTable",
    "Shot",
    "apply_gates",
    "build_qa",
    "classify",
    "clipped_fraction",
    "default_table",
    "estimate_overlaps",
    "ingest_directory",
    "ingest_records",
    "laplacian_variance",
    "parse_exiftool_json",
    "read_directory",
    "resolve_sensor",
    "sharpness_threshold",
]
