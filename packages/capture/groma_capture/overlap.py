"""Overlap estimation from GPS positions and optics. Build spec 8.4.

Overlap is estimated, never measured, at this stage: measuring it would mean
matching features, which is reconstruction's job and costs minutes rather than
milliseconds. The estimate exists to stop a flight that cannot possibly reconstruct
before an operator waits an hour to find out.

The model is the flat-ground nadir footprint:

    footprint = 2 * altitude_agl * tan(fov / 2)
    overlap   = 1 - spacing / footprint

Two consequences worth stating, because both make the estimate optimistic:

- Terrain relief is ignored. Ground closer to the camera than the datum has a
  smaller footprint and therefore less overlap than this reports.
- Tilt is ignored. An oblique frame's footprint is a trapezium, not a rectangle.

Optimistic is the right direction for a *warning* threshold and the wrong direction
for a *blocking* one, so the blocking threshold sits well below the warning.
"""

from __future__ import annotations

import itertools
import math
import statistics
from dataclasses import dataclass

from groma_geo.optics import footprint_m, hfov_rad, vfov_rad

DEFAULT_HEADING_TOLERANCE_DEG = 30.0
"""How far two headings may differ and still count as the same flight line."""


@dataclass(frozen=True)
class Shot:
    """The minimum an overlap estimate needs. Positions are metres in the storage CRS."""

    x: float
    y: float
    altitude_agl_m: float
    heading_deg: float | None = None
    sequence: int = 0
    """Capture order. Ties are broken by it when timestamps are absent or equal."""


def _heading_between(a: Shot, b: Shot) -> float:
    """Compass-style bearing from a to b, degrees, 0 = +y, increasing clockwise."""
    return math.degrees(math.atan2(b.x - a.x, b.y - a.y)) % 360.0


def _angular_gap(a: float, b: float) -> float:
    """Smallest absolute difference between two bearings, 0 to 180."""
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _axis_gap(a: float, b: float) -> float:
    """Difference between two bearings treating opposite directions as equal, 0 to 90.

    A lawnmower flight alternates direction on every line, so a line flown at 90
    degrees and the next flown at 270 lie on the same axis and must group together.
    """
    return min(_angular_gap(a, b), 180.0 - _angular_gap(a, b))


def along_track_footprint_m(altitude_agl_m: float, sensor_h_mm: float, focal_mm: float) -> float:
    """Ground length of one frame in the direction of travel.

    Standard mapping practice points the long sensor axis across the track, so the
    along-track dimension is the sensor's short axis and uses the vertical field of
    view. `estimate_overlaps` takes an override for flights that do not.
    """
    return footprint_m(altitude_agl_m, vfov_rad(sensor_h_mm, focal_mm))


def across_track_footprint_m(altitude_agl_m: float, sensor_w_mm: float, focal_mm: float) -> float:
    """Ground width of one frame perpendicular to the direction of travel."""
    return footprint_m(altitude_agl_m, hfov_rad(sensor_w_mm, focal_mm))


def overlap_fraction(spacing_m: float, footprint_m_value: float) -> float:
    """Fraction of a frame that the next frame repeats, clamped to [0, 1].

    Clamped because a spacing wider than the footprint leaves a gap rather than a
    negative overlap, and the QA report should say "0%" rather than "-40%".
    """
    if footprint_m_value <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - spacing_m / footprint_m_value))


def flight_lines(
    shots: list[Shot], tolerance_deg: float = DEFAULT_HEADING_TOLERANCE_DEG
) -> list[list[Shot]]:
    """Split a capture order into runs that share a heading axis.

    A new line starts when the direction of travel turns off the current axis by
    more than the tolerance, which is what the turn at the end of a lawnmower leg
    looks like in the position track.
    """
    ordered = sorted(shots, key=lambda s: s.sequence)
    if len(ordered) < 2:
        return [ordered] if ordered else []
    lines: list[list[Shot]] = [[ordered[0]]]
    axis: float | None = None
    for prev, shot in itertools.pairwise(ordered):
        step = _heading_between(prev, shot)
        if axis is None:
            axis = step
            lines[-1].append(shot)
            continue
        if _axis_gap(step, axis) <= tolerance_deg:
            lines[-1].append(shot)
        else:
            lines.append([shot])
            axis = None
    return lines


def _median_step_m(line: list[Shot]) -> float | None:
    if len(line) < 2:
        return None
    steps = [math.dist((a.x, a.y), (b.x, b.y)) for a, b in itertools.pairwise(line)]
    steps = [s for s in steps if s > 0]
    return statistics.median(steps) if steps else None


def _median_line_spacing_m(lines: list[list[Shot]]) -> float | None:
    """Perpendicular distance between adjacent flight lines.

    Taken as the distance between consecutive line centroids projected onto the
    normal of the flight axis, so that a line flown slightly long does not read as
    wider spacing.
    """
    usable = [ln for ln in lines if ln]
    if len(usable) < 2:
        return None
    axis = None
    for ln in usable:
        if len(ln) >= 2:
            axis = math.radians(_heading_between(ln[0], ln[-1]))
            break
    if axis is None:
        return None
    nx, ny = math.cos(axis), -math.sin(axis)  # unit normal to the flight axis
    centroids = [
        (sum(s.x for s in ln) / len(ln), sum(s.y for s in ln) / len(ln)) for ln in usable
    ]
    offsets = sorted(cx * nx + cy * ny for cx, cy in centroids)
    gaps = [b - a for a, b in itertools.pairwise(offsets) if b - a > 0]
    return statistics.median(gaps) if gaps else None


def estimate_overlaps(
    shots: list[Shot],
    *,
    sensor_w_mm: float,
    sensor_h_mm: float,
    focal_mm: float,
    tolerance_deg: float = DEFAULT_HEADING_TOLERANCE_DEG,
) -> tuple[float | None, float | None]:
    """Return (front_overlap, side_overlap), each 0 to 1, or None when unknowable.

    None means "not enough geometry to say", which the QA report must render as an
    unknown rather than as a zero: a single flight line genuinely has no side
    overlap to report, and reporting 0% would block a valid corridor survey.
    """
    usable = [s for s in shots if s.altitude_agl_m and s.altitude_agl_m > 0]
    if len(usable) < 2 or focal_mm <= 0:
        return None, None
    altitude = statistics.median(s.altitude_agl_m for s in usable)
    along = along_track_footprint_m(altitude, sensor_h_mm, focal_mm)
    across = across_track_footprint_m(altitude, sensor_w_mm, focal_mm)

    lines = flight_lines(usable, tolerance_deg)
    steps = [step for ln in lines if (step := _median_step_m(ln)) is not None]
    front = overlap_fraction(statistics.median(steps), along) if steps else None

    spacing = _median_line_spacing_m(lines)
    side = overlap_fraction(spacing, across) if spacing is not None else None
    return front, side


__all__ = [
    "DEFAULT_HEADING_TOLERANCE_DEG",
    "Shot",
    "across_track_footprint_m",
    "along_track_footprint_m",
    "estimate_overlaps",
    "flight_lines",
    "overlap_fraction",
]
