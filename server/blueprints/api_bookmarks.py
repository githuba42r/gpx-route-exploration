"""REST endpoints for per-user bookmarks."""

from flask import Blueprint, jsonify, request

from server.auth import get_current_user
from server.models import bookmarks as bm
from server.models import get_db
from server.models import tags as tag_model

bp = Blueprint("api_bookmarks", __name__, url_prefix="/api")


def _err(msg, code):
    return jsonify({"error": msg}), code


def _require_bookmark(bookmark_id):
    b = bm.get_bookmark(get_current_user(), bookmark_id)
    if b is None:
        return None, _err("Not found", 404)
    return b, None


def _clean_tags(raw):
    """Return (names, error)."""
    if raw is None:
        return [], None
    if not isinstance(raw, list):
        return None, "tags must be a list of strings"
    names = []
    for t in raw:
        if not isinstance(t, str) or not t.strip():
            return None, "tags must be non-empty strings"
        if len(t.strip()) > 60:
            return None, "tag names must be at most 60 characters"
        names.append(t.strip())
    return names, None


def _detail(user_id, b):
    b = dict(b)
    b["tags"] = tag_model.get_bookmark_tags(user_id, b["id"])
    b["photos"] = []  # filled in by the photo task
    return b


@bp.route("/bookmarks", methods=["GET"])
def list_bookmarks():
    return jsonify(bm.list_bookmarks(get_current_user())), 200


@bp.route("/bookmarks", methods=["POST"])
def create_bookmark():
    user_id = get_current_user()
    data = request.get_json(silent=True)
    clean, error = bm.validate_bookmark_fields(data, partial=False)
    if error:
        return _err(error, 400)
    tags, terr = _clean_tags(data.get("tags"))
    if terr:
        return _err(terr, 400)
    b = bm.create_bookmark(user_id, **clean)
    if tags:
        tag_model.set_bookmark_tags(user_id, b["id"], tags)
    return jsonify(_detail(user_id, bm.get_bookmark(user_id, b["id"]))), 201


@bp.route("/bookmarks/<int:bookmark_id>", methods=["GET"])
def get_bookmark(bookmark_id):
    b, err = _require_bookmark(bookmark_id)
    if err:
        return err
    return jsonify(_detail(get_current_user(), b)), 200


@bp.route("/bookmarks/<int:bookmark_id>", methods=["PATCH"])
def patch_bookmark(bookmark_id):
    user_id = get_current_user()
    _, err = _require_bookmark(bookmark_id)
    if err:
        return err
    clean, error = bm.validate_bookmark_fields(request.get_json(silent=True), partial=True)
    if error:
        return _err(error, 400)
    b = bm.update_bookmark(user_id, bookmark_id, **clean)
    return jsonify(_detail(user_id, b)), 200


@bp.route("/bookmarks/<int:bookmark_id>", methods=["DELETE"])
def delete_bookmark(bookmark_id):
    deleted = bm.delete_bookmark(get_current_user(), bookmark_id)
    if deleted is None:
        return _err("Not found", 404)
    return "", 204


@bp.route("/bookmarks/<int:bookmark_id>/tags", methods=["PUT"])
def set_tags(bookmark_id):
    user_id = get_current_user()
    _, err = _require_bookmark(bookmark_id)
    if err:
        return err
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or "tags" not in data:
        return _err("tags is required", 400)
    names, terr = _clean_tags(data["tags"])
    if terr:
        return _err(terr, 400)
    tag_model.set_bookmark_tags(user_id, bookmark_id, names)
    return jsonify(tag_model.get_bookmark_tags(user_id, bookmark_id)), 200


@bp.route("/bookmarks/from-waypoint/<int:wpt_id>", methods=["POST"])
def from_waypoint(wpt_id):
    user_id = get_current_user()
    row = get_db().execute(
        """
        SELECT w.* FROM route_waypoints w
        JOIN routes r ON r.id = w.route_id
        WHERE w.id = ? AND r.user_id = ?
        """,
        (wpt_id, user_id),
    ).fetchone()
    if row is None:
        return _err("Not found", 404)
    clean, error = bm.validate_bookmark_fields(
        {
            "name": (row["name"] or "").strip()[: bm.NAME_MAX] or "Bookmark",
            "lat": row["lat"],
            "lon": row["lon"],
            "description": (row["description"] or "")[: bm.DESCRIPTION_MAX],
        },
        partial=False,
    )
    if error:
        return _err(f"Waypoint cannot be bookmarked: {error}", 400)
    b = bm.create_bookmark(user_id, **clean)
    return jsonify(_detail(user_id, b)), 201
