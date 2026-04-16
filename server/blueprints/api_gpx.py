import os

from flask import Blueprint, current_app, jsonify, send_file

from server.auth import get_current_user
from server.models.routes import get_route, touch_last_accessed

bp = Blueprint("api_gpx", __name__, url_prefix="/api")


@bp.route("/gpx/<int:route_id>", methods=["GET"])
def serve_gpx(route_id):
    user_id = get_current_user()
    route = get_route(user_id, route_id)
    if route is None:
        return jsonify({"error": "Not found"}), 404

    data_dir = current_app.config["DATA_DIR"]
    file_path = _find_gpx_file(data_dir, user_id, route["storage_name"])
    if file_path is None or not os.path.exists(file_path):
        return jsonify({"error": "File not found on disk"}), 404

    touch_last_accessed(user_id, route_id)

    return send_file(
        file_path,
        mimetype="application/gpx+xml",
        as_attachment=False,
        download_name=route["filename"],
    )


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
