"""REST endpoints for per-user bookmarks."""

import logging

from flask import Blueprint, current_app, jsonify, make_response, request, send_file

from server import bookmark_photos as bp_files
from server.auth import get_current_user
from server.models import bookmarks as bm
from server.models import get_db
from server.models import tags as tag_model

bp = Blueprint("api_bookmarks", __name__, url_prefix="/api")


log = logging.getLogger(__name__)

# Multipart framing overhead allowed on top of the photo cap before the
# declared Content-Length alone is enough to reject.
_MULTIPART_SLACK = 16 * 1024


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
    b["photos"] = [bm.photo_public(p) for p in bm.list_photos(b["id"])]
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
    try:
        bp_files.remove_bookmark_dir(current_app.config["DATA_DIR"], deleted["user_id"], deleted["uuid"])
    except OSError:
        log.exception("could not remove photo folder for bookmark %s", bookmark_id)
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


# ---- photos -----------------------------------------------------------------

def _declared_length():
    return request.content_length


def _max_bytes():
    return current_app.config.get("BOOKMARK_PHOTO_MAX_BYTES", 10 * 1024 * 1024)


@bp.route("/bookmarks/<int:bookmark_id>/photos", methods=["POST"])
def upload_photo(bookmark_id):
    user_id = get_current_user()
    b, err = _require_bookmark(bookmark_id)
    if err:
        return err
    limit = _max_bytes()
    declared = _declared_length()
    if declared is not None and declared > limit + _MULTIPART_SLACK:
        return _err("Photo too large", 413)
    upload = request.files.get("file")
    if upload is None:
        return _err("file is required", 400)
    # Bounded read: a missing/lying Content-Length cannot get past the cap.
    data = upload.stream.read(limit + 1)
    if len(data) > limit:
        return _err("Photo too large", 413)
    if not data:
        return _err("Empty file", 400)
    try:
        mime = bp_files.detect_mime(data)
    except bp_files.UnsupportedImageType:
        return _err("Unsupported image type (JPEG, PNG or WebP only)", 415)
    except ValueError:
        return _err("File is not a valid image", 400)
    data_dir = current_app.config["DATA_DIR"]
    try:
        name, size = bp_files.save_photo(data_dir, user_id, b["uuid"], data, mime)
    except bp_files.UnsupportedImageType:
        return _err("Unsupported image type (JPEG, PNG or WebP only)", 415)
    except ValueError:
        return _err("File is not a valid image", 400)
    try:
        photo = bm.add_photo(bookmark_id, storage_name=name, mime_type=mime, byte_size=size)
    except Exception:
        bp_files.remove_photo_files(data_dir, user_id, b["uuid"], name)
        raise
    return jsonify(bm.photo_public(photo)), 201


@bp.route("/bookmarks/<int:bookmark_id>/photos/order", methods=["PUT"])
def reorder_photos(bookmark_id):
    _, err = _require_bookmark(bookmark_id)
    if err:
        return err
    data = request.get_json(silent=True)
    ids = data.get("ids") if isinstance(data, dict) else None
    if not bm.reorder_photos(bookmark_id, ids):
        return _err("ids must be exactly the bookmark's current photo ids", 400)
    return jsonify([bm.photo_public(p) for p in bm.list_photos(bookmark_id)]), 200


@bp.route("/bookmarks/<int:bookmark_id>/photos/<int:photo_id>", methods=["GET"])
def serve_photo(bookmark_id, photo_id):
    user_id = get_current_user()
    b, err = _require_bookmark(bookmark_id)
    if err:
        return err
    p = bm.get_photo(bookmark_id, photo_id)
    if p is None:
        return _err("Not found", 404)
    data_dir = current_app.config["DATA_DIR"]
    path, mime = bp_files.photo_path(data_dir, user_id, b["uuid"], p["storage_name"]), p["mime_type"]
    if request.args.get("thumb"):
        tpath = bp_files.photo_path(data_dir, user_id, b["uuid"], p["storage_name"], thumb=True)
        if bp_files.os.path.isfile(tpath):
            path, mime = tpath, "image/jpeg"
    if not bp_files.os.path.isfile(path):
        return _err("Not found", 404)
    resp = make_response(send_file(path, mimetype=mime))
    resp.headers["Cache-Control"] = "private, max-age=3600"
    return resp


@bp.route("/bookmarks/<int:bookmark_id>/photos/<int:photo_id>", methods=["DELETE"])
def delete_photo(bookmark_id, photo_id):
    user_id = get_current_user()
    b, err = _require_bookmark(bookmark_id)
    if err:
        return err
    row = bm.delete_photo(bookmark_id, photo_id)
    if row is None:
        return _err("Not found", 404)
    bp_files.remove_photo_files(current_app.config["DATA_DIR"], user_id, b["uuid"], row["storage_name"])
    return "", 204
