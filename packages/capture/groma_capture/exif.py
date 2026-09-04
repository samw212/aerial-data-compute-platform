"""EXIF and XMP extraction. Build spec 8.2.

Extraction shells out to `exiftool -json -n`. That is a deliberate dependency: the
drone metadata this system depends on lives in vendor XMP namespaces
(`drone-dji:RelativeAltitude`, `drone-dji:RtkFlag`) that no Python EXIF library
reads reliably, and getting the RTK flag wrong means treating a 2 m GPS fix as a
2 cm one.

`-n` disables exiftool's pretty printing, so every value arrives as a number rather
than as a string like "8.8 mm" or a latitude like "22 deg 22' 56.29\" N". Parsing
below therefore assumes numbers and treats anything else as absent.

The parser is separated from the subprocess so it can be tested against a committed
sample of real exiftool output without exiftool installed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

RTK_FIXED_FLAG = 50
"""drone-dji:RtkFlag == 50 is an RTK fixed solution. Anything else is not."""

_DATETIME_FORMATS = ("%Y:%m:%d %H:%M:%S", "%Y:%m:%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S")


@dataclass(frozen=True)
class ExifRecord:
    """The subset of image metadata the pipeline uses."""

    path: str
    filename: str
    width: int
    height: int
    make: str | None = None
    model: str | None = None
    lens_model: str | None = None
    focal_mm: float | None = None
    focal_35_mm: float | None = None
    captured_at: datetime | None = None
    gps_lat: float | None = None
    gps_lon: float | None = None
    gps_alt_m: float | None = None
    gps_alt_is_orthometric: bool | None = None
    """GPSAltitudeRef 0 is above sea level, 1 is below; DJI writes ellipsoidal in XMP."""
    relative_altitude_m: float | None = None
    """drone-dji:RelativeAltitude, height above the take-off point."""
    gimbal_pitch_deg: float | None = None
    gimbal_yaw_deg: float | None = None
    gimbal_roll_deg: float | None = None
    rtk_flag: int | None = None
    rtk_std_lat_m: float | None = None
    rtk_std_lon_m: float | None = None
    rtk_std_hgt_m: float | None = None

    @property
    def rtk_fixed(self) -> bool:
        return self.rtk_flag == RTK_FIXED_FLAG

    @property
    def gps_accuracy_m(self) -> float | None:
        """Horizontal standard deviation, when the aircraft recorded one."""
        if self.rtk_std_lat_m is None and self.rtk_std_lon_m is None:
            return None
        lat = self.rtk_std_lat_m or 0.0
        lon = self.rtk_std_lon_m or 0.0
        return float((lat**2 + lon**2) ** 0.5)


def _num(raw: dict[str, object], *keys: str) -> float | None:
    """First numeric value among `keys`, accepting numbers written as strings.

    `-n` stops exiftool converting numbers into human-readable text, but it does not
    make the XMP tags numeric: `drone-dji:RelativeAltitude` arrives as the string
    "+39.80", sign included, because XMP has no number type. Reading it as a number
    is not optional. Without the relative altitude there is no ground footprint, so
    there is no overlap estimate and no GSD, and the QA report silently degrades to
    "could not be estimated" on perfectly good imagery.
    """
    for k in keys:
        v = raw.get(k)
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v.strip().lstrip("+"))
            except ValueError:
                continue
    return None


def _int(raw: dict[str, object], *keys: str) -> int | None:
    v = _num(raw, *keys)
    return None if v is None else int(v)


def _text(raw: dict[str, object], *keys: str) -> str | None:
    for k in keys:
        v = raw.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _timestamp(raw: dict[str, object]) -> datetime | None:
    text = _text(raw, "DateTimeOriginal", "CreateDate", "ModifyDate")
    if not text:
        return None
    cleaned = text.split("+")[0].split("Z")[0].strip()
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def parse_record(raw: dict[str, object]) -> ExifRecord | None:
    """Turn one exiftool JSON object into an ExifRecord.

    Returns None when the object has no usable pixel dimensions, which is how a
    non-image file that happened to be in the directory is dropped.
    """
    width = _int(raw, "ImageWidth", "ExifImageWidth")
    height = _int(raw, "ImageHeight", "ExifImageHeight")
    if not width or not height or width <= 0 or height <= 0:
        return None
    source = _text(raw, "SourceFile") or ""
    alt_ref = _int(raw, "GPSAltitudeRef")
    return ExifRecord(
        path=source,
        filename=_text(raw, "FileName") or Path(source).name,
        width=width,
        height=height,
        make=_text(raw, "Make"),
        model=_text(raw, "Model"),
        lens_model=_text(raw, "LensModel"),
        focal_mm=_num(raw, "FocalLength"),
        focal_35_mm=_num(raw, "FocalLengthIn35mmFormat", "FocalLengthIn35mmFilm"),
        captured_at=_timestamp(raw),
        gps_lat=_num(raw, "GPSLatitude"),
        gps_lon=_num(raw, "GPSLongitude"),
        gps_alt_m=_num(raw, "GPSAltitude", "AbsoluteAltitude"),
        gps_alt_is_orthometric=None if alt_ref is None else alt_ref in (0, 1),
        relative_altitude_m=_num(raw, "RelativeAltitude"),
        gimbal_pitch_deg=_num(raw, "GimbalPitchDegree"),
        gimbal_yaw_deg=_num(raw, "GimbalYawDegree"),
        gimbal_roll_deg=_num(raw, "GimbalRollDegree"),
        rtk_flag=_int(raw, "RtkFlag"),
        rtk_std_lat_m=_num(raw, "RtkStdLat"),
        rtk_std_lon_m=_num(raw, "RtkStdLon"),
        rtk_std_hgt_m=_num(raw, "RtkStdHgt"),
    )


def parse_exiftool_json(payload: str | list[dict[str, object]]) -> list[ExifRecord]:
    """Parse the whole of an `exiftool -json -n` document."""
    rows = json.loads(payload) if isinstance(payload, str) else payload
    return [r for r in (parse_record(dict(row)) for row in rows) if r is not None]


def exiftool_available() -> bool:
    return shutil.which("exiftool") is not None


def read_directory(directory: Path | str, *, timeout_s: float = 900.0) -> list[ExifRecord]:
    """Run exiftool over a directory of images and parse the result.

    Raises RuntimeError when exiftool is absent, rather than falling back to a
    weaker reader: a silent downgrade here would drop the RTK flag and the gimbal
    angles, and the survey would look fine while being wrong about both.
    """
    if not exiftool_available():
        raise RuntimeError(
            "exiftool is not installed. It is required for capture ingest because the "
            "drone-dji XMP tags (RelativeAltitude, GimbalPitchDegree, RtkFlag) are not "
            "readable without it. Install it with: apt-get install -y libimage-exiftool-perl"
        )
    proc = subprocess.run(
        ["exiftool", "-json", "-n", "-r", str(directory)],
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    if proc.returncode != 0 and not proc.stdout.strip():
        raise RuntimeError(f"exiftool failed: {proc.stderr.strip()[:400]}")
    return parse_exiftool_json(proc.stdout or "[]")


__all__ = [
    "RTK_FIXED_FLAG",
    "ExifRecord",
    "exiftool_available",
    "parse_exiftool_json",
    "parse_record",
    "read_directory",
]
