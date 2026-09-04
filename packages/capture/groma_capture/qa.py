"""The capture QA report and its gate. Build spec 8.3, 8.4, 8.5, 8.7.

`CaptureQA.blocking` is a gate, not advice: POST /surveys/{id}/reconstruct answers
409 while it is non-empty and unacknowledged. The distinction between blocking and
warning is the distinction between "this cannot produce a usable model" and "this
will produce a model you should look at sceptically".

The thresholds come from the build spec and are stated once, here, so that a report
and the API agree about what blocked a survey.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from groma_capture.classify import CaptureSplit
from groma_capture.quality import ABSOLUTE_UNUSABLE_SHARPNESS, DEFAULT_CLIP_LIMIT
from groma_contracts.imagery import CaptureQA, ImageState

FRONT_OVERLAP_BLOCK = 0.60
FRONT_OVERLAP_WARN = 0.70
SIDE_OVERLAP_WARN = 0.60
MAX_REJECTED_FRACTION = 0.30
MIN_ACCEPTED_IMAGES = 20


@dataclass(frozen=True)
class AssessedImage:
    """One image after scoring, before it becomes a database row."""

    filename: str
    sharpness: float
    clipped_fraction: float
    state: ImageState = ImageState.ACCEPTED
    gimbal_pitch_deg: float | None = None
    rtk_fixed: bool = False

    @property
    def accepted(self) -> bool:
        return self.state == ImageState.ACCEPTED


def apply_gates(
    images: list[AssessedImage],
    *,
    sharpness_floor: float,
    clip_limit: float = DEFAULT_CLIP_LIMIT,
    absolute_minimum: float = ABSOLUTE_UNUSABLE_SHARPNESS,
) -> list[AssessedImage]:
    """Set each image's state from its scores.

    A frame is rejected for blur when it falls under the set's relative threshold or
    under the absolute minimum, whichever catches it. See
    `quality.ABSOLUTE_UNUSABLE_SHARPNESS` for why the second test is needed.

    Blur is checked before exposure so that a frame which is both blurred and
    clipped is reported as blurred, which is the more actionable of the two.
    """
    out: list[AssessedImage] = []
    for im in images:
        if im.sharpness < sharpness_floor or im.sharpness < absolute_minimum:
            state = ImageState.REJECTED_BLUR
        elif im.clipped_fraction > clip_limit:
            state = ImageState.REJECTED_EXPOSURE
        else:
            state = ImageState.ACCEPTED
        out.append(
            AssessedImage(
                filename=im.filename,
                sharpness=im.sharpness,
                clipped_fraction=im.clipped_fraction,
                state=state,
                gimbal_pitch_deg=im.gimbal_pitch_deg,
                rtk_fixed=im.rtk_fixed,
            )
        )
    return out


def build_qa(
    images: list[AssessedImage],
    split: CaptureSplit,
    *,
    front_overlap: float | None = None,
    side_overlap: float | None = None,
    estimated_gsd_m: float | None = None,
    sensor_estimated: bool = False,
    georef: str = "none",
    has_scale_bar: bool = False,
    video_sourced: bool = False,
) -> CaptureQA:
    """Assemble the report and decide what blocks reconstruction."""
    total = len(images)
    accepted = [im for im in images if im.accepted]
    rejected: dict[str, int] = {}
    for im in images:
        if not im.accepted:
            rejected[im.state.value] = rejected.get(im.state.value, 0) + 1

    sharpness_p10 = (
        float(statistics.quantiles([im.sharpness for im in images], n=10)[0])
        if total >= 2
        else float(images[0].sharpness if total else 0.0)
    )
    rejected_fraction = (total - len(accepted)) / total if total else 0.0
    rtk_fraction = (
        sum(1 for im in accepted if im.rtk_fixed) / len(accepted) if accepted else 0.0
    )

    warnings: list[str] = []
    blocking: list[str] = []

    if front_overlap is not None:
        if front_overlap < FRONT_OVERLAP_BLOCK:
            blocking.append(
                f"Front overlap is {front_overlap:.0%}, below the {FRONT_OVERLAP_BLOCK:.0%} "
                "needed to reconstruct. Re-fly with a shorter shutter interval."
            )
        elif front_overlap < FRONT_OVERLAP_WARN:
            warnings.append(
                f"Front overlap is {front_overlap:.0%}, below the {FRONT_OVERLAP_WARN:.0%} "
                "recommended. Expect gaps where the ground is featureless."
            )
    else:
        warnings.append("Front overlap could not be estimated: no usable GPS or altitude.")

    if side_overlap is not None and side_overlap < SIDE_OVERLAP_WARN:
        warnings.append(
            f"Side overlap is {side_overlap:.0%}, below the {SIDE_OVERLAP_WARN:.0%} "
            "recommended. Expect weak geometry between flight lines."
        )

    if rejected_fraction > MAX_REJECTED_FRACTION:
        blocking.append(
            f"{rejected_fraction:.0%} of frames were rejected, above the "
            f"{MAX_REJECTED_FRACTION:.0%} limit."
        )
    if len(accepted) < MIN_ACCEPTED_IMAGES:
        blocking.append(
            f"Only {len(accepted)} usable images; at least {MIN_ACCEPTED_IMAGES} are needed."
        )
    if georef == "none" and not has_scale_bar:
        blocking.append(
            "No georeferencing and no scale bar: the model would be correct in shape and "
            "arbitrary in size, so nothing on it could be measured."
        )

    if split.oblique == 0 and total:
        warnings.append(
            "Nadir-only capture: masts will reconstruct short or not at all, and mast "
            "geometry is the input to camera mounting."
        )
    if sensor_estimated:
        warnings.append(
            "Sensor dimensions were estimated from the 35 mm equivalent focal length. "
            "The error propagates into GSD and into every px/m figure downstream."
        )
    if video_sourced:
        warnings.append(
            "Frames came from video: rolling shutter and compression both reduce the "
            "accuracy of the reconstruction."
        )

    return CaptureQA(
        image_count=total,
        accepted_count=len(accepted),
        rejected=rejected,
        sharpness_p10=sharpness_p10,
        estimated_gsd_m=estimated_gsd_m,
        estimated_front_overlap=front_overlap,
        estimated_side_overlap=side_overlap,
        nadir_count=split.nadir,
        oblique_count=split.oblique,
        rtk_fraction=rtk_fraction,
        warnings=warnings,
        blocking=blocking,
    )


__all__ = [
    "FRONT_OVERLAP_BLOCK",
    "FRONT_OVERLAP_WARN",
    "MAX_REJECTED_FRACTION",
    "MIN_ACCEPTED_IMAGES",
    "SIDE_OVERLAP_WARN",
    "AssessedImage",
    "apply_gates",
    "build_qa",
]
