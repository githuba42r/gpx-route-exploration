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
    # Fixture is a live Valhalla capture — assert it round-trips rather
    # than hard-coding distances that break on regeneration.
    assert resp["trip"]["legs"][0]["summary"]["length"] == \
        fake["trip"]["legs"][0]["summary"]["length"]
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
    src = fake["trip"]["legs"][0]
    assert legs[0]["distance_m"] == src["summary"]["length"] * 1000.0  # km → m
    assert legs[0]["duration_s"] == src["summary"]["time"]
    assert legs[0]["polyline"] == src["shape"]


def test_fixture_is_live_capture_with_elevation():
    """M3c-1: the shared fixture must be a real Valhalla response taken
    with elevation_interval set, so post-processor tests and parse_legs
    exercise the actual schema rather than an assumed one."""
    with open(os.path.join(FIXTURES, "valhalla_response_sample.json")) as f:
        sample = json.load(f)
    legs = sample["trip"]["legs"]
    assert len(legs) >= 2
    for leg in legs:
        assert "elevation" in leg, f"no 'elevation' in leg keys: {list(leg.keys())}"
        assert leg["elevation_interval"] == 10.0
        assert all(isinstance(x, (int, float)) for x in leg["elevation"])
        assert len(leg["elevation"]) > 1


def test_parse_legs_prefers_leg_level_elevation_interval():
    """Live Valhalla echoes elevation_interval on each leg, not (only)
    at the trip top level — parse_legs reads the leg value first."""
    forged = {
        "trip": {
            "legs": [{
                "summary": {"length": 1.0, "time": 300.0},
                "shape": "abc",
                "elevation": [10.0, 11.0],
                "elevation_interval": 5.0,
            }],
            "summary": {"length": 1.0, "time": 300.0},
        },
        "elevation_interval": 10.0,
    }
    assert vc.parse_legs(forged)[0]["elevation_interval_m"] == 5.0


def test_parse_legs_includes_elevation_and_interval():
    """parse_legs exposes per-leg elevation samples + interval when the
    response carries them (always, since build_request_body always
    sets elevation_interval: 10)."""
    from server.routing.valhalla_client import parse_legs
    forged = {
        "trip": {
            "legs": [{
                "summary": {"length": 1.0, "time": 300.0},
                "shape": "abc",
                "elevation": [10.0, 11.0, 12.5, 14.0],
            }],
            "summary": {"length": 1.0, "time": 300.0},
        },
        "elevation_interval": 10.0,
    }
    parsed = parse_legs(forged)
    assert len(parsed) == 1
    leg = parsed[0]
    assert leg["elevation"] == [10.0, 11.0, 12.5, 14.0]
    assert leg["elevation_interval_m"] == 10.0


def test_parse_legs_defaults_elevation_interval_when_missing():
    """Older responses without the echoed elevation_interval still parse."""
    from server.routing.valhalla_client import parse_legs
    forged = {
        "trip": {
            "legs": [{
                "summary": {"length": 0.5, "time": 100.0},
                "shape": "xyz",
            }],
            "summary": {"length": 0.5, "time": 100.0},
        },
    }
    parsed = parse_legs(forged)
    assert parsed[0]["elevation"] == []
    assert parsed[0]["elevation_interval_m"] == 10.0
