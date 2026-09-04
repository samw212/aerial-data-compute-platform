"""Author fixtures/sites/site_alpha.json.

site_alpha is the hand-authored proxy model that everything downstream is measured
against: the coverage golden (T13), the synthetic point cloud and rendered survey
(M2, build spec 16), and the extraction recovery test (build spec 12.5).

The inventory comes from explained 4.1, which lists what the proxy model of a
sports ground looks like:

    6 x light mast    cylinder, radius 0.28 m, height 15.2 m
    4 x fence run     vertical polyline, height 2.4 m, thickness 0.12 m, porosity 0.85
    1 x spectator stand   box, 44 x 6 x 6 m
    1 x pavilion      box, 18 x 8 x 4.5 m
    2 x tree          box, 6.4 x 6.4 x 8 m, flagged seasonal
    1 x terrain       height grid at 0.5 m spacing

The site extent is 132 x 82 m, from the performance target in build spec 6.4
("173,184 cells (0.25 m over 132 x 82 m)"). A regulation 105 x 68 m pitch sits
inside it, which is also what the M12 measurement criterion expects to measure.

Positions are authored here rather than in the JSON so that the constraints between
them — masts inside the fence, stand clear of the touchline — are visible and stay
true if a dimension changes. Run `python scripts/author_site_alpha.py` to rewrite
the fixture.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "fixtures" / "sites" / "site_alpha.json"

# Site extent, local ENU metres, centred on the pitch.
#
# The compute frame is Y-up and right-handed with X east, so north is -Z (pan 0
# points along -Z, and geo.ts maps N = origin_y - z). "South" structures therefore
# carry positive z. Getting this backwards puts the stand on the wrong touchline
# and the "south-west" camera in the north-west on every map.
HALF_W = 66.0
HALF_D = 41.0

# Regulation pitch, for the markings the synthetic ortho draws (build spec 16.1).
PITCH_HALF_X = 52.5
PITCH_HALF_Z = 34.0

MAST_RADIUS = 0.28
MAST_HEIGHT = 15.2

FENCE_HEIGHT = 2.4
FENCE_THICKNESS = 0.12
FENCE_POROSITY = 0.85
FENCE_HALF_X = 64.5
FENCE_HALF_Z = 40.5

# The four corner masts carry the cameras in the T13 golden layout. The two
# midfield masts are floodlighting only, and exist so that extraction has to
# separate six cylinders rather than four.
CORNER_MASTS = [
    ("mast_sw", -57.0, 37.0),
    ("mast_se", 57.0, 37.0),
    ("mast_ne", 57.0, -37.0),
    ("mast_nw", -57.0, -37.0),
]
MIDFIELD_MASTS = [
    ("mast_mid_s", 0.0, 38.0),
    ("mast_mid_n", 0.0, -38.0),
]


def cylinder(cx: float, cz: float, r: float, y0: float, y1: float) -> dict[str, object]:
    return {"kind": "cylinder", "cx": cx, "cz": cz, "r": r, "y0": y0, "y1": y1}


def box(
    cx: float, cy: float, cz: float, hx: float, hy: float, hz: float, yaw: float = 0.0
) -> dict[str, object]:
    return {
        "kind": "box",
        "cx": cx,
        "cy": cy,
        "cz": cz,
        "hx": hx,
        "hy": hy,
        "hz": hz,
        "yaw": yaw,
    }


def polyline(
    points: list[tuple[float, float]], y0: float, y1: float, thickness: float
) -> dict[str, object]:
    return {
        "kind": "polyline",
        "points": [list(p) for p in points],
        "y0": y0,
        "y1": y1,
        "thickness": thickness,
    }


def build() -> dict[str, object]:
    structures: list[dict[str, object]] = []

    for name, x, z in CORNER_MASTS + MIDFIELD_MASTS:
        structures.append(
            {
                "name": name,
                "cls": "pole",
                "primitive": cylinder(x, z, MAST_RADIUS, 0.0, MAST_HEIGHT),
                "porosity": 0.0,
                "mountable": True,
                "seasonal": False,
            }
        )

    # Four straight perimeter runs, each its own structure. Post-processing merges
    # collinear clusters into runs like these (build spec 12.3), so the authored
    # truth has to be four, not forty.
    corners = {
        "fence_s": [(-FENCE_HALF_X, FENCE_HALF_Z), (FENCE_HALF_X, FENCE_HALF_Z)],
        "fence_e": [(FENCE_HALF_X, FENCE_HALF_Z), (FENCE_HALF_X, -FENCE_HALF_Z)],
        "fence_n": [(FENCE_HALF_X, -FENCE_HALF_Z), (-FENCE_HALF_X, -FENCE_HALF_Z)],
        "fence_w": [(-FENCE_HALF_X, -FENCE_HALF_Z), (-FENCE_HALF_X, FENCE_HALF_Z)],
    }
    for name, points in corners.items():
        structures.append(
            {
                "name": name,
                "cls": "fence",
                "primitive": polyline(points, 0.0, FENCE_HEIGHT, FENCE_THICKNESS),
                "porosity": FENCE_POROSITY,
                "mountable": False,
                "seasonal": False,
            }
        )

    # Spectator stand, 44 x 6 x 6, along the south touchline (+Z) and clear of it.
    structures.append(
        {
            "name": "stand_south",
            "cls": "stand",
            "primitive": box(cx=0.0, cy=3.0, cz=37.0, hx=22.0, hy=3.0, hz=3.0),
            "porosity": 0.0,
            "mountable": True,
            "seasonal": False,
        }
    )

    # Pavilion, 18 x 8 x 4.5, on the west margin with its long axis along Z.
    # It cannot go on the north margin: only 7 m separates the pitch from the site
    # edge there, and the building is 8 m deep.
    structures.append(
        {
            "name": "pavilion",
            "cls": "building",
            "primitive": box(cx=-58.0, cy=2.25, cz=0.0, hx=4.0, hy=2.25, hz=9.0),
            "porosity": 0.0,
            "mountable": True,
            "seasonal": False,
        }
    )

    # Two trees, 6.4 x 6.4 x 8, on the north margin (-Z), flagged seasonal: a
    # February survey and a July report describe different sites, so coverage is
    # computed both ways.
    for name, x, z in (("tree_east", 44.0, -37.3), ("tree_west", -20.0, -37.3)):
        structures.append(
            {
                "name": name,
                "cls": "vegetation",
                "primitive": box(cx=x, cy=4.0, cz=z, hx=3.2, hy=4.0, hz=3.2),
                "porosity": 0.0,
                "mountable": False,
                "seasonal": True,
            }
        )

    return {
        "name": "site_alpha",
        "srid": 2326,
        "origin": {
            "srid": 2326,
            "x": 833000.0,
            "y": 817000.0,
            "z": 0.0,
            "height_datum": "orthometric_mpd",
        },
        "x_min": -HALF_W,
        "x_max": HALF_W,
        "z_min": -HALF_D,
        "z_max": HALF_D,
        "pitch": {
            "half_x": PITCH_HALF_X,
            "half_z": PITCH_HALF_Z,
            "nominal_length_m": 2 * PITCH_HALF_X,
            "nominal_width_m": 2 * PITCH_HALF_Z,
        },
        "structures": structures,
    }


def validate(site: dict[str, object]) -> None:
    """Check the constraints the layout is supposed to satisfy.

    Cheap, and it catches the class of edit where a dimension changes and a
    structure quietly ends up outside the fence or on top of a mast.
    """
    structures: list[dict] = site["structures"]  # type: ignore[assignment]

    counts: dict[str, int] = {}
    for s in structures:
        counts[s["cls"]] = counts.get(s["cls"], 0) + 1
    expected = {"pole": 6, "fence": 4, "stand": 1, "building": 1, "vegetation": 2}
    if counts != expected:
        raise AssertionError(f"inventory is {counts}, expected {expected} (explained 4.1)")

    for s in structures:
        prim = s["primitive"]
        if prim["kind"] == "cylinder":
            if abs(prim["cx"]) > FENCE_HALF_X or abs(prim["cz"]) > FENCE_HALF_Z:
                raise AssertionError(f"{s['name']} stands outside the perimeter fence")
        if prim["kind"] == "box":
            if abs(prim["cx"]) + prim["hx"] > HALF_W or abs(prim["cz"]) + prim["hz"] > HALF_D:
                raise AssertionError(f"{s['name']} extends beyond the site extent")

    # Nothing on the playing surface.
    for s in structures:
        prim = s["primitive"]
        if prim["kind"] != "box":
            continue
        if (
            abs(prim["cx"]) - prim["hx"] < PITCH_HALF_X
            and abs(prim["cz"]) - prim["hz"] < PITCH_HALF_Z
        ):
            raise AssertionError(f"{s['name']} overlaps the pitch")

    # Masts must not collide with each other.
    poles = [s for s in structures if s["cls"] == "pole"]
    for i, a in enumerate(poles):
        for b in poles[i + 1 :]:
            gap = math.hypot(
                a["primitive"]["cx"] - b["primitive"]["cx"],
                a["primitive"]["cz"] - b["primitive"]["cz"],
            )
            if gap < 1.0:
                raise AssertionError(f"{a['name']} and {b['name']} are {gap:.2f} m apart")


def main() -> None:
    site = build()
    validate(site)
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(site, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {FIXTURE.relative_to(REPO_ROOT)} with {len(site['structures'])} structures")


if __name__ == "__main__":
    main()
