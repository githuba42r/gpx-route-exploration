import os
import uuid

from flask import Blueprint, current_app, jsonify, request

from server.auth import get_current_user
from server.gpx_parser import parse_gpx
from server.models.categories import ensure_default_category, get_category
from server.models.routes import (
    create_route,
    delete_route,
    get_route,
    get_routes,
    move_route,
    update_route,
)

bp = Blueprint("api_routes", __name__, url_prefix="/api")


@bp.before_request
def ensure_default():
    ensure_default_category(get_current_user())


@bp.route("/routes", methods=["POST"])
def upload_route():
    user_id = get_current_user()

    # --- JSON recipe-only creation (M1) ---
    if request.is_json:
        return _create_recipe_only(user_id, request.get_json() or {})

    # --- Existing multipart upload path ---
    file = request.files.get("file")
    if file is None:
        return jsonify({"error": "No file provided"}), 400
    raw = file.read()

    try:
        stats = parse_gpx(raw)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    title = (request.form.get("title") or "").strip()
    if not title:
        title = (stats.get("name") or "").strip()
    if not title:
        return jsonify({"error": "title is required when GPX has no <name>"}), 400

    category_id_param = request.form.get("category_id")
    if category_id_param:
        category = get_category(user_id, int(category_id_param))
        if category is None:
            return jsonify({"error": "Category not found"}), 404
    else:
        category = ensure_default_category(user_id)

    category_slug = category["slug"]
    data_dir = current_app.config["DATA_DIR"]
    store_dir = os.path.join(data_dir, "gpx", user_id, category_slug)
    os.makedirs(store_dir, exist_ok=True)

    storage_name = f"{uuid.uuid4().hex}.gpx"
    file_path = os.path.join(store_dir, storage_name)
    with open(file_path, "wb") as f:
        f.write(raw)

    original_filename = file.filename or "upload.gpx"
    route = create_route(
        user_id=user_id,
        category_id=category["id"],
        filename=original_filename,
        storage_name=storage_name,
        title=title,
        distance_km=stats.get("distance_km"),
        min_elevation=stats.get("min_elevation"),
        max_elevation=stats.get("max_elevation"),
        max_gradient_asc=stats.get("max_gradient_asc"),
        max_gradient_desc=stats.get("max_gradient_desc"),
        point_count=stats.get("point_count"),
    )
    parsed_wps = stats.get("waypoints") or []
    if parsed_wps:
        from server.models import waypoints as wp_model
        for wp in parsed_wps:
            wp_model.append_waypoint(
                route["id"],
                name=wp["name"],
                lat=wp["lat"],
                lon=wp["lon"],
                kind=wp["kind"],
                description=wp.get("description"),
            )
        wp_model.get_or_create_options(route["id"])
    return jsonify(route), 201


def _create_recipe_only(user_id, data):
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    profile = data.get("profile") or "bicycle"
    if profile not in ("bicycle", "pedestrian", "auto"):
        return jsonify({"error": f"invalid profile: {profile}"}), 400

    category_id_param = data.get("category_id")
    if category_id_param:
        category = get_category(user_id, int(category_id_param))
        if category is None:
            return jsonify({"error": "Category not found"}), 404
    else:
        category = ensure_default_category(user_id)

    storage_name = f"{uuid.uuid4().hex}.gpx"
    filename = f"{title}.gpx"

    route = create_route(
        user_id=user_id,
        category_id=category["id"],
        filename=filename,
        storage_name=storage_name,
        title=title,
    )
    from server.models import waypoints as wp_model
    wp_model.update_options(route["id"], profile=profile)
    return jsonify(route), 201


@bp.route("/routes", methods=["GET"])
def list_routes():
    user_id = get_current_user()
    category_id = request.args.get("category_id")
    if category_id is not None:
        routes = get_routes(user_id, int(category_id))
    else:
        routes = get_routes(user_id)
    return jsonify(routes), 200


@bp.route("/routes/<int:route_id>", methods=["GET"])
def get_single_route(route_id):
    user_id = get_current_user()
    route = get_route(user_id, route_id)
    if route is None:
        return jsonify({"error": "Not found"}), 404
    # has_recipe is true iff route_waypoints has at least one row — drives
    # the Edit button's enabled/disabled state on the Analysis page.
    from server.models import waypoints as wp_model
    route["has_recipe"] = bool(wp_model.list_waypoints(route_id))
    return jsonify(route), 200


@bp.route("/routes/<int:route_id>", methods=["PATCH"])
def update_route_metadata(route_id):
    user_id = get_current_user()
    route = get_route(user_id, route_id)
    if route is None:
        return jsonify({"error": "Not found"}), 404

    data = request.get_json(silent=True) or {}
    updated = update_route(
        user_id,
        route_id,
        title=data.get("title"),
        description=data.get("description"),
        notes=data.get("notes"),
    )
    return jsonify(updated), 200


@bp.route("/routes/<int:route_id>", methods=["DELETE"])
def delete_single_route(route_id):
    user_id = get_current_user()
    route = delete_route(user_id, route_id)
    if route is None:
        return jsonify({"error": "Not found"}), 404

    # Remove file from disk
    data_dir = current_app.config["DATA_DIR"]
    file_path = _find_gpx_file(data_dir, user_id, route["storage_name"])
    if file_path and os.path.exists(file_path):
        os.remove(file_path)

    return "", 204


@bp.route("/routes/<int:route_id>/move", methods=["PATCH"])
def move_route_endpoint(route_id):
    user_id = get_current_user()
    route = get_route(user_id, route_id)
    if route is None:
        return jsonify({"error": "Not found"}), 404

    data = request.get_json(silent=True) or {}
    new_category_id = data.get("category_id")
    if new_category_id is None:
        return jsonify({"error": "category_id is required"}), 400

    new_category = get_category(user_id, int(new_category_id))
    if new_category is None:
        return jsonify({"error": "Target category not found"}), 404

    # Move file on disk
    data_dir = current_app.config["DATA_DIR"]
    old_file_path = _find_gpx_file(data_dir, user_id, route["storage_name"])
    if old_file_path and os.path.exists(old_file_path):
        new_dir = os.path.join(data_dir, "gpx", user_id, new_category["slug"])
        os.makedirs(new_dir, exist_ok=True)
        new_file_path = os.path.join(new_dir, route["storage_name"])
        os.rename(old_file_path, new_file_path)

    try:
        updated = move_route(user_id, route_id, int(new_category_id))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(updated), 200


def _find_gpx_file(data_dir, user_id, storage_name):
    """Search for a GPX file by storage_name under data_dir/gpx/user_id/."""
    user_gpx_dir = os.path.join(data_dir, "gpx", user_id)
    if not os.path.isdir(user_gpx_dir):
        return None
    for category_slug in os.listdir(user_gpx_dir):
        candidate = os.path.join(user_gpx_dir, category_slug, storage_name)
        if os.path.exists(candidate):
            return candidate
    return None
