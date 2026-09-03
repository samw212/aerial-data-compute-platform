"""Labelled heights. CLAUDE.md, known trap 5.

Every stored height carries its datum. Ellipsoidal, orthometric and above-ground
heights differ by tens of metres, they all look like plausible numbers, and mixing
them puts cameras underground with no error message anywhere.

The geoid separation needed to convert ellipsoidal to orthometric is a grid lookup
(HKGeoid or EGM2008) that lands with M8. Until then `to_orthometric` refuses rather
than guessing: a silent wrong conversion is the failure this module exists to stop.
"""

from __future__ import annotations

from dataclasses import dataclass

from groma_contracts.site import HeightDatum


@dataclass(frozen=True)
class LabelledHeight:
    """A height that knows what it is measured from."""

    value_m: float
    datum: HeightDatum

    def __post_init__(self) -> None:
        if not isinstance(self.datum, HeightDatum):
            raise TypeError(f"datum must be a HeightDatum, got {type(self.datum).__name__}")

    def difference_to(self, other: LabelledHeight) -> float:
        """Height difference, which is only meaningful within one datum.

        Differences are datum-invariant only if both heights share a datum; the
        geoid separation cancels. Across datums it does not, so this raises.
        """
        if self.datum is not other.datum:
            raise ValueError(
                f"cannot subtract a {other.datum} height from a {self.datum} height; "
                "convert to a common datum first"
            )
        return self.value_m - other.value_m


def to_orthometric(
    height: LabelledHeight, geoid_separation_m: float | None = None
) -> LabelledHeight:
    """Convert to orthometric (metres above Principal Datum).

    orthometric = ellipsoidal - geoid_separation

    `geoid_separation_m` must be supplied for an ellipsoidal input; there is no
    default, because the value varies by tens of metres across a region and a
    plausible-looking guess is exactly the trap.
    """
    if height.datum is HeightDatum.ORTHOMETRIC_MPD:
        return height
    if height.datum is HeightDatum.LOCAL:
        raise ValueError(
            "a local vertical datum has no defined relationship to Principal Datum; "
            "georeference the survey first"
        )
    if geoid_separation_m is None:
        raise ValueError(
            "converting an ellipsoidal height needs a geoid separation; pass one "
            "from the geoid model rather than assuming a value"
        )
    return LabelledHeight(height.value_m - geoid_separation_m, HeightDatum.ORTHOMETRIC_MPD)


__all__ = ["LabelledHeight", "to_orthometric"]
