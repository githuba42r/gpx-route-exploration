"""REST endpoints for a route's waypoint recipe."""

from flask import Blueprint, jsonify, request

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
    try:
        wp = wp_model.append_waypoint(
            route_id,
            name=data.get("name") or "Waypoint",
            lat=data.get("lat"),
            lon=data.get("lon"),
            kind=kind,
            address=data.get("address"),
            description=data.get("description"),
            dwell_minutes=int(data.get("dwell_minutes") or 0),
            pin_role=data.get("pin_role"),
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
    updated = wp_model.update_waypoint(wpt_id, route_id, **data)
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
