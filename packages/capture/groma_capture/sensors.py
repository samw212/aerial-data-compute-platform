"""Sensor dimension lookup. Build spec 8.2.

EXIF carries focal length in millimetres and, for practical purposes, never carries
sensor dimensions. Both are needed for a ground sample distance, so the pair
(make, model) is resolved against a maintained table.

When a model is absent the 35 mm equivalent gives a usable estimate:

    sensor_w_mm = 36 * focal_mm / focal_35_mm

That identity is exact by the definition of "35 mm equivalent" — the focal length
that would produce the same field of view on a 36 mm wide frame. It is still an
estimate here, because the reported equivalent is itself rounded by the camera, and
the error propagates directly into GSD and therefore into every px/m in the report.
Every estimated sensor is recorded in `capture_qa.warnings`.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path

from groma_contracts.imagery import SensorSpec

FULL_FRAME_WIDTH_MM = 36.0
"""The width of a 35 mm film frame, which is what "35 mm equivalent" is equivalent to."""

DEFAULT_TABLE = Path(__file__).resolve().parents[3] / "fixtures" / "sensors" / "sensors.yaml"


def _key(make: str, model: str) -> tuple[str, str]:
    return (make.strip().lower(), model.strip().lower())


@dataclass(frozen=True)
class SensorTable:
    """A lookup from (make, model) to a physical sensor."""

    entries: dict[tuple[str, str], SensorSpec]

    @classmethod
    def from_rows(cls, rows: list[dict[str, object]]) -> SensorTable:
        return cls(
            {_key(str(r["make"]), str(r["model"])): SensorSpec(**r) for r in rows}
        )

    @classmethod
    def from_yaml(cls, path: Path | None = None) -> SensorTable:
        import yaml  # type: ignore[import-untyped]  # lazy: pyyaml is an m6 extra

        doc = yaml.safe_load(Path(path or DEFAULT_TABLE).read_text())
        return cls.from_rows(list(doc["sensors"]))

    def get(self, make: str | None, model: str | None) -> SensorSpec | None:
        if not make or not model:
            return None
        return self.entries.get(_key(make, model))


@functools.lru_cache(maxsize=1)
def default_table() -> SensorTable:
    """The committed table, parsed once."""
    return SensorTable.from_yaml()


def estimate_sensor(
    *,
    make: str | None,
    model: str | None,
    focal_mm: float | None,
    focal_35_mm: float | None,
    res_x: int,
    res_y: int,
) -> SensorSpec | None:
    """Derive a sensor from the 35 mm equivalent focal length.

    Returns None when the equivalent is missing or degenerate, because a guessed
    sensor is worse than an absent one: absent blocks dimensioning loudly, whereas
    a guess produces a plausible and wrong px/m.
    """
    if not focal_mm or not focal_35_mm or focal_mm <= 0 or focal_35_mm <= 0:
        return None
    width = FULL_FRAME_WIDTH_MM * focal_mm / focal_35_mm
    if res_x <= 0 or res_y <= 0:
        return None
    # Height follows from the pixel aspect ratio, which is square on every sensor
    # this system will meet. Deriving it keeps the frame's diagonal consistent.
    height = width * res_y / res_x
    return SensorSpec(
        make=(make or "unknown").strip(),
        model=(model or "unknown").strip(),
        sensor_w_mm=width,
        sensor_h_mm=height,
        res_x=res_x,
        res_y=res_y,
    )


def resolve_sensor(
    *,
    make: str | None,
    model: str | None,
    focal_mm: float | None,
    focal_35_mm: float | None,
    res_x: int,
    res_y: int,
    table: SensorTable | None = None,
) -> tuple[SensorSpec | None, bool]:
    """Return (sensor, estimated).

    `estimated` is True when the dimensions came from the 35 mm equivalent rather
    than the table; the caller must surface it as a warning.
    """
    known = (table or default_table()).get(make, model)
    if known is not None:
        return known, False
    return estimate_sensor(
        make=make,
        model=model,
        focal_mm=focal_mm,
        focal_35_mm=focal_35_mm,
        res_x=res_x,
        res_y=res_y,
    ), True


__all__ = [
    "FULL_FRAME_WIDTH_MM",
    "SensorTable",
    "default_table",
    "estimate_sensor",
    "resolve_sensor",
]
