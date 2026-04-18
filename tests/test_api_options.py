"""Tests for PATCH /api/routes/<id>/options (M3a)."""

import json


def _create_route(client, title="T"):
    r = client.post("/api/routes", json={"title": title},
                    content_type="application/json")
    return r.get_json()["id"]


def test_patch_options_sets_round_trip(client):
    rid = _create_route(client)
    resp = client.patch(f"/api/routes/{rid}/options",
                        json={"round_trip": True})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["round_trip"] == 1


def test_patch_options_sets_preset_and_costing_options(client):
    rid = _create_route(client)
    resp = client.patch(f"/api/routes/{rid}/options", json={
        "costing_preset": "gravel-mtb",
        "costing_options": {"use_hills": 0.8, "bicycle_type": "Mountain"},
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["costing_preset"] == "gravel-mtb"
    assert json.loads(body["costing_options"]) == {
        "use_hills": 0.8, "bicycle_type": "Mountain",
    }


def test_patch_options_rejects_unknown_preset(client):
    rid = _create_route(client)
    resp = client.patch(f"/api/routes/{rid}/options",
                        json={"costing_preset": "not-real"})
    assert resp.status_code == 400
    assert "preset" in resp.get_json()["error"].lower()


def test_patch_options_sets_profile(client):
    rid = _create_route(client)
    resp = client.patch(f"/api/routes/{rid}/options", json={"profile": "pedestrian"})
    assert resp.status_code == 200
    assert resp.get_json()["profile"] == "pedestrian"


def test_patch_options_sets_max_gradient_warn(client):
    rid = _create_route(client)
    resp = client.patch(f"/api/routes/{rid}/options",
                        json={"max_gradient_warn": 10.0})
    assert resp.status_code == 200
    assert resp.get_json()["max_gradient_warn"] == 10.0


def test_patch_options_404_on_unknown_route(client):
    resp = client.patch("/api/routes/99999/options", json={"round_trip": True})
    assert resp.status_code == 404


def test_patch_options_invalidates_legs_when_geometry_changes(client):
    """Changing a geometry-affecting option drops cached legs so the
    Analysis page gates on a fresh Regenerate."""
    from server.models import waypoints as wp_model
    rid = _create_route(client)
    # Seed with a fake leg so we can observe the invalidation.
    wp_model.replace_legs(rid, [{
        "from_position": 0, "to_position": 1,
        "distance_m": 100.0, "duration_s": 30.0, "polyline": "x",
    }])
    assert len(wp_model.list_legs(rid)) == 1
    resp = client.patch(f"/api/routes/{rid}/options",
                        json={"costing_preset": "gravel-mtb"})
    assert resp.status_code == 200
    assert wp_model.list_legs(rid) == []
