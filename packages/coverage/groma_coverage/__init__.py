"""Groma coverage kernel.

Pure. No I/O, no database, no framework, no logging of user data. It has to run
identically in the worker, the CLI, and the browser via WASM. Keep it that way.
"""

from groma_coverage.kernel import KERNEL_VERSION, compute_coverage
from groma_coverage.occluders import RAY_EPS_M
from groma_coverage.reference import compute_coverage_reference
from groma_coverage.stats import blind_polygons, compare, summarise
from groma_coverage.types import CoverageResult, Grid, Occluder, Terrain

__all__ = [
    "KERNEL_VERSION",
    "RAY_EPS_M",
    "CoverageResult",
    "Grid",
    "Occluder",
    "Terrain",
    "blind_polygons",
    "compare",
    "compute_coverage",
    "compute_coverage_reference",
    "summarise",
]
