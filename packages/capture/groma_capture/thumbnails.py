"""Thumbnails for the capture gallery.

A survey is hundreds of 20 megapixel frames. The browser needs a contact sheet, so
each frame is reduced once, at ingest, and the reduction is what the gallery loads.
Serving the originals would be several gigabytes down the wire for one screen.

EXIF orientation is applied and then dropped. A thumbnail that still carries an
orientation flag is rotated by some viewers and not others, and a gallery where half
the frames are sideways reads as a reconstruction fault rather than a display one.
"""

from __future__ import annotations

from pathlib import Path

THUMBNAIL_MAX_PX = 320
"""Long edge of a gallery thumbnail. Two of these fit the dock at device pixel ratio 2."""

THUMBNAIL_QUALITY = 78


def write_thumbnail(
    source: Path | str, destination: Path | str, *, max_px: int = THUMBNAIL_MAX_PX
) -> Path:
    """Write a reduced JPEG copy of `source` and return its path."""
    from PIL import Image, ImageOps  # pillow is an m6 extra, imported lazily

    dst = Path(destination)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as opened:
        upright = ImageOps.exif_transpose(opened) or opened
        rgb = upright.convert("RGB")
        rgb.thumbnail((max_px, max_px))
        rgb.save(dst, "JPEG", quality=THUMBNAIL_QUALITY, optimize=True)
    return dst


__all__ = ["THUMBNAIL_MAX_PX", "THUMBNAIL_QUALITY", "write_thumbnail"]
