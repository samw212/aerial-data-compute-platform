"""TypeScript type generation. Build spec 4; M0.

The generated file is gitignored, so this does not compare against a committed
copy. It regenerates into a temporary path and checks that the contracts the
frontend actually needs came through — that the generator has not silently
stopped emitting a model after a contracts change.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "scripts" / "generate_ts_types.py"


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> str:
    target = tmp_path_factory.mktemp("ts") / "contracts.ts"
    subprocess.run(
        [sys.executable, str(GENERATOR), str(target)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return target.read_text(encoding="utf-8")


def test_header_marks_the_file_as_generated(generated: str) -> None:
    """Nobody should edit this file and expect the edit to survive."""
    assert "Do not edit" in generated
    assert "make contracts-ts" in generated


@pytest.mark.parametrize(
    "name",
    [
        "CameraSpec",
        "CoverageRequest",
        "CoverageStats",
        "CoverageRun",
        "Structure",
        "MountPoint",
        "Scenario",
        "Tent",
        "Survey",
        "SourceImage",
        "Measurement",
        "Job",
        "JobProgress",
        "Vec3",
        "BoxPrim",
        "CylinderPrim",
        "ExtrudedPolyline",
    ],
)
def test_every_frontend_model_is_emitted(generated: str, name: str) -> None:
    assert f"export interface {name} {{" in generated


@pytest.mark.parametrize(
    "name", ["DoriTier", "ReviewState", "StructureClass", "GeorefMethod", "JobStatus"]
)
def test_enums_become_string_literal_unions(generated: str, name: str) -> None:
    """String unions, not TypeScript enums: they compare equal to the JSON."""
    assert f"export type {name} =" in generated


def test_primitive_is_a_discriminated_union(generated: str) -> None:
    assert "export type Primitive = BoxPrim | CylinderPrim | ExtrudedPolyline;" in generated
    assert 'kind: "box"' in generated
    assert 'kind: "cylinder"' in generated
    assert 'kind: "polyline"' in generated


def test_optional_fields_are_marked_optional(generated: str) -> None:
    """A required field rendered optional would let the viewer omit it silently."""
    assert "mount_structure_id?: string | null;" in generated
    assert "id: string;" in generated


def test_uncertainty_is_not_optional_in_typescript(generated: str) -> None:
    """measurement.uncertainty is required on both sides of the wire."""
    start = generated.index("export interface Measurement {")
    body = generated[start : generated.index("}", start)]
    assert "uncertainty: number;" in body, body
