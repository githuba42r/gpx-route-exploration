"""Tests for POST /api/routes/<id>/generate."""

import json
import os
from unittest.mock import patch

from server.routing.gpx_writer import encode_polyline

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _fake_valhalla_response():
    """Fake response with two legs whose decoded points are known."""
    leg1 = encode_polyline([(-27.40, 152.90), (-27.405, 152.905), (-27.41, 152.91)], precision=6)
    leg2 = encode_polyline([(-27.41, 152.91), (-27.42, 152.92)], precision=6)
    return {
        "trip": {
            "legs": [
                {"summary": {"length": 1.0, "time": 300.0}, "shape": leg1},
                {"summary": {"length": 0.8, "time": 240.0}, "shape": leg2},
            ],
            "summary": {"length": 1.8, "time": 540.0},
        }
    }


def _create_route_with_three_waypoints(client):
    r = client.post(
        "/api/routes",
        json={"title": "Gen test", "profile": "bicycle"},
        content_type="application/json",
    )
    rid = r.get_json()["id"]
    for name, lat, lon in [("A", -27.40, 152.90), ("B", -27.41, 152.91), ("C", -27.42, 152.92)]:
        client.post(
            f"/api/routes/{rid}/waypoints",
            json={"name": name, "lat": lat, "lon": lon, "kind": "stop"},
        )
    return rid


def test_generate_rejects_when_fewer_than_two_waypoints(client):
    r = client.post(
        "/api/routes",
        json={"title": "No WP"},
        content_type="application/json",
    )
    rid = r.get_json()["id"]
    resp = client.post(f"/api/routes/{rid}/generate")
    assert resp.status_code == 400


