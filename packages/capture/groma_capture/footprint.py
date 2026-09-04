"""Ground footprints for source images. Build spec 8.4.

The quadrilateral each frame covers on flat ground, used to draw image footprints
and the flight line on the map. Nadir only: an oblique frame's footprint is a
trapezium that runs to the horizon as the tilt approaches level, and drawing that as
a rectangle would be a lie rather than an approximation.

The frame is the storage CRS in metres, x east and y north, and yaw is a compass
bearing: 0 points along +y, increasing clockwise. That matches the gimbal yaw the
aircraft records, and it is *not* the kernel's pan convention, which works in the
Y-up compute frame where north is -Z. The two never meet: footprints are a map
overlay, and the kernel never sees them.
"""

from __future__ import annotations

import math

from groma_geo.optics import hfov_rad, vfov_rad

Corner = tuple[float, float]


def half_extents_m(
    altitude_agl_m: float, sensor_w_mm: float, sensor_h_mm: float, focal_mm: float
) -> tuple[float, float]:
    """Half the across-track width and half the along-track length, in metres."""
    if altitude_agl_m <= 0 or focal_mm <= 0:
        return 0.0, 0.0
    across = altitude_agl_m * math.tan(hfov_rad(sensor_w_mm, focal_mm) / 2.0)
    along = altitude_agl_m * math.tan(vfov_rad(sensor_h_mm, focal_mm) / 2.0)
    return across, along


def footprint_corners(
    x: float,
    y: float,
    *,
    altitude_agl_m: float,
    yaw_deg: float,
    sensor_w_mm: float,
    sensor_h_mm: float,
    focal_mm: float,
) -> list[Corner]:
    """The four ground corners of a nadir frame, anticlockwise from the near left.

    With yaw 0 the frame is axis aligned and the corners are simply the half extents,
    which is what makes this testable without trusting the rotation.
    """
    across, along = half_extents_m(altitude_agl_m, sensor_w_mm, sensor_h_mm, focal_mm)
    if across <= 0 or along <= 0:
        return []
    t = math.radians(yaw_deg)
    forward = (math.sin(t), math.cos(t))
    right = (math.cos(t), -math.sin(t))
    out: list[Corner] = []
    for a, b in ((-across, -along), (across, -along), (across, along), (-across, along)):
        out.append((x + a * right[0] + b * forward[0], y + a * right[1] + b * forward[1]))
    return out


__all__ = ["Corner", "footprint_corners", "half_extents_m"]
