"""Tests for server.routing.valhalla_client."""

import json
import os
from unittest.mock import patch, MagicMock

import pytest

from server.routing import valhalla_client as vc

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _mock_requests_post(response_json, status_code=200):
    m = MagicMock()
    m.status_code = status_code
    m.ok = status_code < 400
    m.json.return_value = response_json
    m.text = ""
    if status_code >= 400:
        import json as _json
        m.text = _json.dumps(response_json)
    return m


def test_request_body_shape():
    body = vc.build_request_body(
        waypoints=[(-27.4, 152.9), (-27.5, 152.8)],
        profile="bicycle",
        costing_options={"use_hills": 0.5},
    )
    assert body["costing"] == "bicycle"
    assert body["costing_options"]["bicycle"]["use_hills"] == 0.5
    # Every location carries a search radius so near-road pins snap reliably.
    assert body["locations"] == [
        {"lat": -27.4, "lon": 152.9, "type": "break", "radius": 100},
        {"lat": -27.5, "lon": 152.8, "type": "break", "radius": 100},
    ]
    assert body["elevation_interval"] == 10


def test_request_body_applies_radius_to_every_location():
    body = vc.build_request_body(
        waypoints=[(0, 0), (1, 1), (2, 2)],
        profile="bicycle",
        kinds=["stop", "waypoint", "stop"],
        round_trip=True,
    )
    # All three original locations + the synthetic round-trip close.
    assert len(body["locations"]) == 4
    for loc in body["locations"]:
        assert loc["radius"] == 100


def test_call_success(app):
    with open(os.path.join(FIXTURES, "valhalla_response_sample.json")) as f:
        fake = json.load(f)
    with app.app_context(), patch("server.routing.valhalla_client.requests.post",
                                  return_value=_mock_requests_post(fake)):
        resp = vc.call_route(
            waypoints=[(-27.4, 152.9), (-27.5, 152.8), (-27.6, 152.7)],
            profile="bicycle",
        )
    assert resp["trip"]["legs"][0]["summary"]["length"] == 2.0
    assert len(resp["trip"]["legs"]) == 2


def test_call_http_error(app):
    with app.app_context(), patch("server.routing.valhalla_client.requests.post",
                                  return_value=_mock_requests_post({"error": "nope"}, 400)):
        with pytest.raises(vc.ValhallaError):
            vc.call_route(
                waypoints=[(0.0, 0.0), (0.0, 0.0)],
                profile="bicycle",
            )


def test_call_fewer_than_two_waypoints_rejected(app):
    with app.app_context():
        with pytest.raises(ValueError):
            vc.call_route(waypoints=[(0.0, 0.0)], profile="bicycle")


def test_build_request_body_every_location_is_break_regardless_of_kind():
    """Per-leg routing: every pin is sent as type=break so Valhalla
    returns one leg per adjacent pair. The `kinds` argument is
    accepted for callers but ignored when constructing the request —
    stop vs waypoint remains a UI/recipe concept, not a routing one."""
    body = vc.build_request_body(
        waypoints=[(-27.4, 152.9), (-27.41, 152.91), (-27.42, 152.92), (-27.43, 152.93)],
        profile="bicycle",
        kinds=["stop", "waypoint", "stop", "waypoint"],
    )
    types = [loc["type"] for loc in body["locations"]]
    assert types == ["break", "break", "break", "break"]


def test_build_request_body_defaults_to_all_breaks():
    """Legacy callers (no kinds) also get all breaks."""
    body = vc.build_request_body(
        waypoints=[(0, 0), (1, 1), (2, 2)],
        profile="bicycle",
    )
    assert all(loc["type"] == "break" for loc in body["locations"])


def test_parse_legs_decodes_shape():
    with open(os.path.join(FIXTURES, "valhalla_response_sample.json")) as f:
        fake = json.load(f)
    legs = vc.parse_legs(fake)
    assert len(legs) == 2
    assert legs[0]["distance_m"] == 2000.0  # km → m
    assert legs[0]["duration_s"] == 360.0
    assert legs[0]["polyline"] == fake["trip"]["legs"][0]["shape"]
