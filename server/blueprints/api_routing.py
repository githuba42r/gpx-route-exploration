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
        )
    except vc.ValhallaError as e:
        return jsonify({"error": f"Valhalla upstream error: {e}"}), 502

    parsed_legs = vc.parse_legs(response)
    if len(parsed_legs) != len(wps) - 1 and not opts.get("round_trip"):
        return jsonify({"error": f"Valhalla returned {len(parsed_legs)} legs, expected {len(wps)-1}"}), 502

    legs_rows = []
    for i, leg in enumerate(parsed_legs):
        legs_rows.append({
            "from_position": wps[i]["position"],
            "to_position": wps[(i + 1) % len(wps)]["position"],
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
    }), 200


@bp.route("/routes/<int:route_id>/legs", methods=["GET"])
def list_legs(route_id):
    user_id = get_current_user()
    route = get_route(user_id, route_id)
    if route is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(wp_model.list_legs(route_id)), 200
