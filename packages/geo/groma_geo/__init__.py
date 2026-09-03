"""Groma geo: coordinate frames, height datums, optics.

crs.py and raster.py (pyproj/rasterio) land with M8/M9 and are deliberately absent
here, so that installing the coverage kernel does not require GDAL.
"""

from groma_geo.heights import LabelledHeight, to_orthometric
from groma_geo.optics import (
    camera_basis,
    dori_range_m,
    f_px,
    footprint_m,
    gsd_m,
    hfov_rad,
    vfov_rad,
)
from groma_geo.origin import assert_local, to_local, to_storage

__all__ = [
    "LabelledHeight",
    "assert_local",
    "camera_basis",
    "dori_range_m",
    "f_px",
    "footprint_m",
    "gsd_m",
    "hfov_rad",
    "to_local",
    "to_orthometric",
    "to_storage",
    "vfov_rad",
]
