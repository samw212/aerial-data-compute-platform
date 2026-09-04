"""M4 acceptance: the API over real PostGIS. Build spec 17, 5 (constraints), 7.

Every expected value here is either a stored input read back, a 4xx the spec
names, or a kernel figure computed independently through the fixture path.
"""

from __future__ import annotations

import pytest

from groma_contracts.camera import DORI_TIERS_HARDEST_FIRST
from groma_coverage.fixtures import golden_cameras, load_site, site_occluders
from groma_coverage.kernel import KERNEL_VERSION, compute_coverage
from groma_coverage.stats import summarise
from groma_coverage.types import Grid

pytestmark = pytest.mark.integration

PITCH = [(-52.5, -34.0), (52.5, -34.0), (52.5, 34.0), (-52.5, 34.0)]


def test_health_reports_database_and_versions(anon) -> None:
    r = anon.get("/api/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["checks"]["database"]["ok"] is True
    assert body["kernel_version"] == KERNEL_VERSION


def test_unauthenticated_is_refused(anon, seeded) -> None:
    assert anon.get(f"/api/venues/{seeded['venue_id']}").status_code == 401


def test_viewer_cannot_review(viewer, admin, seeded) -> None:
    sid = seeded["survey_id"]
    structures = admin.get(f"/api/surveys/{sid}/structures").json()["items"]
    target = next(s for s in structures if s["name"] == "mast_sw")
    r = viewer.patch(
        f"/api/structures/{target['id']}", json={"state": "rejected", "reject_reason": "noise"}
    )
    assert r.status_code == 403


def test_portfolio_lists_the_seeded_venue(admin, seeded) -> None:
    r = admin.get(f"/api/orgs/{seeded['org_id']}/venues")
    assert r.status_code == 200, r.text
    venues = r.json()
    assert [v["venue"]["name"] for v in venues] == ["Sha Tin Sports Ground"]
    assert venues[0]["facility_count"] == 1
    assert venues[0]["latest_survey_flown_at"] == "2025-11-14"


def test_scenario_round_trips_local_coordinates(admin, seeded, repo_root) -> None:
    """Cameras stored as PostGIS points in Hong Kong Grid come back in local ENU
    to the millimetre: the rebase is the whole point of the geometry layer."""
    site = load_site(repo_root / "fixtures" / "sites" / "site_alpha.json")
    expected = {c.name: c for c in golden_cameras(site)}
    sc = admin.get(f"/api/scenarios/{seeded['scenario_id']}").json()
    assert len(sc["cameras"]) == 4
    for cam in sc["cameras"]:
        e = expected[cam["name"]]
        assert abs(cam["position"]["x"] - e.position.x) < 1e-3
        assert abs(cam["position"]["y"] - e.position.y) < 1e-3
        assert abs(cam["position"]["z"] - e.position.z) < 1e-3
        assert cam["pan_deg"] == pytest.approx(e.pan_deg)
        assert cam["mount_structure_id"] is not None


def test_coverage_run_matches_the_kernel_on_the_facility_grid(admin, seeded, repo_root) -> None:
    """The API's persisted numbers equal a direct kernel run over the same
    facility polygon, occluders and cameras. Independent path: fixture loaders."""
    site = load_site(repo_root / "fixtures" / "sites" / "site_alpha.json")
    cams = golden_cameras(site)
    grid = Grid.from_facility(PITCH, 0.5)
    ref = summarise(
        compute_coverage(cams, site_occluders(site, include_seasonal=True), grid, None, 1.6, True),
        cams,
    )

    r = admin.post(
        f"/api/scenarios/{seeded['scenario_id']}/coverage",
        json={"grid_spacing_m": 0.5, "include_tents": True},
    )
    assert r.status_code == 201, r.text
    run = r.json()
    assert run["kernel_version"] == KERNEL_VERSION
    stats = run["stats"]
    assert stats["cells"] == ref.cells
    assert stats["area_m2"] == pytest.approx(ref.area_m2)
    for tier in DORI_TIERS_HARDEST_FIRST:
        assert stats["tier_area_m2"][tier.value] == pytest.approx(ref.tier_area_m2[tier])
    assert stats["blind_m2"] == pytest.approx(ref.blind_m2)
    assert stats["redundant_2plus_m2"] == pytest.approx(ref.redundant_2plus_m2)
    # Percentages are of the pitch, so the area is the pitch, not the site rectangle.
    assert abs(stats["area_m2"] - 105 * 68) / (105 * 68) < 0.005

    png = admin.get(f"/api/coverage-runs/{run['id']}/grid.png")
    assert png.status_code == 200 and png.content[:8] == b"\x89PNG\r\n\x1a\n"
    npz = admin.get(f"/api/coverage-runs/{run['id']}/grid.npz")
    assert npz.status_code == 200 and len(npz.content) > 1000


def test_tents_reduce_coverage_and_compare_reports_newly_blind(admin, seeded) -> None:
    sid = seeded["scenario_id"]
    base = admin.post(
        f"/api/scenarios/{sid}/coverage", json={"grid_spacing_m": 1.0, "include_tents": False}
    ).json()
    r = admin.post(f"/api/scenarios/{sid}/tents:preset")
    assert r.status_code == 201 and len(r.json()) == 12
    tents = admin.post(
        f"/api/scenarios/{sid}/coverage", json={"grid_spacing_m": 1.0, "include_tents": True}
    ).json()
    assert tents["stats"]["blind_m2"] > base["stats"]["blind_m2"]
    d = admin.post("/api/coverage/compare", json={"run_a": base["id"], "run_b": tents["id"]})
    assert d.status_code == 200, d.text
    assert d.json()["newly_blind_m2"] > 0
    assert d.json()["newly_covered_m2"] == 0
    # Clean up so later tests see the seeded scenario without tents.
    for t in admin.get(f"/api/scenarios/{sid}").json()["tents"]:
        admin.delete(f"/api/tents/{t['id']}")


def test_rejection_must_be_typed(admin, seeded) -> None:
    sid = seeded["survey_id"]
    s = next(
        x
        for x in admin.get(f"/api/surveys/{sid}/structures").json()["items"]
        if x["name"] == "tree_east"
    )
    r = admin.patch(f"/api/structures/{s['id']}", json={"state": "rejected"})
    assert r.status_code == 422
    r = admin.patch(
        f"/api/structures/{s['id']}", json={"state": "rejected", "reject_reason": "transient"}
    )
    assert r.status_code == 200 and r.json()["reject_reason"] == "transient"
    admin.patch(f"/api/structures/{s['id']}", json={"state": "seasonal"})


def test_only_accepted_structures_occlude(admin, seeded) -> None:
    """Rejecting the south stand opens coverage behind it; the occlusion model
    reads state = 'accepted' and nothing else."""
    sid = seeded["scenario_id"]
    survey = seeded["survey_id"]
    before = admin.post(
        f"/api/scenarios/{sid}/coverage", json={"grid_spacing_m": 1.0, "include_tents": False}
    ).json()
    stand = next(
        x
        for x in admin.get(f"/api/surveys/{survey}/structures").json()["items"]
        if x["name"] == "stand_south"
    )
    admin.patch(
        f"/api/structures/{stand['id']}", json={"state": "rejected", "reject_reason": "transient"}
    )
    after = admin.post(
        f"/api/scenarios/{sid}/coverage", json={"grid_spacing_m": 1.0, "include_tents": False}
    ).json()
    admin.patch(f"/api/structures/{stand['id']}", json={"state": "accepted"})
    assert after["stats"]["blind_m2"] <= before["stats"]["blind_m2"]
    assert after["stats"]["tier_area_m2"]["detect"] >= before["stats"]["tier_area_m2"]["detect"]


def test_measurement_refused_without_georef(admin, seeded) -> None:
    venue = seeded["venue_id"]
    r = admin.post(f"/api/venues/{venue}/surveys", json={"name": "scale-free", "georef": "none"})
    assert r.status_code == 201
    sid = r.json()["id"]
    body = {
        "survey_id": sid,
        "kind": "distance",
        "points": [[0, 0, 0], [10, 0, 0]],
        "snap_modes": ["terrain", "terrain"],
        "snap_sigmas_m": [0.02, 0.02],
    }
    assert admin.post("/api/measurements", json=body).status_code == 409


def test_measurement_carries_uncertainty_and_formatting(admin, seeded) -> None:
    body = {
        "survey_id": seeded["survey_id"],
        "kind": "distance",
        "points": [[0, 0, 0], [47.8213, 0, 0]],
        "snap_modes": ["primitive_feature", "primitive_feature"],
        "snap_sigmas_m": [0.003, 0.003],
    }
    r = admin.post("/api/measurements", json=body)
    assert r.status_code == 201, r.text
    mrow = r.json()
    assert mrow["value"] == pytest.approx(47.8213)
    assert mrow["uncertainty"] > 0
    assert "+/-" in mrow["formatted"]
    listed = admin.get(f"/api/venues/{seeded['venue_id']}/measurements").json()
    assert any(abs(x["points"][1][0] - 47.8213) < 1e-3 for x in listed)


def test_immutable_survey_rejects_mutation_but_can_be_superseded(admin, seeded) -> None:
    sid = seeded["survey_id"]
    assert admin.patch(f"/api/surveys/{sid}", json={"name": "renamed"}).status_code == 409
    r = admin.post(f"/api/surveys/{sid}/supersede")
    assert r.status_code == 201
    assert r.json()["status"] == "draft"
    assert admin.get(f"/api/surveys/{sid}").json()["superseded_by"] == r.json()["id"]


def test_mount_on_rejected_structure_is_refused_then_accepted(admin, seeded) -> None:
    survey = seeded["survey_id"]
    venue = seeded["venue_id"]
    mast = next(
        x
        for x in admin.get(f"/api/surveys/{survey}/structures").json()["items"]
        if x["name"] == "mast_mid_n"
    )
    admin.patch(
        f"/api/structures/{mast['id']}", json={"state": "rejected", "reject_reason": "duplicate"}
    )
    body = {
        "position": {"x": 0.0, "y": 14.0, "z": 38.0},
        "structure_id": mast["id"],
        "landed_on": "structure",
        "height_agl_m": 14.0,
    }
    r = admin.post(f"/api/venues/{venue}/mount-points", json=body)
    assert r.status_code == 409
    body["accept_rejected_structure"] = True
    r = admin.post(f"/api/venues/{venue}/mount-points", json=body)
    assert r.status_code == 201, r.text
    assert admin.get(f"/api/surveys/{survey}/structures").json()["items"]
    s = next(
        x
        for x in admin.get(f"/api/surveys/{survey}/structures").json()["items"]
        if x["id"] == mast["id"]
    )
    assert s["state"] == "accepted"


def test_terrain_drop_creates_a_proposed_mast_that_occludes(admin, seeded) -> None:
    venue = seeded["venue_id"]
    sid = seeded["scenario_id"]
    survey = seeded["survey_id"]
    before = admin.post(
        f"/api/scenarios/{sid}/coverage", json={"grid_spacing_m": 1.0, "include_tents": False}
    ).json()
    body = {
        "position": {"x": 20.0, "y": 0.0, "z": 10.0},
        "landed_on": "terrain",
        "height_agl_m": 0.0,
        "proposed_mast_height_m": 12.0,
        "proposed_mast_radius_m": 0.4,
        "label": "proposed mast A",
    }
    r = admin.post(f"/api/venues/{venue}/mount-points", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["origin"] == "proposed_structure"
    proposed = [
        x
        for x in admin.get(f"/api/surveys/{survey}/structures").json()["items"]
        if x["name"] == "proposed mast A"
    ]
    assert (
        len(proposed) == 1
        and proposed[0]["state"] == "accepted"
        and proposed[0]["origin"] == "manual"
    )
    after = admin.post(
        f"/api/scenarios/{sid}/coverage", json={"grid_spacing_m": 1.0, "include_tents": False}
    ).json()
    assert after["stats"]["blind_m2"] >= before["stats"]["blind_m2"]
    admin.patch(
        f"/api/structures/{proposed[0]['id']}",
        json={"state": "rejected", "reject_reason": "transient"},
    )


def test_keyset_pagination_walks_every_structure(admin, seeded) -> None:
    sid = seeded["survey_id"]
    seen: list[str] = []
    cursor = None
    while True:
        r = admin.get(
            f"/api/surveys/{sid}/structures",
            params={"limit": 3, **({"cursor": cursor} if cursor else {})},
        )
        page = r.json()
        seen += [x["id"] for x in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) >= 14