def test_generate_writes_legs_and_gpx_file(client, app):
    rid = _create_route_with_three_waypoints(client)
    fake = _fake_valhalla_response()
    with patch("server.routing.valhalla_client.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = fake
        mock_post.return_value.raise_for_status = lambda: None
        resp = client.post(f"/api/routes/{rid}/generate")
    assert resp.status_code == 200, resp.data
    body = resp.get_json()
    assert body["legs_count"] == 2
    assert body["distance_km"] == 1.8
    assert "gpx_url" in body

    # DB: route_legs populated
    r = client.get(f"/api/routes/{rid}/legs")
    assert r.status_code == 200
    legs = r.get_json()
    assert len(legs) == 2
    assert legs[0]["from_position"] == 0 and legs[0]["to_position"] == 1
    assert legs[1]["from_position"] == 1 and legs[1]["to_position"] == 2

    # File: written under DATA_DIR/gpx/<user>/<cat>/<storage_name>
    data_dir = app.config["DATA_DIR"]
    stored = None
    for root, _, files in os.walk(os.path.join(data_dir, "gpx")):
        for f in files:
            if f.endswith(".gpx") and os.path.getsize(os.path.join(root, f)) > 0:
                stored = os.path.join(root, f)
    assert stored, "GPX file was not written"
    content = open(stored).read()
    assert "<trk>" in content and "<trkpt" in content


def test_generate_valhalla_error_returns_502(client):
    rid = _create_route_with_three_waypoints(client)
    with patch("server.routing.valhalla_client.requests.post") as mock_post:
        mock_post.return_value.ok = False
        mock_post.return_value.status_code = 500
        mock_post.return_value.text = '{"error":"upstream fail"}'
        resp = client.post(f"/api/routes/{rid}/generate")
    assert resp.status_code == 502
    body = resp.get_json()
    assert body["error"] == "Upstream routing service failed"
    assert "upstream_url" in body and "/route" in body["upstream_url"]
    assert "upstream_body" in body and "upstream fail" in body["upstream_body"]


def test_generate_success_includes_legs_in_response(client):
    rid = _create_route_with_three_waypoints(client)
    fake = _fake_valhalla_response()
    with patch("server.routing.valhalla_client.requests.post") as mock_post:
        mock_post.return_value.ok = True
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = fake
        resp = client.post(f"/api/routes/{rid}/generate")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "legs" in body and len(body["legs"]) == 2
    assert body["legs"][0]["polyline"] == fake["trip"]["legs"][0]["shape"]


def _create_route_with_4_pins_mixed_kinds(client):
    """Create a 4-pin route with mixed kinds. Per-leg routing sends all
    four as breaks so Valhalla returns 3 legs regardless of kind."""
    r = client.post(
        "/api/routes",
        json={"title": "mixed-kinds", "profile": "bicycle"},
        content_type="application/json",
    )
    rid = r.get_json()["id"]
    for name, lat, lon, kind in [
        ("A",  -27.40, 152.90, "stop"),
        ("B",  -27.41, 152.91, "waypoint"),
        ("C",  -27.42, 152.92, "waypoint"),
        ("D",  -27.43, 152.93, "stop"),
    ]:
        client.post(
            f"/api/routes/{rid}/waypoints",
            json={"name": name, "lat": lat, "lon": lon, "kind": kind},
        )
    return rid


def _mock_valhalla_legs(n_legs):
    """Build a fake Valhalla response with n_legs separate legs."""
    legs = []
    for i in range(n_legs):
        shape = encode_polyline(
            [(-27.40 - 0.01 * i, 152.90 + 0.01 * i),
             (-27.40 - 0.01 * (i + 1), 152.90 + 0.01 * (i + 1))],
            precision=6,
        )
        legs.append({"summary": {"length": 1.0, "time": 300.0}, "shape": shape})
    return {"trip": {"legs": legs,
                      "summary": {"length": n_legs * 1.0, "time": n_legs * 300.0}}}


def test_generate_4_pins_returns_3_legs_regardless_of_kind(client):
    """Per-leg routing: a 4-pin route (any kind mix) returns 3 legs.
    Each leg covers exactly one adjacent pair — no through-collapse."""
    rid = _create_route_with_4_pins_mixed_kinds(client)
    fake = _mock_valhalla_legs(3)
    with patch("server.routing.valhalla_client.requests.post") as mock_post:
        mock_post.return_value.ok = True
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = fake
        resp = client.post(f"/api/routes/{rid}/generate")
    assert resp.status_code == 200, resp.data
    body = resp.get_json()
    assert body["legs_count"] == 3
    from_to = [(l["from_position"], l["to_position"]) for l in body["legs"]]
    assert from_to == [(0, 1), (1, 2), (2, 3)]


def test_generate_stop_waypoint_stop_yields_two_legs(client):
    """A 3-pin route returns 2 legs: (0,1) and (1,2). Kind is irrelevant."""
    r = client.post(
        "/api/routes",
        json={"title": "mixed3", "profile": "bicycle"},
        content_type="application/json",
    )
    rid = r.get_json()["id"]
    for name, lat, lon, kind in [
        ("A",  -27.40, 152.90, "stop"),
        ("B",  -27.41, 152.91, "waypoint"),
        ("C",  -27.42, 152.92, "stop"),
    ]:
        client.post(
            f"/api/routes/{rid}/waypoints",
            json={"name": name, "lat": lat, "lon": lon, "kind": kind},
        )
    fake = _mock_valhalla_legs(2)
    with patch("server.routing.valhalla_client.requests.post") as mock_post:
        mock_post.return_value.ok = True
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = fake
        resp = client.post(f"/api/routes/{rid}/generate")
    assert resp.status_code == 200, resp.data
    body = resp.get_json()
    assert body["legs_count"] == 2
    from_to = [(l["from_position"], l["to_position"]) for l in body["legs"]]
    assert from_to == [(0, 1), (1, 2)]


def test_generate_uses_resolved_costing_options(client, app, monkeypatch):
    """preset=gravel-mtb flows through to the Valhalla request."""
    rid = client.post("/api/routes", json={"title": "Gravel"},
                      content_type="application/json").get_json()["id"]
    for name, lat, lon in [("A", -27.4, 152.9), ("B", -27.5, 152.8), ("C", -27.6, 152.7)]:
        client.post(f"/api/routes/{rid}/waypoints",
                    json={"kind": "stop", "name": name, "lat": lat, "lon": lon})
    client.patch(f"/api/routes/{rid}/options",
                 json={"costing_preset": "gravel-mtb"})

    captured = {}
    fake = _fake_valhalla_response()

    def fake_call_route(**kwargs):
        captured.update(kwargs)
        return fake

    monkeypatch.setattr("server.blueprints.api_routing.vc.call_route", fake_call_route)
    resp = client.post(f"/api/routes/{rid}/generate")
    assert resp.status_code == 200, resp.get_data(as_text=True)

    co = captured["costing_options"]
    assert co.get("bicycle_type") == "Mountain"
    assert co.get("use_roads", 1.0) < 0.5


def test_generate_custom_preset_uses_stored_costing_options(client, app, monkeypatch):
    """preset=custom uses the persisted costing_options verbatim."""
    rid = client.post("/api/routes", json={"title": "Custom"},
                      content_type="application/json").get_json()["id"]
    for name, lat, lon in [("A", -27.4, 152.9), ("B", -27.5, 152.8), ("C", -27.6, 152.7)]:
        client.post(f"/api/routes/{rid}/waypoints",
                    json={"kind": "stop", "name": name, "lat": lat, "lon": lon})
    client.patch(f"/api/routes/{rid}/options", json={
        "costing_preset": "custom",
        "costing_options": {"use_hills": 0.95, "bicycle_type": "Mountain"},
    })

    captured = {}
    fake = _fake_valhalla_response()

    def fake_call_route(**kwargs):
        captured.update(kwargs)
        return fake

    monkeypatch.setattr("server.blueprints.api_routing.vc.call_route", fake_call_route)
    resp = client.post(f"/api/routes/{rid}/generate")
    assert resp.status_code == 200
    assert captured["costing_options"] == {"use_hills": 0.95, "bicycle_type": "Mountain"}


def test_generate_round_trip_flag_reaches_valhalla(client, app, monkeypatch):
    """round_trip=True is forwarded to the Valhalla client."""
    rid = client.post("/api/routes", json={"title": "Loop"},
                      content_type="application/json").get_json()["id"]
    for name, lat, lon in [("A", -27.4, 152.9), ("B", -27.5, 152.8)]:
        client.post(f"/api/routes/{rid}/waypoints",
                    json={"kind": "stop", "name": name, "lat": lat, "lon": lon})
    client.patch(f"/api/routes/{rid}/options", json={"round_trip": True})

    # Round-trip with 2 waypoints expects 2 legs — use the 2-leg fake.
    captured = {}
    fake = _fake_valhalla_response()

    def fake_call_route(**kwargs):
        captured.update(kwargs)
        return fake

    monkeypatch.setattr("server.blueprints.api_routing.vc.call_route", fake_call_route)
    resp = client.post(f"/api/routes/{rid}/generate")
    assert resp.status_code == 200
    assert captured["round_trip"] is True
