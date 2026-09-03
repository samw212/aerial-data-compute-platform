"""Camera optics and the camera basis. Build spec 6.2.

Pure functions over scalars and NumPy arrays. This module and `camera_basis` below
are the only place the pan/tilt convention appears as code; everything else calls
it. See CLAUDE.md, "Pan and tilt".
"""

from __future__ import annotations

import math

import numpy as np


def hfov_rad(sensor_w_mm: float, focal_mm: float) -> float:
    """Horizontal field of view in radians."""
    return 2.0 * math.atan(sensor_w_mm / (2.0 * focal_mm))


def vfov_rad(sensor_h_mm: float, focal_mm: float) -> float:
    """Vertical field of view in radians."""
    return 2.0 * math.atan(sensor_h_mm / (2.0 * focal_mm))


def f_px(focal_mm: float, res_y: int, sensor_h_mm: float) -> float:
    """Focal length in pixels.

    This is the constant that turns a distance into a pixel density:
    px/m = f_px / d, before foreshortening. T1 asserts the identity
    f_px == res_y / (2 * tan(vfov/2)), which is the same quantity derived through
    the field of view instead of through the sensor dimension.
    """
    return focal_mm * res_y / sensor_h_mm


def gsd_m(sensor_w_mm: float, altitude_m: float, focal_mm: float, res_x: int) -> float:
    """Ground sample distance: metres on the ground per pixel, looking straight down."""
    return sensor_w_mm * altitude_m / (focal_mm * res_x)


def dori_range_m(f_px_value: float, px_per_m: float) -> float:
    """The distance at which a camera still delivers `px_per_m`.

    Foreshortening is not applied here: this is the on-axis range, which is what a
    camera schedule quotes.
    """
    return f_px_value / px_per_m


def footprint_m(altitude_m: float, fov_rad: float) -> float:
    """Ground footprint of one image dimension, nadir, over flat ground."""
    return 2.0 * altitude_m * math.tan(fov_rad / 2.0)


def camera_basis(pan_deg: float, tilt_deg: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (forward, right, up) unit vectors for a pan/tilt pair.

        pan   0 deg points along -Z, increasing clockwise viewed from above
        tilt  positive = downward

        forward = ( sin(pan)*cos(tilt), -sin(tilt), -cos(pan)*cos(tilt) )
        right   = normalise( forward x (0,1,0) )
        up      = right x forward

    Roll is not applied. Roll rotates the frustum about `forward`, which changes
    which cells fall inside a rectangular frustum but not the distance to any of
    them; the kernel's frustum test would need it, and does not yet support it.
    CameraSpec.roll_deg is carried through to the renderer and reports, and the
    kernel asserts it is zero rather than silently ignoring it.

    At tilt = +/-90 degrees (straight down or straight up) `forward` is parallel to
    (0,1,0) and the cross product degenerates. The convention there is that `right`
    stays with the pan direction, which is what a pan/tilt head physically does.
    """
    pan = math.radians(pan_deg)
    tilt = math.radians(tilt_deg)
    cos_tilt = math.cos(tilt)

    forward = np.array(
        [
            math.sin(pan) * cos_tilt,
            -math.sin(tilt),
            -math.cos(pan) * cos_tilt,
        ],
        dtype=np.float64,
    )
    forward /= np.linalg.norm(forward)

    world_up = np.array([0.0, 1.0, 0.0])
    right = np.cross(forward, world_up)
    norm = float(np.linalg.norm(right))
    if norm < 1e-9:
        # Looking straight down or straight up. Keep `right` aligned with pan.
        right = np.array([math.cos(pan), 0.0, math.sin(pan)])
        norm = float(np.linalg.norm(right))
    right /= norm

    up = np.cross(right, forward)
    up /= np.linalg.norm(up)

    return forward, right, up


__all__ = [
    "camera_basis",
    "dori_range_m",
    "f_px",
    "footprint_m",
    "gsd_m",
    "hfov_rad",
    "vfov_rad",
]
