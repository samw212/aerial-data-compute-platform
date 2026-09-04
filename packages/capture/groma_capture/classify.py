"""Nadir and oblique classification. Build spec 8.5.

Split on gimbal pitch, where -90 degrees is straight down.

The reason this matters is structural, not cosmetic. A nadir-only flight sees the
top of a mast and almost none of its side, so the reconstruction has no evidence of
the mast's height and the fitted cylinder comes out short or missing. Mast geometry
is the input to camera mounting, so a nadir-only survey silently produces a coverage
plan mounted at the wrong heights. See explained.md 2.10.
"""

from __future__ import annotations

from dataclasses import dataclass

NADIR_PITCH_DEG = -90.0
NADIR_TOLERANCE_DEG = 10.0
"""Nadir is -90 +/- 10 degrees."""

OBLIQUE_MIN_DEG = -70.0
OBLIQUE_MAX_DEG = -20.0
"""Oblique runs from -70 to -20 degrees; between -80 and -70 is neither."""


@dataclass(frozen=True)
class CaptureSplit:
    nadir: int
    oblique: int
    other: int
    unknown: int
    """Frames with no gimbal pitch recorded at all."""

    @property
    def total(self) -> int:
        return self.nadir + self.oblique + self.other + self.unknown


def is_nadir(pitch_deg: float | None) -> bool:
    if pitch_deg is None:
        return False
    return abs(pitch_deg - NADIR_PITCH_DEG) <= NADIR_TOLERANCE_DEG


def is_oblique(pitch_deg: float | None) -> bool:
    if pitch_deg is None:
        return False
    return OBLIQUE_MIN_DEG <= pitch_deg <= OBLIQUE_MAX_DEG


def classify(pitches: list[float | None]) -> CaptureSplit:
    nadir = oblique = other = unknown = 0
    for p in pitches:
        if p is None:
            unknown += 1
        elif is_nadir(p):
            nadir += 1
        elif is_oblique(p):
            oblique += 1
        else:
            other += 1
    return CaptureSplit(nadir=nadir, oblique=oblique, other=other, unknown=unknown)


__all__ = [
    "NADIR_PITCH_DEG",
    "NADIR_TOLERANCE_DEG",
    "OBLIQUE_MAX_DEG",
    "OBLIQUE_MIN_DEG",
    "CaptureSplit",
    "classify",
    "is_nadir",
    "is_oblique",
]
