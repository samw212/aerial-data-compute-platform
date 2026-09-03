"""Contract behaviour. Build spec 4, 5.

The shapes themselves are Pydantic's problem. What is tested here is the
behaviour the specification attaches to them: the measurement formatting rule, the
georeferencing gate, typed rejection, and the discriminated primitive union that
the whole geometry layer depends on parsing correctly.
"""

from __future__ import annotations

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from groma_contracts import (
    CONTRACTS_VERSION,
    BoxPrim,
    CylinderPrim,
    ExtrudedPolyline,
    GeorefMethod,
    RejectReason,
    ReviewState,
    SiteFixture,
    Structure,
    StructureClass,
    Survey,
    format_measurement,
)
from groma_contracts.geometry import Primitive


def test_contracts_version_is_set() -> None:
    assert CONTRACTS_VERSION


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"kind": "box", "cx": 0, "cy": 1, "cz": 0, "hx": 1, "hy": 1, "hz": 1}, BoxPrim),
        ({"kind": "cylinder", "cx": 0, "cz": 0, "r": 0.3, "y0": 0, "y1": 15}, CylinderPrim),
        (
            {
                "kind": "polyline",
                "points": [[0, 0], [10, 0]],
                "y0": 0,
                "y1": 2.4,
                "thickness": 0.12,
            },
            ExtrudedPolyline,
        ),
    ],
)
def test_primitive_union_discriminates_on_kind(payload: dict, expected: type) -> None:
    """A primitive round-trips to its own class, not to whichever matches first.

    Every occluder in the system is parsed through this union. A box silently
    validating as something else would move geometry without erroring anywhere.
    """
    parsed = TypeAdapter(Primitive).validate_python(payload)
    assert isinstance(parsed, expected)


def test_primitive_union_rejects_an_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(Primitive).validate_python({"kind": "sphere", "r": 1.0})


def test_degenerate_primitives_are_rejected() -> None:
    """Zero extents produce rays that intersect nothing and shadows that vanish."""
    with pytest.raises(ValidationError):
        BoxPrim(cx=0, cy=0, cz=0, hx=0, hy=1, hz=1)
    with pytest.raises(ValidationError):
        CylinderPrim(cx=0, cz=0, r=0, y0=0, y1=5)
    with pytest.raises(ValidationError):
        ExtrudedPolyline(points=[(0.0, 0.0)], y0=0, y1=2, thickness=0.1)


@pytest.mark.parametrize(
    ("value", "uncertainty", "expected"),
    [
        (47.8213, 0.03, "47.82 m +/- 0.03"),
        (47.8213, 0.004, "47.821 m +/- 0.004"),
        (105.0, 0.25, "105.0 m +/- 0.2"),
        (12.3456, 0.0, "12.346 m +/- 0.000"),
    ],
)
def test_measurements_are_formatted_to_their_tolerance(
    value: float, uncertainty: float, expected: str
) -> None:
    """Never format a measurement to more precision than its tolerance.

    47.82 m +/- 0.03, not 47.8213 m. The long form is a number someone will paste
    into a site plan believing four decimal places of it.
    """
    assert format_measurement(value, uncertainty) == expected


def test_uncertainty_has_no_default() -> None:
    """measurement.uncertainty is deliberately NOT NULL, with no default."""
    from groma_contracts import Measurement

    with pytest.raises(ValidationError):
        Measurement(
            id="m1",
            site_id="s1",
            survey_id="sv1",
            kind="distance",
            value=47.82,
            unit="m",
            snap_mode="primitive_feature",
        )


def test_scale_free_survey_blocks_dimensioning() -> None:
    """georef='none' means the model is correct in shape and arbitrary in size.

    The API returns 409 on a measurement against such a survey; this is the flag
    that decision reads.
    """
    scale_free = Survey(id="a", site_id="s", name="no georef", georef=GeorefMethod.NONE)
    assert not scale_free.dimensioning_allowed

    for method in (GeorefMethod.RTK, GeorefMethod.PPK, GeorefMethod.GCP, GeorefMethod.SCALE_BAR):
        assert Survey(id="a", site_id="s", name="x", georef=method).dimensioning_allowed


def test_only_accepted_structures_occlude() -> None:
    """The occlusion model reads structures WHERE state = 'accepted'. Nothing else."""
    prim = CylinderPrim(cx=0, cz=0, r=0.3, y0=0, y1=15)
    base = {
        "id": "st",
        "survey_id": "sv",
        "cls": StructureClass.POLE,
        "name": "mast",
        "confidence": 0.9,
        "primitive": prim,
    }

    assert Structure(**base, state=ReviewState.ACCEPTED).occludes
    assert not Structure(**base, state=ReviewState.PENDING).occludes
    assert not Structure(**base, state=ReviewState.REJECTED).occludes
    # Seasonal is toggled per run rather than occluding unconditionally.
    assert not Structure(**base, state=ReviewState.SEASONAL).occludes


def test_rejection_reasons_are_typed() -> None:
    """An untyped rejection loses information you will want next year."""
    assert {r.value for r in RejectReason} == {"noise", "transient", "duplicate"}


def test_porosity_is_bounded() -> None:
    prim = CylinderPrim(cx=0, cz=0, r=0.3, y0=0, y1=15)
    with pytest.raises(ValidationError):
        Structure(
            id="st",
            survey_id="sv",
            cls=StructureClass.FENCE,
            name="f",
            confidence=0.5,
            primitive=prim,
            porosity=1.5,
        )


def test_site_alpha_fixture_parses_and_matches_the_inventory(site_alpha_path) -> None:
    """The committed fixture is valid and holds what explained 4.1 describes."""
    site = SiteFixture.model_validate(json.loads(site_alpha_path.read_text()))

    assert site.width_m == 132.0
    assert site.depth_m == 82.0

    counts: dict[str, int] = {}
    for s in site.structures:
        counts[s.cls] = counts.get(s.cls, 0) + 1
    assert counts == {"pole": 6, "fence": 4, "stand": 1, "building": 1, "vegetation": 2}

    fences = [s for s in site.structures if s.cls == "fence"]
    assert all(f.porosity == 0.85 for f in fences)
    assert all(isinstance(f.primitive, ExtrudedPolyline) for f in fences)

    trees = [s for s in site.structures if s.cls == "vegetation"]
    assert all(t.seasonal for t in trees), "vegetation must be flagged seasonal"

    poles = [s for s in site.structures if s.cls == "pole"]
    assert all(p.mountable for p in poles)
    assert all(isinstance(p.primitive, CylinderPrim) for p in poles)
