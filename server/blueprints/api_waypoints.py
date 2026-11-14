"""REST endpoints for a route's waypoint recipe."""

import os

from flask import Blueprint, current_app, jsonify, request

from server.auth import get_current_user
from server.models.routes import get_route
from server.models import waypoints as wp_model

bp = Blueprint("api_waypoints", __name__, url_prefix="/api")

VALID_KINDS = {"stop", "waypoint"}


def _require_route(route_id):
    user_id = get_current_user()
    route = get_route(user_id, route_id)
    if route is None:
        return None, (jsonify({"error": "Not found"}), 404)
    return route, None


@bp.route("/routes/<int:route_id>/waypoints", methods=["GET"])
def list_waypoints(route_id):
    _, err = _require_route(route_id)
    if err:
        return err
    return jsonify(wp_model.list_waypoints(route_id)), 200


@bp.route("/routes/<int:route_id>/waypoints", methods=["POST"])
def append_waypoint(route_id):
    _, err = _require_route(route_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    kind = data.get("kind")
    if kind not in VALID_KINDS:
        return jsonify({"error": "kind must be 'stop' or 'waypoint'"}), 400
    common = dict(
        name=data.get("name") or "Waypoint",
        lat=data.get("lat"),
        lon=data.get("lon"),
        kind=kind,
        address=data.get("address"),
        description=data.get("description"),
        dwell_minutes=int(data.get("dwell_minutes") or 0),
        pin_role=data.get("pin_role"),
    )
    if "linked_to_previous" in data:
        common["linked_to_previous"] = 1 if data["linked_to_previous"] else 0
    # Optional `position` turns this into an insert-at-position (used by
    # the line-drag feature). Absent → append at tail (original M1 behaviour).
    raw_position = data.get("position")
    try:
        if raw_position is None:
            wp = wp_model.append_waypoint(route_id, **common)
        else:
            wp = wp_model.insert_waypoint_at(
                route_id, position=int(raw_position), **common,
            )
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(wp), 201


@bp.route("/routes/<int:route_id>/waypoints/<int:wpt_id>", methods=["PATCH"])
def patch_waypoint(route_id, wpt_id):
    _, err = _require_route(route_id)
    if err:
        return err
    existing = wp_model.get_waypoint(wpt_id, route_id)
    if existing is None:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json(silent=True) or {}
    if "kind" in data and data["kind"] not in VALID_KINDS:
        return jsonify({"error": "kind must be 'stop' or 'waypoint'"}), 400
    if "linked_to_previous" in data:
        data["linked_to_previous"] = 1 if data["linked_to_previous"] else 0
    updated = wp_model.update_waypoint(wpt_id, route_id, **data)
    # D5: any change to linked_to_previous invalidates the optimiser's
    # cached result (groupings shifted). Direct SQL because update_options
    # filters None values out.
    if "linked_to_previous" in data and \
            int(data["linked_to_previous"]) != int(existing.get("linked_to_previous", 1)):
        from server.models import get_db
        db = get_db()
        db.execute(
            "UPDATE route_options SET last_optimised_at = NULL WHERE route_id = ?",
            (route_id,),
        )
        db.commit()
    return jsonify(updated), 200


@bp.route("/routes/<int:route_id>/waypoints/<int:wpt_id>", methods=["DELETE"])
def delete_waypoint(route_id, wpt_id):
    _, err = _require_route(route_id)
    if err:
        return err
    existing = wp_model.get_waypoint(wpt_id, route_id)
    if existing is None:
        return jsonify({"error": "Not found"}), 404
    wp_model.delete_waypoint(wpt_id, route_id)
    return "", 204


@bp.route("/routes/<int:route_id>/waypoints", methods=["PUT"])
def reorder_waypoints(route_id):
    _, err = _require_route(route_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    order = data.get("order")
    if not isinstance(order, list) or not all(isinstance(i, int) for i in order):
        return jsonify({"error": "order must be a list of waypoint ids"}), 400
    try:
        wp_model.reorder_waypoints(route_id, order)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(wp_model.list_waypoints(route_id)), 200


@bp.route("/routes/<int:route_id>/convert-to-recipe", methods=["POST"])
def convert_to_recipe(route_id):
    """Turn a GPX-only route into a recipe by sampling its track."""
    route, err = _require_route(route_id)
    if err:
        return err
    if wp_model.list_waypoints(route_id):
        return jsonify({"error": "Route already has a recipe"}), 409

    data = request.get_json(silent=True)
    data = data if isinstance(data, dict) else {}
    count = data.get("count", 6)
    if isinstance(count, bool) or not isinstance(count, int) or not 2 <= count <= 50:
        return jsonify({"error": "count must be an integer between 2 and 50"}), 400

    from server.blueprints.api_gpx import _find_gpx_file
    from server.gpx_recipe import extract_waypoints

    path = _find_gpx_file(
        current_app.config["DATA_DIR"], get_current_user(), route["storage_name"],
    )
    if path is None or not os.path.exists(path):
        return jsonify({"error": "Route has no GPX file"}), 404
    with open(path, "rb") as f:
        gpx_bytes = f.read()
    try:
        points = extract_waypoints(gpx_bytes, count)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    for p in points:
        wp_model.append_waypoint(
            route_id, name=p["name"], lat=p["lat"], lon=p["lon"],
            kind="waypoint", included=1,
        )
    wp_model.get_or_create_options(route_id)
    rows = wp_model.list_waypoints(route_id)
    return jsonify({"route_id": route_id, "count": len(rows), "waypoints": rows}), 200
