"""Route generation endpoints — calls Valhalla and writes the detailed GPX."""

import json as _json
import os
import time

from flask import Blueprint, current_app, jsonify, request

from server.auth import get_current_user
from server.models import get_db
from server.models import waypoints as wp_model
from server.models.routes import get_route
from server.models.categories import get_category
from server.routing import presets
from server.routing import valhalla_client as vc
from server.routing.gpx_writer import write_track_gpx

ALLOWED_PROFILES = {"bicycle", "pedestrian", "auto"}
ALLOWED_PRESETS = {"road", "gravel-mtb", "easy", "hike", "drive", "custom", "hybrid"}

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
    # Preset resolution: the stored preset name yields a profile +
    # costing-options dict. Persisted overrides (set via the custom
    # panel, or directly by the API) merge on top — explicit user edits
    # win over preset defaults. 'custom' resolves to an empty preset so
    # only the persisted options apply.
    preset_name = opts.get("costing_preset") or "road"
    resolved = presets.resolve(preset_name)
    profile = opts.get("profile") or resolved["profile"]
    costing_options = dict(resolved["costing_options"])
    persisted = opts.get("costing_options")
    if persisted:
        try:
            override = _json.loads(persisted)
            if isinstance(override, dict):
                costing_options.update(override)
        except (TypeError, ValueError):
            pass  # corrupted JSON — ignore and use preset defaults.

    try:
        response = vc.call_route(
            waypoints=[(w["lat"], w["lon"]) for w in wps],
            profile=profile,
            costing_options=costing_options,
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

    # Every included waypoint is a break now (see valhalla_client.build_request_body),
    # so Valhalla returns one leg per adjacent pair: N-1 for a linear route,
    # N for a round trip (the closing leg back to the first waypoint counted).
    n = len(wps)
    expected_legs = n if opts.get("round_trip") else n - 1
    if len(parsed_legs) != expected_legs:
        return jsonify({
            "error": "Upstream routing service failed",
            "detail": (
                f"Valhalla returned {len(parsed_legs)} legs, "
                f"expected {expected_legs} for {n} waypoints"
                f"{' (round-trip)' if opts.get('round_trip') else ''}"
            ),
        }), 502

    # One leg per adjacent waypoint pair: from_position → to_position.
    legs_rows = []
    for i, leg in enumerate(parsed_legs):
        from_pos = wps[i]["position"]
        to_pos = wps[(i + 1) % n]["position"] if opts.get("round_trip") else wps[i + 1]["position"]
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


@bp.route("/routes/<int:route_id>/options", methods=["PATCH"])
def patch_route_options(route_id):
    user_id = get_current_user()
    route = get_route(user_id, route_id)
    if route is None:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json(silent=True) or {}

    patch = {}
    if "profile" in data:
        p = data["profile"]
        if p not in ALLOWED_PROFILES:
            return jsonify({"error": f"invalid profile: {p}"}), 400
        patch["profile"] = p
    if "costing_preset" in data:
        cp = data["costing_preset"]
        if cp not in ALLOWED_PRESETS:
            return jsonify({"error": f"invalid costing_preset: {cp}"}), 400
        patch["costing_preset"] = cp
    if "costing_options" in data:
        co = data["costing_options"]
        if isinstance(co, dict):
            patch["costing_options"] = _json.dumps(co)
        elif co is None:
            patch["costing_options"] = _json.dumps({})
        else:
            return jsonify({"error": "costing_options must be an object"}), 400
    if "round_trip" in data:
        patch["round_trip"] = 1 if bool(data["round_trip"]) else 0
    if "max_gradient_warn" in data:
        mg = data["max_gradient_warn"]
        patch["max_gradient_warn"] = None if mg is None else float(mg)

    # Geometry-affecting changes invalidate the leg cache. replace_legs([])
    # drops the rows; last_generated_at is cleared via direct SQL because
    # update_options filters None out.
    geometry_affecting = {"profile", "costing_preset", "costing_options", "round_trip"}
    if geometry_affecting.intersection(patch.keys()):
        wp_model.replace_legs(route_id, [])
        db = get_db()
        db.execute(
            "UPDATE route_options SET last_generated_at = NULL WHERE route_id = ?",
            (route_id,),
        )
        db.commit()

    updated = wp_model.update_options(route_id, **patch)
    return jsonify(updated), 200
