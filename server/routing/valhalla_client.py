"""Thin Valhalla /route HTTP client."""

import requests
from flask import current_app


class ValhallaError(Exception):
    """Raised when Valhalla returns a non-2xx or malformed response."""


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
    try:
        r = requests.post(url, json=body, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException as e:
        raise ValhallaError(str(e)) from e
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
