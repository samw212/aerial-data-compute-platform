"""Per-image quality scoring. Build spec 8.3.

Two measures, both cheap enough to run on every frame of a large flight:

- **Sharpness**, the variance of the Laplacian on a greyscale downscale. A blurred
  frame has little high-frequency content, so the second derivative is small
  everywhere and its variance collapses. The absolute value depends on how much
  texture the scene has, which is why the threshold is a percentile of the set with
  an absolute floor underneath rather than a fixed number: a flight over mown grass
  scores lower everywhere than one over a car park, and neither is blurred.
- **Clipping**, the fraction of pixels crushed to 0 or blown to 255. Clipped pixels
  carry no gradient, so features cannot be matched in them.

The array functions here are pure NumPy and are the ones under test. Decoding a
file needs Pillow, which is an M6 extra, so it lives behind a lazy import.
"""

from __future__ import annotations

import numpy as np

LAPLACIAN_KERNEL = np.array([[0.0, 1.0, 0.0], [1.0, -4.0, 1.0], [0.0, 1.0, 0.0]])
"""The 4-neighbour discrete Laplacian, the same stencil OpenCV's ksize=1 uses."""

DEFAULT_SHARPNESS_FLOOR = 8.0
"""The spec's absolute floor: the upper bound on the relative rejection threshold."""

ABSOLUTE_UNUSABLE_SHARPNESS = 1.0
"""Variance below which a frame carries no matchable detail in any scene.

This constant is *not* in build spec 8.3, and it is here to close a hole in the rule
as written. The spec says to reject below "the 10th percentile of the set or an
absolute floor, whichever is lower". Taking the lower of the two is right for a good
flight: it stops a uniformly sharp set from losing a tenth of its frames to a
percentile that means nothing. But it inverts on a bad flight. If half the set is
blurred, the 10th percentile lands *inside* the blurred cluster, the threshold
collapses to that value, almost nothing is rejected, and the "more than 30% of
frames rejected" blocking rule can never fire. A half-blurred survey would pass the
gate and waste an hour of reconstruction.

So the percentile rule stays exactly as specified and governs the relative
threshold, and this floor sits underneath it as a hard minimum. At this level the
Laplacian variance of 8-bit imagery is essentially a flat grey frame.
"""

DEFAULT_CLIP_LIMIT = 0.05
"""Reject above 5% clipped pixels (build spec 8.3)."""

DOWNSCALE_WIDTH = 1024
"""Sharpness is scale dependent, so every frame is measured at one width."""


def laplacian(gray: np.ndarray) -> np.ndarray:
    """Convolve with the 4-neighbour Laplacian, dropping the 1 px border.

    The border is dropped rather than padded because padding invents a gradient at
    the frame edge that would count towards the variance.
    """
    a = np.asarray(gray, dtype=np.float64)
    if a.ndim != 2 or a.shape[0] < 3 or a.shape[1] < 3:
        raise ValueError("laplacian needs a 2-D array of at least 3x3")
    return (
        a[:-2, 1:-1] + a[2:, 1:-1] + a[1:-1, :-2] + a[1:-1, 2:] - 4.0 * a[1:-1, 1:-1]
    )


def laplacian_variance(gray: np.ndarray) -> float:
    """Variance of the Laplacian: the sharpness score."""
    return float(np.var(laplacian(gray)))


def clipped_fraction(image: np.ndarray, *, low: float = 0.0, high: float = 255.0) -> float:
    """Fraction of samples sitting exactly on either end of the range."""
    a = np.asarray(image)
    if a.size == 0:
        return 0.0
    return float(np.count_nonzero((a <= low) | (a >= high)) / a.size)


def sharpness_threshold(
    scores: list[float] | np.ndarray, *, floor: float = DEFAULT_SHARPNESS_FLOOR
) -> float:
    """The rejection threshold: the 10th percentile or the floor, whichever is lower.

    "Whichever is lower" is deliberate and is the whole point of the rule. A set that
    is uniformly sharp still has a 10th percentile, and rejecting a tenth of a good
    flight would be absurd; taking the lower of the two means the percentile only
    bites when the set genuinely contains softer frames than the floor allows.
    """
    a = np.asarray(list(scores), dtype=np.float64)
    if a.size == 0:
        return floor
    percentile = float(np.percentile(a, 10.0))
    return percentile if percentile < floor else floor


def to_greyscale(rgb: np.ndarray) -> np.ndarray:
    """Rec. 601 luma, the same weighting OpenCV's COLOR_RGB2GRAY applies."""
    a = np.asarray(rgb, dtype=np.float64)
    if a.ndim == 2:
        return a
    return 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]


class ScoringUnavailableError(RuntimeError):
    """Raised when frames cannot be scored at all, as opposed to scoring badly.

    The distinction matters more than it looks. When Pillow was missing on the
    instance, every frame failed to decode, was recorded as sharpness 0, and the QA
    report announced that 100% of the flight was blurred and blocked it. The report
    blamed the imagery for a missing library. A cause that is not the imagery must
    never be reported as a property of the imagery.
    """


def score_file(path: str, *, width: int = DOWNSCALE_WIDTH) -> tuple[float, float]:
    """Return (sharpness, clipped_fraction) for an image on disk.

    Needs Pillow, which the `m6` extra installs. Its absence raises
    `ScoringUnavailableError` rather than returning a score, so that a deployment fault
    surfaces as a deployment fault.
    """
    try:
        from PIL import Image  # type: ignore[import-not-found]  # lazy: pillow is an m6 extra
    except ImportError as exc:  # pragma: no cover - exercised by the deployment, not the suite
        raise ScoringUnavailableError(
            "Pillow is not installed, so image quality cannot be scored. Install the "
            "capture extra: uv sync --extra m6"
        ) from exc

    with Image.open(path) as im:
        im = im.convert("RGB")
        clipped = clipped_fraction(np.asarray(im))
        if im.width > width:
            im = im.resize((width, max(1, round(im.height * width / im.width))))
        grey = to_greyscale(np.asarray(im))
    return laplacian_variance(grey), clipped


__all__ = [
    "ABSOLUTE_UNUSABLE_SHARPNESS",
    "DEFAULT_CLIP_LIMIT",
    "DEFAULT_SHARPNESS_FLOOR",
    "DOWNSCALE_WIDTH",
    "LAPLACIAN_KERNEL",
    "ScoringUnavailableError",
    "clipped_fraction",
    "laplacian",
    "laplacian_variance",
    "score_file",
    "sharpness_threshold",
    "to_greyscale",
]
