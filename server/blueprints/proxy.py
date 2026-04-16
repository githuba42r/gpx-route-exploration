import requests
from flask import Blueprint, current_app, jsonify
from flask import request as flask_request

bp = Blueprint("proxy", __name__, url_prefix="/proxy")

SUPPORTED_METHODS = ["GET", "POST", "PUT", "DELETE"]


def _proxy(upstream_base, path):
    url = f"{upstream_base}/{path}"
    if flask_request.query_string:
        url = f"{url}?{flask_request.query_string.decode('utf-8')}"

    headers = {}
    content_type = flask_request.headers.get("Content-Type")
    if content_type:
        headers["Content-Type"] = content_type

    try:
        resp = requests.request(
            method=flask_request.method,
            url=url,
            headers=headers,
            data=flask_request.get_data(),
            timeout=30,
        )
    except requests.Timeout as exc:
        return jsonify({"error": f"Upstream service unavailable: {exc}"}), 502
    except requests.ConnectionError as exc:
        return jsonify({"error": f"Upstream service unavailable: {exc}"}), 502

    return resp.content, resp.status_code, {"Content-Type": resp.headers.get("Content-Type", "application/octet-stream")}


@bp.route("/valhalla/<path:path>", methods=SUPPORTED_METHODS)
def valhalla_proxy(path):
    return _proxy(current_app.config["VALHALLA_URL"], path)


@bp.route("/nominatim/<path:path>", methods=SUPPORTED_METHODS)
def nominatim_proxy(path):
    return _proxy(current_app.config["NOMINATIM_URL"], path)
