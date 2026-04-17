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
