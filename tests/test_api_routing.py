"""Tests for POST /api/routes/<id>/generate."""

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
    """Create a route with stop-waypoint-waypoint-stop. Endpoints are
    auto-break; the two interior 'waypoint' kinds collapse into through
    points, so Valhalla returns only 1 leg (start → end)."""
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


def test_generate_accepts_single_leg_when_interior_waypoints_collapse(client):
    """Regression guard for the 'Valhalla returned 1 legs, expected 3' error.
    With two interior through-type waypoints, Valhalla returns a single leg
    end-to-end, and api_routing must accept that + map it to from_position=0,
    to_position=3 (the break-type endpoints)."""
    rid = _create_route_with_4_pins_mixed_kinds(client)
    leg = encode_polyline(
        [(-27.40, 152.90), (-27.41, 152.91), (-27.42, 152.92), (-27.43, 152.93)],
        precision=6,
    )
    fake_single_leg = {
        "trip": {
            "legs": [{"summary": {"length": 4.0, "time": 1000.0}, "shape": leg}],
            "summary": {"length": 4.0, "time": 1000.0},
        }
    }
    with patch("server.routing.valhalla_client.requests.post") as mock_post:
        mock_post.return_value.ok = True
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = fake_single_leg
        resp = client.post(f"/api/routes/{rid}/generate")
    assert resp.status_code == 200, resp.data
    body = resp.get_json()
    assert body["legs_count"] == 1
    assert body["legs"][0]["from_position"] == 0
    assert body["legs"][0]["to_position"] == 3   # skips the two through-points


def test_generate_stop_waypoint_stop_yields_two_legs(client):
    """Stop-Waypoint-Stop: one interior through waypoint, but the middle
    location is NOT a break — so Valhalla still returns 1 leg end-to-end
    (A -> C via B). Expected legs = break_count (2) - 1 = 1."""
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
    leg = encode_polyline(
        [(-27.40, 152.90), (-27.41, 152.91), (-27.42, 152.92)], precision=6)
    fake = {"trip": {"legs": [{"summary": {"length": 3.0, "time": 600}, "shape": leg}],
                      "summary": {"length": 3.0, "time": 600}}}
    with patch("server.routing.valhalla_client.requests.post") as mock_post:
        mock_post.return_value.ok = True
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = fake
        resp = client.post(f"/api/routes/{rid}/generate")
    assert resp.status_code == 200, resp.data
    body = resp.get_json()
    assert body["legs_count"] == 1
    assert body["legs"][0]["from_position"] == 0
    assert body["legs"][0]["to_position"] == 2
