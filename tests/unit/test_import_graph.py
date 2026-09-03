"""T14: dependency direction. Build spec 3.2, 6.6.

    apps/* -> packages/* -> packages/contracts. Never the reverse.

One of the two tests build spec 18 says pays for itself repeatedly. It is cheap,
it is unambiguous, and the violation it catches — a package reaching back into an
app, or the kernel importing a database session — is the kind that is easy to add
and very expensive to unpick later.

The check is static: it parses imports rather than importing the modules, so a
violation is caught even in a module that would fail to import for another reason.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

PACKAGE_DIRS = {
    "groma_contracts": REPO_ROOT / "packages" / "contracts",
    "groma_geo": REPO_ROOT / "packages" / "geo",
    "groma_coverage": REPO_ROOT / "packages" / "coverage",
    "groma_capture": REPO_ROOT / "packages" / "capture",
    "groma_recon": REPO_ROOT / "packages" / "recon",
    "groma_tiles": REPO_ROOT / "packages" / "tiles",
    "groma_segment": REPO_ROOT / "packages" / "segment",
}

APP_MODULES = {"groma_api", "groma_worker", "groma_cli"}

# Modules that must never appear anywhere under packages/coverage. The kernel has
# to run identically in the worker, the CLI and the browser via WASM, and each of
# these would tie it to one of those.
KERNEL_FORBIDDEN = {
    "asyncio",
    "fastapi",
    "logging",
    "pydantic_settings",
    "psycopg",
    "redis",
    "requests",
    "sqlalchemy",
    "httpx",
    "arq",
}


def python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def imported_roots(path: Path) -> set[str]:
    """Top-level module names imported by a file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # Relative imports stay inside their own package by definition.
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("package", sorted(PACKAGE_DIRS))
def test_t14_packages_never_import_apps(package: str) -> None:
    """No packages/* module imports an apps/* module."""
    offenders: list[str] = []
    for path in python_files(PACKAGE_DIRS[package]):
        bad = imported_roots(path) & APP_MODULES
        if bad:
            offenders.append(f"{path.relative_to(REPO_ROOT)} imports {sorted(bad)}")
    assert not offenders, "packages must not depend on apps:\n" + "\n".join(offenders)


def test_t14_contracts_depends_on_nothing_in_groma() -> None:
    """packages/contracts is the root of the graph and imports no other groma package."""
    others = set(PACKAGE_DIRS) - {"groma_contracts"} | APP_MODULES
    offenders: list[str] = []
    for path in python_files(PACKAGE_DIRS["groma_contracts"]):
        bad = imported_roots(path) & others
        if bad:
            offenders.append(f"{path.relative_to(REPO_ROOT)} imports {sorted(bad)}")
    assert not offenders, "contracts must depend on nothing else:\n" + "\n".join(offenders)


def test_t14_geo_depends_only_on_contracts() -> None:
    """packages/geo sits directly above contracts."""
    forbidden = set(PACKAGE_DIRS) - {"groma_contracts", "groma_geo"} | APP_MODULES
    offenders: list[str] = []
    for path in python_files(PACKAGE_DIRS["groma_geo"]):
        bad = imported_roots(path) & forbidden
        if bad:
            offenders.append(f"{path.relative_to(REPO_ROOT)} imports {sorted(bad)}")
    assert not offenders, "geo may only use contracts:\n" + "\n".join(offenders)


def test_t14_coverage_depends_only_on_contracts_and_geo() -> None:
    """The kernel's dependencies are contracts, geo and NumPy."""
    forbidden = (
        set(PACKAGE_DIRS)
        - {
            "groma_contracts",
            "groma_geo",
            "groma_coverage",
        }
        | APP_MODULES
    )
    offenders: list[str] = []
    for path in python_files(PACKAGE_DIRS["groma_coverage"]):
        bad = imported_roots(path) & forbidden
        if bad:
            offenders.append(f"{path.relative_to(REPO_ROOT)} imports {sorted(bad)}")
    assert not offenders, "coverage may only use contracts and geo:\n" + "\n".join(offenders)


def test_kernel_stays_pure() -> None:
    """packages/coverage has no I/O, no framework, no logging.

    fixtures.py is the exception and is excluded by name: it reads a site fixture
    from disk, which is why nothing else in the package imports it.
    """
    offenders: list[str] = []
    for path in python_files(PACKAGE_DIRS["groma_coverage"]):
        if path.name == "fixtures.py":
            continue
        bad = imported_roots(path) & KERNEL_FORBIDDEN
        if bad:
            offenders.append(f"{path.relative_to(REPO_ROOT)} imports {sorted(bad)}")
    assert not offenders, (
        "the coverage kernel must stay pure so it runs identically in the worker, "
        "the CLI and the browser (CLAUDE.md, Architecture):\n" + "\n".join(offenders)
    )


def test_kernel_does_not_read_the_filesystem() -> None:
    """No module in the kernel opens a file, `fixtures.py` aside."""
    offenders: list[str] = []
    for path in python_files(PACKAGE_DIRS["groma_coverage"]):
        if path.name == "fixtures.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "open":
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} calls open()")
        if "pathlib" in imported_roots(path):
            offenders.append(f"{path.relative_to(REPO_ROOT)} imports pathlib")
    assert not offenders, "the kernel does no I/O:\n" + "\n".join(offenders)


def test_every_package_can_import_contracts() -> None:
    """M0's completion criterion: contracts is importable from every package."""
    import importlib

    for package in PACKAGE_DIRS:
        module = importlib.import_module(package)
        assert module is not None
    from groma_contracts import CONTRACTS_VERSION

    assert CONTRACTS_VERSION
