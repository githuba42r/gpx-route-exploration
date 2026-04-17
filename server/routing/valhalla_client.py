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


def build_request_body(waypoints, profile, costing_options=None, round_trip=False, kinds=None):
    """Compose the Valhalla /route request body.

    waypoints: list of (lat, lon) tuples. Minimum 2.
    profile: 'bicycle' | 'pedestrian' | 'auto'.
    costing_options: dict merged into costing_options[profile].
    round_trip: if True, append first waypoint at the end to close the loop.
    kinds: optional list parallel to waypoints, each 'stop' or 'waypoint'.
           Stops and the first/last location always become Valhalla type=break
           (a mandatory routing stop that must snap to the network). Interior
           waypoints become type=through, which is much more forgiving about
           off-network locations and maps naturally to "pass through, don't
           stop". If kinds is None, everything is a break (legacy behaviour).
    """
    n = len(waypoints)
    if kinds is None:
        kinds = ["stop"] * n
    # Per-location search radius (metres). Tells Valhalla to snap any pin
    # whose closest candidate edge is within this distance — dramatically
    # reduces the 499 "Could not find candidate edge used for destination
    # label" error for pins placed near but not exactly on a road or
    # cycle-able track. 100 m is a sweet spot: tight enough that we don't
    # route wildly far from the user's click, loose enough that clicks at
    # trail edges, park entrances, etc. still resolve.
    RADIUS_M = 100
    locs = []
    for i, (lat, lon) in enumerate(waypoints):
        is_endpoint = i == 0 or i == n - 1
        loc_type = "break" if (is_endpoint or kinds[i] == "stop") else "through"
        locs.append({"lat": lat, "lon": lon, "type": loc_type, "radius": RADIUS_M})
    if round_trip and waypoints:
        lat, lon = waypoints[0]
        locs.append({"lat": lat, "lon": lon, "type": "break", "radius": RADIUS_M})

    body = {
        "locations": locs,
        "costing": profile,
        "costing_options": {profile: dict(costing_options or {})},
        "elevation_interval": 10,
    }
    return body


def call_route(waypoints, profile, costing_options=None, round_trip=False, kinds=None, timeout=30):
    """Call Valhalla /route and return the parsed JSON response."""
    if len(waypoints) < 2:
        raise ValueError("at least 2 waypoints required")
    body = build_request_body(waypoints, profile, costing_options, round_trip, kinds=kinds)
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
