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
    m.json.return_value = response_json
    m.raise_for_status = lambda: None
    if status_code >= 400:
        def _raise():
            from requests import HTTPError
            raise HTTPError(f"HTTP {status_code}")
        m.raise_for_status = _raise
    return m


def test_request_body_shape():
    body = vc.build_request_body(
        waypoints=[(-27.4, 152.9), (-27.5, 152.8)],
        profile="bicycle",
        costing_options={"use_hills": 0.5},
    )
    assert body["costing"] == "bicycle"
    assert body["costing_options"]["bicycle"]["use_hills"] == 0.5
    assert body["locations"] == [
        {"lat": -27.4, "lon": 152.9, "type": "break"},
        {"lat": -27.5, "lon": 152.8, "type": "break"},
    ]
    assert body["elevation_interval"] == 10


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


def test_parse_legs_decodes_shape():
    with open(os.path.join(FIXTURES, "valhalla_response_sample.json")) as f:
        fake = json.load(f)
    legs = vc.parse_legs(fake)
    assert len(legs) == 2
    assert legs[0]["distance_m"] == 2000.0  # km → m
    assert legs[0]["duration_s"] == 360.0
    assert legs[0]["polyline"] == fake["trip"]["legs"][0]["shape"]
