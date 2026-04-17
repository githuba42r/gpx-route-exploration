"""Route generation endpoints — calls Valhalla and writes the detailed GPX."""

import os
import time

from flask import Blueprint, current_app, jsonify, request

from server.auth import get_current_user
from server.models import waypoints as wp_model
from server.models.routes import get_route
from server.models.categories import get_category
from server.routing import valhalla_client as vc
from server.routing.gpx_writer import write_track_gpx

bp = Blueprint("api_routing", __name__, url_prefix="/api")


def _resolve_gpx_path(app, user_id, route):
    """Find or create the on-disk path for the route's GPX file."""
    category = get_category(user_id, route["category_id"])
    data_dir = app.config["DATA_DIR"]
    store_dir = os.path.join(data_dir, "gpx", user_id, category["slug"])
    os.makedirs(store_dir, exist_ok=True)
    return os.path.join(store_dir, route["storage_name"])


@bp.route("/routes/<int:route_id>/generate", methods=["POST"])
def generate_route(route_id):
    user_id = get_current_user()
    route = get_route(user_id, route_id)
    if route is None:
        return jsonify({"error": "Not found"}), 404

    wps = [w for w in wp_model.list_waypoints(route_id) if w.get("included", 1)]
    if len(wps) < 2:
        return jsonify({"error": "at least 2 included waypoints required"}), 400
    missing = [w["id"] for w in wps if w.get("lat") is None or w.get("lon") is None]
    if missing:
        return jsonify({"error": f"waypoints without coordinates: {missing}"}), 400

    opts = wp_model.get_or_create_options(route_id)
    profile = opts["profile"]

    try:
        response = vc.call_route(
            waypoints=[(w["lat"], w["lon"]) for w in wps],
            profile=profile,
            costing_options={},  # M3 wires the full costing options
            round_trip=bool(opts.get("round_trip")),
            kinds=[w.get("kind") or "stop" for w in wps],
        )
    except vc.ValhallaError as e:
        payload = {
            "error": "Upstream routing service failed",
            "detail": str(e),
            "upstream_url": e.upstream_url,
        }
        if e.upstream_body:
            payload["upstream_body"] = e.upstream_body
        return jsonify(payload), 502

    parsed_legs = vc.parse_legs(response)

    # Valhalla collapses interior `through`-type locations into a single leg
    # between adjacent `break`-type locations, so the leg count equals the
    # number of break boundaries minus 1 (or same as breaks if round-trip,
    # because the closing leg back to the first break is counted too).
    # We replicate the break-determination logic from valhalla_client.build_request_body.
    break_positions = []
    kinds = [w.get("kind") or "stop" for w in wps]
    n = len(wps)
    for i, w in enumerate(wps):
        is_endpoint = i == 0 or i == n - 1
        if is_endpoint or kinds[i] == "stop":
            break_positions.append(w["position"])

    expected_legs = len(break_positions) - 1
    if opts.get("round_trip"):
        expected_legs = len(break_positions)

    if len(parsed_legs) != expected_legs:
        return jsonify({
            "error": "Upstream routing service failed",
            "detail": (
                f"Valhalla returned {len(parsed_legs)} legs, expected {expected_legs} "
                f"({len(break_positions)} break-type locations: "
                f"{len(wps) - len(break_positions)} interior waypoints collapsed into through-points)"
            ),
        }), 502

    # Pair each returned leg with its from/to break-type positions. Interior
    # `through` waypoints are silently included inside the leg's polyline.
    legs_rows = []
    for i, leg in enumerate(parsed_legs):
        from_pos = break_positions[i]
        # Round-trip's last leg returns to break_positions[0].
        to_pos = break_positions[(i + 1) % len(break_positions)] \
                 if opts.get("round_trip") else break_positions[i + 1]
        legs_rows.append({
            "from_position": from_pos,
            "to_position": to_pos,
            "distance_m": leg["distance_m"],
            "duration_s": leg["duration_s"],
            "polyline": leg["polyline"],
        })
    wp_model.replace_legs(route_id, legs_rows)
    wp_model.update_options(route_id, last_generated_at=int(time.time()))

    gpx_path = _resolve_gpx_path(current_app, user_id, route)
    write_track_gpx(gpx_path, title=route["title"], legs=parsed_legs)

    summary = (response.get("trip") or {}).get("summary") or {}
    distance_km = float(summary.get("length") or 0.0)
    duration_s = float(summary.get("time") or 0.0)

    return jsonify({
        "route_id": route_id,
        "legs_count": len(parsed_legs),
        "distance_km": distance_km,
        "duration_s": duration_s,
        "gpx_url": f"/api/gpx/{route_id}",
        # Encoded polylines (precision 6) so the Create page can draw the
        # generated track inline without a follow-up /legs round-trip.
        "legs": [
            {
                "from_position": row["from_position"],
                "to_position": row["to_position"],
                "distance_m": row["distance_m"],
                "duration_s": row["duration_s"],
                "polyline": row["polyline"],
            }
            for row in legs_rows
        ],
    }), 200


@bp.route("/routes/<int:route_id>/legs", methods=["GET"])
def list_legs(route_id):
    user_id = get_current_user()
    route = get_route(user_id, route_id)
    if route is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(wp_model.list_legs(route_id)), 200
