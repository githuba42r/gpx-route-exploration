"""Route generation endpoints — calls Valhalla and writes the detailed GPX."""

import json as _json
import os
import shutil
import time

from flask import Blueprint, current_app, jsonify, request

from server.auth import get_current_user
from server.models import get_db
from server.models import waypoints as wp_model
from server.models.routes import get_route
from server.models.categories import get_category
from server.route_postprocess import scan_legs_for_warnings
from server.routing import optimiser
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

    # Post-process: elevation-aware warnings (M3c). The post-processor
    # reads elevation samples from parsed_legs and emits
    # {max_grade_pct, warnings} parallel to legs_rows. We persist both
    # (writing the JSON list into the existing warnings TEXT column).
    threshold = opts.get("max_gradient_warn")
    post = scan_legs_for_warnings(parsed_legs, threshold)
    for row, scanned in zip(legs_rows, post):
        row["max_grade_pct"] = scanned["max_grade_pct"]
        row["warnings"] = (
            _json.dumps(scanned["warnings"]) if scanned["warnings"] else None
        )

    wp_model.replace_legs(route_id, legs_rows)
    never_generated = opts.get("last_generated_at") is None
    wp_model.update_options(route_id, last_generated_at=int(time.time()))

    gpx_path = _resolve_gpx_path(current_app, user_id, route)
    # Keep a one-time backup of an uploaded file before the first generate
    # overwrites it.
    if (never_generated and os.path.exists(gpx_path)
            and not os.path.exists(gpx_path + ".orig")):
        shutil.copy2(gpx_path, gpx_path + ".orig")
    write_track_gpx(gpx_path, title=route["title"], legs=parsed_legs,
        waypoints=[
            {
                "name": w.get("name") or "",
                "lat": w["lat"],
                "lon": w["lon"],
                "kind": w.get("kind") or "stop",
                "description": w.get("description"),
            }
            for w in wps
        ],
    )

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
                "max_grade_pct": row.get("max_grade_pct"),
                "warnings": _json.loads(row["warnings"]) if row.get("warnings") else None,
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


@bp.route("/routes/<int:route_id>/optimise", methods=["POST"])
def optimise_route(route_id):
    """Run NN + 2-opt over groups, persist the new order, stamp the
    last_optimised_at timestamp so frontends can tell when a stale flag
    toggle (M3b-6) invalidates the result."""
    user_id = get_current_user()
    route = get_route(user_id, route_id)
    if route is None:
        return jsonify({"error": "Not found"}), 404

    wps = wp_model.list_waypoints(route_id)
    included = [w for w in wps if w.get("included", 1)]
    if len(included) < 2:
        return jsonify({"error": "at least 2 included waypoints required"}), 400

    # Cost matrix from cached legs — real network distance beats haversine
    # whenever we already have it. Legs are symmetric for our purposes
    # (bicycle on a network where one-way edges are the exception).
    cost_matrix = {}
    wp_by_pos = {w["position"]: w for w in wps}
    for leg in wp_model.list_legs(route_id):
        a = wp_by_pos.get(leg["from_position"])
        b = wp_by_pos.get(leg["to_position"])
        if a is None or b is None:
            continue
        cost_matrix[(a["id"], b["id"])] = leg["distance_m"]
        cost_matrix[(b["id"], a["id"])] = leg["distance_m"]

    new_order = optimiser.optimise(included, cost_matrix=cost_matrix or None)

    # Excluded rows stay in the recipe but aren't part of the optimised
    # sequence. Park them at the tail in their prior order — simple and
    # correct; a future iteration can slot them back next to their
    # original neighbours.
    excluded = [w for w in wps if not w.get("included", 1)]
    full_order = new_order + [w["id"] for w in excluded]
    wp_model.reorder_waypoints(route_id, full_order)

    wp_model.update_options(route_id, last_optimised_at=int(time.time()))

    return jsonify({"new_order": new_order}), 200
