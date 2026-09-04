"""Capture ingest: a directory of images becomes source images and a QA report.

This is the orchestration layer. Every decision it makes lives in one of the modules
beside it, so that each can be tested against an independently derived answer:
`exif` for metadata, `sensors` for dimensions, `quality` for scoring, `overlap` for
geometry, `classify` for the nadir split and `qa` for the gate.

Positions arrive from EXIF as latitude and longitude in degrees, and overlap needs
metres. Rather than depend on a projection library here, which would drag GDAL into
a package that must stay importable everywhere, positions are converted with a local
equirectangular approximation about the flight's own mean latitude. Over the extent
of a single survey, a few hundred metres, that is accurate to well under a percent,
which is far tighter than an overlap estimate that already ignores terrain and tilt.
A caller that has a real projection can inject one.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from groma_capture.classify import classify
from groma_capture.exif import ExifRecord, read_directory
from groma_capture.overlap import Shot, estimate_overlaps
from groma_capture.qa import AssessedImage, apply_gates, build_qa
from groma_capture.quality import (
    DEFAULT_CLIP_LIMIT,
    DEFAULT_SHARPNESS_FLOOR,
    score_file,
    sharpness_threshold,
)
from groma_capture.sensors import SensorTable, resolve_sensor
from groma_contracts.geometry import Vec3
from groma_contracts.imagery import CaptureQA, SensorSpec, SourceImage

EARTH_RADIUS_M = 6_378_137.0
"""WGS 84 semi-major axis, used by the local equirectangular approximation."""

Projector = Callable[[float, float], tuple[float, float]]
"""(lon_deg, lat_deg) -> (x_m, y_m) in the storage CRS."""


def equirectangular(lon: float, lat: float, *, lon0: float, lat0: float) -> tuple[float, float]:
    """Local planar metres about (lon0, lat0). East and north positive."""
    x = math.radians(lon - lon0) * EARTH_RADIUS_M * math.cos(math.radians(lat0))
    y = math.radians(lat - lat0) * EARTH_RADIUS_M
    return x, y


def sha256_file(path: Path | str, *, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


@dataclass(frozen=True)
class IngestResult:
    images: list[SourceImage]
    qa: CaptureQA
    sensor: SensorSpec | None
    sensor_estimated: bool
    estimated_gsd_m: float | None


def _shots(records: list[ExifRecord], projector: Projector | None) -> list[Shot]:
    """Build the overlap input, dropping frames with no position or no altitude."""
    located = [r for r in records if r.gps_lat is not None and r.gps_lon is not None]
    if not located:
        return []
    if projector is None:
        lat0 = sum(r.gps_lat or 0.0 for r in located) / len(located)
        lon0 = sum(r.gps_lon or 0.0 for r in located) / len(located)

        def projector(lon: float, lat: float) -> tuple[float, float]:
            return equirectangular(lon, lat, lon0=lon0, lat0=lat0)

    ordered = sorted(
        located,
        key=lambda r: (r.captured_at is None, r.captured_at or 0, r.filename),
    )
    shots: list[Shot] = []
    for i, r in enumerate(ordered):
        agl = r.relative_altitude_m
        if agl is None or agl <= 0:
            continue
        x, y = projector(r.gps_lon or 0.0, r.gps_lat or 0.0)
        shots.append(
            Shot(x=x, y=y, altitude_agl_m=agl, heading_deg=r.gimbal_yaw_deg, sequence=i)
        )
    return shots


def _gsd(sensor: SensorSpec | None, records: list[ExifRecord]) -> float | None:
    """Median ground sample distance across the flight, metres per pixel."""
    if sensor is None:
        return None
    focals = [r.focal_mm for r in records if r.focal_mm]
    alts = [r.relative_altitude_m for r in records if r.relative_altitude_m]
    if not focals or not alts:
        return None
    focal = sorted(focals)[len(focals) // 2]
    altitude = sorted(alts)[len(alts) // 2]
    if not focal:
        return None
    return sensor.sensor_w_mm * altitude / (focal * sensor.res_x)


def ingest_records(
    records: list[ExifRecord],
    scores: dict[str, tuple[float, float]],
    *,
    survey_id: str,
    georef: str = "none",
    has_scale_bar: bool = False,
    video_sourced: bool = False,
    sensor_table: SensorTable | None = None,
    projector: Projector | None = None,
    sharpness_floor: float = DEFAULT_SHARPNESS_FLOOR,
    clip_limit: float = DEFAULT_CLIP_LIMIT,
    uri_for: Callable[[ExifRecord], str] | None = None,
    sha_for: Callable[[ExifRecord], str] | None = None,
) -> IngestResult:
    """Assemble source images and a QA report from parsed metadata and scores.

    Separated from disk so the whole of the ingest decision can be tested without
    image files: `scores` maps filename to (sharpness, clipped_fraction).
    """
    if not records:
        empty = build_qa([], classify([]), georef=georef, has_scale_bar=has_scale_bar)
        return IngestResult([], empty, None, False, None)

    first = records[0]
    sensor, estimated = resolve_sensor(
        make=first.make,
        model=first.model,
        focal_mm=first.focal_mm,
        focal_35_mm=first.focal_35_mm,
        res_x=first.width,
        res_y=first.height,
        table=sensor_table,
    )

    assessed = [
        AssessedImage(
            filename=r.filename,
            sharpness=scores.get(r.filename, (0.0, 0.0))[0],
            clipped_fraction=scores.get(r.filename, (0.0, 0.0))[1],
            gimbal_pitch_deg=r.gimbal_pitch_deg,
            rtk_fixed=r.rtk_fixed,
        )
        for r in records
    ]
    floor = sharpness_threshold([a.sharpness for a in assessed], floor=sharpness_floor)
    assessed = apply_gates(assessed, sharpness_floor=floor, clip_limit=clip_limit)
    state_by_name = {a.filename: a for a in assessed}

    front = side = None
    if sensor is not None and first.focal_mm:
        front, side = estimate_overlaps(
            _shots(records, projector),
            sensor_w_mm=sensor.sensor_w_mm,
            sensor_h_mm=sensor.sensor_h_mm,
            focal_mm=first.focal_mm,
        )

    gsd = _gsd(sensor, records)
    qa = build_qa(
        assessed,
        classify([r.gimbal_pitch_deg for r in records]),
        front_overlap=front,
        side_overlap=side,
        estimated_gsd_m=gsd,
        sensor_estimated=estimated,
        georef=georef,
        has_scale_bar=has_scale_bar,
        video_sourced=video_sourced,
    )

    images: list[SourceImage] = []
    for r in records:
        a = state_by_name[r.filename]
        images.append(
            SourceImage(
                id=f"{survey_id}:{r.filename}",
                survey_id=survey_id,
                filename=r.filename,
                uri=uri_for(r) if uri_for else r.path,
                sha256=(sha_for(r) if sha_for else "0" * 64),
                width=r.width,
                height=r.height,
                focal_mm=r.focal_mm,
                sensor=sensor,
                captured_at=r.captured_at,
                gps=(
                    Vec3(x=r.gps_lon, y=r.gps_lat, z=r.gps_alt_m or 0.0)
                    if r.gps_lat is not None and r.gps_lon is not None
                    else None
                ),
                gps_accuracy_m=r.gps_accuracy_m,
                rtk_fixed=r.rtk_fixed,
                gimbal_pitch_deg=r.gimbal_pitch_deg,
                gimbal_yaw_deg=r.gimbal_yaw_deg,
                sharpness=a.sharpness,
                clipped_fraction=a.clipped_fraction,
                state=a.state,
            )
        )
    return IngestResult(images, qa, sensor, estimated, gsd)


def ingest_directory(
    directory: Path | str,
    *,
    survey_id: str,
    georef: str = "none",
    has_scale_bar: bool = False,
    sensor_table: SensorTable | None = None,
    projector: Projector | None = None,
    checksums: bool = True,
) -> IngestResult:
    """Read a directory of drone images and produce source images and a QA report."""
    root = Path(directory)
    records = read_directory(root)
    scores: dict[str, tuple[float, float]] = {}
    for r in records:
        try:
            scores[r.filename] = score_file(r.path)
        except Exception:
            scores[r.filename] = (0.0, 1.0)
    return ingest_records(
        records,
        scores,
        survey_id=survey_id,
        georef=georef,
        has_scale_bar=has_scale_bar,
        sensor_table=sensor_table,
        projector=projector,
        uri_for=lambda r: r.path,
        sha_for=(lambda r: sha256_file(r.path)) if checksums else None,
    )


def image_paths(directory: Path | str) -> Iterable[Path]:
    """Every image file under a directory, in a stable order."""
    exts = {".jpg", ".jpeg", ".tif", ".tiff", ".png"}
    return sorted(p for p in Path(directory).rglob("*") if p.suffix.lower() in exts)


__all__ = [
    "EARTH_RADIUS_M",
    "IngestResult",
    "Projector",
    "equirectangular",
    "image_paths",
    "ingest_directory",
    "ingest_records",
    "sha256_file",
]
