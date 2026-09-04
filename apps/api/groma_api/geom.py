"""Between PostGIS geometry in the venue's CRS and local ENU. CLAUDE.md, "Coordinate frames".

Storage is (easting, northing, height) in `venue.srid`. Compute and display are
local ENU metres relative to the venue origin, Y up, -Z north. Every value that
leaves the API for the browser has been through `to_local_*` here; every value
that arrives from the browser goes through `to_storage_*`. Nothing else converts.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from geoalchemy2.elements import WKBElement
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import MultiPolygon, Point, Polygon

from groma_contracts.geometry import Vec3
from groma_contracts.site import HeightDatum, SiteOrigin
from groma_geo.origin import to_local, to_storage

XZ = tuple[float, float]


def origin_of(venue) -> SiteOrigin:  # type: ignore[no-untyped-def]
    return SiteOrigin(
        srid=venue.srid,
        x=venue.origin_x,
        y=venue.origin_y,
        z=venue.origin_z,
        height_datum=HeightDatum(venue.height_datum),
    )


# ---- plan-view polygons (facility boundary, tents, blind regions) --------------


def polygon_to_local(geom: WKBElement | None, origin: SiteOrigin) -> list[XZ]:
    """Exterior ring of a stored polygon as local (x, z) pairs, closing point dropped."""
    if geom is None:
        return []
    shape = to_shape(geom)
    coords = np.asarray(shape.exterior.coords, dtype=np.float64)[:-1]
    en = np.column_stack([coords[:, 0], coords[:, 1], np.zeros(len(coords))])
    local = to_local(en, origin)
    return [(float(x), float(z)) for x, z in zip(local[:, 0], local[:, 2], strict=True)]


def polygon_to_storage(ring: Sequence[XZ], origin: SiteOrigin) -> WKBElement:
    pts = np.asarray([(x, 0.0, z) for x, z in ring], dtype=np.float64)
    en = to_storage(pts, origin)
    return from_shape(Polygon([(float(e), float(n)) for e, n, _ in en]), srid=0)


def multipolygon_to_storage(rings: Sequence[Sequence[XZ]], origin: SiteOrigin) -> WKBElement | None:
    polys = []
    for ring in rings:
        if len(ring) < 3:
            continue
        pts = np.asarray([(x, 0.0, z) for x, z in ring], dtype=np.float64)
        en = to_storage(pts, origin)
        polys.append(Polygon([(float(e), float(n)) for e, n, _ in en]))
    if not polys:
        return None
    return from_shape(MultiPolygon(polys), srid=0)


def multipolygon_to_local(geom: WKBElement | None, origin: SiteOrigin) -> list[list[XZ]]:
    if geom is None:
        return []
    shape = to_shape(geom)
    polys = list(shape.geoms) if hasattr(shape, "geoms") else [shape]
    out: list[list[XZ]] = []
    for poly in polys:
        coords = np.asarray(poly.exterior.coords, dtype=np.float64)[:-1]
        en = np.column_stack([coords[:, 0], coords[:, 1], np.zeros(len(coords))])
        local = to_local(en, origin)
        out.append([(float(x), float(z)) for x, z in zip(local[:, 0], local[:, 2], strict=True)])
    return out


# ---- 3-D points (cameras, mount points, GCPs) ----------------------------------


def point_to_local(geom: WKBElement, origin: SiteOrigin) -> Vec3:
    p = to_shape(geom)
    local = to_local([p.x, p.y, p.z if p.has_z else 0.0], origin)
    return Vec3(x=float(local[0]), y=float(local[1]), z=float(local[2]))


def point_to_storage(v: Vec3, origin: SiteOrigin) -> WKBElement:
    en = to_storage([v.x, v.y, v.z], origin)
    return from_shape(Point(float(en[0]), float(en[1]), float(en[2])), srid=0)


# ---- boundary as a storage polygon straight from (easting, northing) -----------


def storage_polygon(ring: Sequence[tuple[float, float]]) -> WKBElement:
    return from_shape(Polygon([(float(e), float(n)) for e, n in ring]), srid=0)


def storage_polygon_coords(geom: WKBElement | None) -> list[tuple[float, float]] | None:
    if geom is None:
        return None
    coords = list(to_shape(geom).exterior.coords)[:-1]
    return [(float(e), float(n)) for e, n in coords]


__all__ = [
    "multipolygon_to_local",
    "multipolygon_to_storage",
    "origin_of",
    "point_to_local",
    "point_to_storage",
    "polygon_to_local",
    "polygon_to_storage",
    "storage_polygon",
    "storage_polygon_coords",
]
