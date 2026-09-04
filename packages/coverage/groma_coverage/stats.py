"""Aggregation over a coverage grid. Build spec 6.3.

Every number a report prints comes from here, once, and is persisted on the
coverage_run. Reports never recompute (build spec 15.2).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from groma_contracts.camera import DORI_PX_PER_M, CameraSpec, DoriTier
from groma_contracts.coverage import CoverageDelta, CoverageStats
from groma_coverage.types import CoverageResult, Grid


def summarise(
    result: CoverageResult,
    cameras: Sequence[CameraSpec] = (),
    tiers: dict[DoriTier, float] | None = None,
) -> CoverageStats:
    """Reduce a coverage grid to the numbers that go in a report.

    Tier areas are cumulative: `observe` counts every cell at 62 px/m or better,
    including the cells that also clear `identify`. Quoting them any other way
    invites a reader to add them up.

    `cameras` is needed only for per_camera_unique_m2, which is keyed by camera id.
    Without it that mapping comes back empty rather than keyed by array index,
    because an index means nothing in a report.
    """
    tier_thresholds = tiers if tiers is not None else DORI_PX_PER_M

    # Only cells inside the facility polygon count. A masked-out cell is not
    # blind and it is not covered; it is not in scope (build spec 6.3, T15).
    scope = result.grid.in_scope()
    ppm = result.ppm[scope]
    count = result.count[scope]
    best = result.best_camera[scope]
    cell_area = result.grid.cell_area_m2
    cells = int(ppm.size)
    area = cells * cell_area

    tier_area = {
        tier: float(np.count_nonzero(ppm >= threshold) * cell_area)
        for tier, threshold in tier_thresholds.items()
    }

    detect_threshold = tier_thresholds[DoriTier.DETECT]
    seen = count > 0
    blind = int(np.count_nonzero(~seen))
    below_detect = int(np.count_nonzero(seen & (ppm < detect_threshold)))

    per_camera: dict[str, float] = {}
    if cameras:
        unique = seen & (count == 1)
        for index, cam in enumerate(cameras):
            n = int(np.count_nonzero(unique & (best == index)))
            per_camera[cam.id] = float(n * cell_area)

    seen_values = ppm[seen]
    mean_ppm = float(seen_values.mean()) if seen_values.size else 0.0

    return CoverageStats(
        kernel_version=result.kernel_version,
        cells=cells,
        cell_area_m2=cell_area,
        area_m2=area,
        tier_area_m2=tier_area,
        below_detect_m2=float(below_detect * cell_area),
        blind_m2=float(blind * cell_area),
        redundant_2plus_m2=float(np.count_nonzero(count >= 2) * cell_area),
        per_camera_unique_m2=per_camera,
        mean_ppm=mean_ppm,
    )


def compare(
    a: CoverageResult,
    b: CoverageResult,
    run_a: str = "a",
    run_b: str = "b",
    tiers: dict[DoriTier, float] | None = None,
) -> CoverageDelta:
    """What changed between two runs.

    `newly_blind_m2` is not the change in blind area. Erecting tents can blind one
    corner while a re-aimed camera opens another, and the net figure hides both.
    The scenario comparison in a report quotes the newly-blind area because that is
    the area someone has to do something about.
    """
    if a.grid != b.grid:
        raise ValueError(
            "coverage runs are on different grids; compare requires the same extent and spacing"
        )
    if a.kernel_version != b.kernel_version:
        raise ValueError(
            f"kernel version differs between runs ({a.kernel_version} vs "
            f"{b.kernel_version}); recompute both before comparing"
        )

    tier_thresholds = tiers if tiers is not None else DORI_PX_PER_M
    cell_area = a.grid.cell_area_m2
    scope = a.grid.in_scope()
    ppm_a = a.ppm[scope]
    ppm_b = b.ppm[scope]

    tier_delta = {
        tier: float(
            (np.count_nonzero(ppm_b >= threshold) - np.count_nonzero(ppm_a >= threshold))
            * cell_area
        )
        for tier, threshold in tier_thresholds.items()
    }

    seen_a = a.count[scope] > 0
    seen_b = b.count[scope] > 0
    blind_a = int(np.count_nonzero(~seen_a))
    blind_b = int(np.count_nonzero(~seen_b))

    mean_a = float(ppm_a[seen_a].mean()) if np.any(seen_a) else 0.0
    mean_b = float(ppm_b[seen_b].mean()) if np.any(seen_b) else 0.0

    return CoverageDelta(
        run_a=run_a,
        run_b=run_b,
        kernel_version=a.kernel_version,
        tier_area_delta_m2=tier_delta,
        blind_delta_m2=float((blind_b - blind_a) * cell_area),
        newly_blind_m2=float(np.count_nonzero(seen_a & ~seen_b) * cell_area),
        newly_covered_m2=float(np.count_nonzero(~seen_a & seen_b) * cell_area),
        mean_ppm_delta=mean_b - mean_a,
    )


def blind_polygons(
    result: CoverageResult, min_area_m2: float = 4.0
) -> list[list[tuple[float, float]]]:
    """Trace outlines around the regions no camera can see.

    Returns plan-view rings in local ENU metres. Regions smaller than
    `min_area_m2` are dropped: a report full of half-metre specks between two
    cameras is noise, and the operator cannot act on it. Cells outside the grid's
    mask are never blind: they are out of scope (T15).

    This is a connected-component trace rather than marching squares. Blind cells
    are a discrete set, and the boundary that matters is the boundary of the cells
    themselves — an interpolated iso-contour would imply sub-cell precision the
    grid does not have. Where a smooth contour is wanted for a plan drawing, the
    renderer smooths this ring; the area quoted in the report comes from the cell
    count, never from the polygon.
    """
    blind = (result.count == 0) & result.grid.in_scope()
    if not np.any(blind):
        return []

    grid = result.grid
    cell_area = grid.cell_area_m2
    labels, sizes = _label_components(blind)

    rings: list[list[tuple[float, float]]] = []
    for label, size in sizes.items():
        if size * cell_area < min_area_m2:
            continue
        rings.append(_component_ring(labels == label, grid))
    return rings


def _label_components(mask: np.ndarray) -> tuple[np.ndarray, dict[int, int]]:
    """Four-connected component labelling, breadth-first, no SciPy dependency."""
    nz, nx = mask.shape
    labels = np.zeros((nz, nx), dtype=np.int32)
    sizes: dict[int, int] = {}
    next_label = 0

    for j0 in range(nz):
        for i0 in range(nx):
            if not mask[j0, i0] or labels[j0, i0] != 0:
                continue
            next_label += 1
            stack = [(j0, i0)]
            labels[j0, i0] = next_label
            size = 0
            while stack:
                j, i = stack.pop()
                size += 1
                for dj, di in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nj, ni = j + dj, i + di
                    if 0 <= nj < nz and 0 <= ni < nx and mask[nj, ni] and labels[nj, ni] == 0:
                        labels[nj, ni] = next_label
                        stack.append((nj, ni))
            sizes[next_label] = size

    return labels, sizes


def _component_ring(mask: np.ndarray, grid: Grid) -> list[tuple[float, float]]:
    """The axis-aligned outline of one component, as a closed ring.

    Walks the boundary edges of the cell squares and stitches them into a loop.
    Two blind regions that touch only at a corner share that corner between two
    outgoing edges, and this returns the first loop it can close rather than both;
    the area in the report comes from the cell count, so the figure stays right
    even where the drawn outline is incomplete.
    """
    half = 0.5 * grid.spacing
    nz, nx = mask.shape

    def corner(i: int, j: int, dx: int, dz: int) -> tuple[float, float]:
        x = grid.x_min + i * grid.spacing + dx * half
        z = grid.z_min + j * grid.spacing + dz * half
        return (round(x, 6), round(z, 6))

    edges: dict[tuple[float, float], tuple[float, float]] = {}
    for j in range(nz):
        for i in range(nx):
            if not mask[j, i]:
                continue
            # Edges are emitted anticlockwise around each cell, so that shared
            # edges between two blind cells cancel and only the outline survives.
            if j == 0 or not mask[j - 1, i]:
                edges[corner(i, j, -1, -1)] = corner(i, j, 1, -1)
            if i == nx - 1 or not mask[j, i + 1]:
                edges[corner(i, j, 1, -1)] = corner(i, j, 1, 1)
            if j == nz - 1 or not mask[j + 1, i]:
                edges[corner(i, j, 1, 1)] = corner(i, j, -1, 1)
            if i == 0 or not mask[j, i - 1]:
                edges[corner(i, j, -1, 1)] = corner(i, j, -1, -1)

    if not edges:
        return []

    start = next(iter(edges))
    ring = [start]
    current = edges[start]
    while current != start and current in edges:
        ring.append(current)
        current = edges[current]
    ring.append(start)
    return ring


__all__ = ["blind_polygons", "compare", "summarise"]
