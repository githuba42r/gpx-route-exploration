from flask import Blueprint, jsonify, request

from server.auth import get_current_user
from server.models.categories import ensure_default_category, get_category
from server.models.routes import get_route
from server.models.tags import (
    delete_tag,
    get_category_tags,
    get_route_tags,
    get_tags_with_counts,
    set_category_tags,
    set_route_tags,
)

bp = Blueprint("api_tags", __name__, url_prefix="/api")


@bp.before_request
def ensure_default():
    ensure_default_category(get_current_user())


@bp.route("/tags", methods=["GET"])
def list_tags():
    user_id = get_current_user()
    tags = get_tags_with_counts(user_id)
    return jsonify(tags), 200


@bp.route("/tags/<int:tag_id>", methods=["DELETE"])
def delete_tag_endpoint(tag_id):
    user_id = get_current_user()
    tags_before = get_tags_with_counts(user_id)
    if not any(t["id"] == tag_id for t in tags_before):
        return jsonify({"error": "Not found"}), 404
    delete_tag(user_id, tag_id)
    return "", 204


@bp.route("/routes/<int:route_id>/tags", methods=["PUT"])
def set_route_tags_endpoint(route_id):
    user_id = get_current_user()
    route = get_route(user_id, route_id)
    if route is None:
        return jsonify({"error": "Not found"}), 404

    data = request.get_json(silent=True) or {}
    tag_names = data.get("tags", [])
    set_route_tags(user_id, route_id, tag_names)

    route["tags"] = get_route_tags(user_id, route_id)
    return jsonify(route), 200


@bp.route("/categories/<int:category_id>/tags", methods=["PUT"])
def set_category_tags_endpoint(category_id):
    user_id = get_current_user()
    category = get_category(user_id, category_id)
    if category is None:
        return jsonify({"error": "Not found"}), 404

    data = request.get_json(silent=True) or {}
    tag_names = data.get("tags", [])
    set_category_tags(user_id, category_id, tag_names)

    category["tags"] = get_category_tags(user_id, category_id)
    return jsonify(category), 200
