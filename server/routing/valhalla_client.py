"""Thin Valhalla /route HTTP client."""

import logging

import requests
from flask import current_app

log = logging.getLogger(__name__)


class ValhallaError(Exception):
    """Raised when Valhalla returns a non-2xx or malformed response.

    Carries the upstream URL that was attempted and, when available,
    the upstream response body — so callers can surface "which server
    failed and why" without leaking raw exception formatting to users.
    """

    def __init__(self, message, *, upstream_url=None, upstream_body=None):
        super().__init__(message)
        self.upstream_url = upstream_url
        self.upstream_body = upstream_body


def build_request_body(waypoints, profile, costing_options=None, round_trip=False):
    """Compose the Valhalla /route request body.

    waypoints: list of (lat, lon) tuples. Minimum 2.
    profile: 'bicycle' | 'pedestrian' | 'auto'.
    costing_options: dict merged into costing_options[profile]. M1 passes {}.
    round_trip: if True, append first waypoint at the end to close the loop.
    """
    locs = [{"lat": lat, "lon": lon, "type": "break"} for lat, lon in waypoints]
    if round_trip and waypoints:
        lat, lon = waypoints[0]
        locs.append({"lat": lat, "lon": lon, "type": "break"})

    body = {
        "locations": locs,
        "costing": profile,
        "costing_options": {profile: dict(costing_options or {})},
        "elevation_interval": 10,
    }
    return body


def call_route(waypoints, profile, costing_options=None, round_trip=False, timeout=30):
    """Call Valhalla /route and return the parsed JSON response."""
    if len(waypoints) < 2:
        raise ValueError("at least 2 waypoints required")
    body = build_request_body(waypoints, profile, costing_options, round_trip)
    url = current_app.config["VALHALLA_URL"].rstrip("/") + "/route"
    log.info("valhalla: POST %s (%d waypoints, profile=%s, round_trip=%s)",
             url, len(waypoints), profile, round_trip)
    try:
        r = requests.post(url, json=body, timeout=timeout)
    except requests.RequestException as e:
        log.warning("valhalla: request to %s failed: %s", url, e)
        raise ValhallaError(
            f"could not reach Valhalla at {url}: {e}",
            upstream_url=url,
        ) from e
    if not r.ok:
        body_text = r.text[:500] if r.text else ""
        log.warning("valhalla: %s returned %s: %s", url, r.status_code, body_text)
        raise ValhallaError(
            f"Valhalla at {url} returned HTTP {r.status_code}",
            upstream_url=url,
            upstream_body=body_text,
        )
    return r.json()


def parse_legs(response):
    """Convert a Valhalla response into a list of leg dicts ready for
    route_legs insertion. The caller assigns from_position/to_position."""
    trip = response.get("trip") or {}
    legs = trip.get("legs") or []
    out = []
    for leg in legs:
        summary = leg.get("summary") or {}
        length_km = summary.get("length", 0.0)
        time_s = summary.get("time", 0.0)
        shape = leg.get("shape") or ""
        out.append({
            "distance_m": float(length_km) * 1000.0,
            "duration_s": float(time_s),
            "polyline": shape,
        })
    return out
