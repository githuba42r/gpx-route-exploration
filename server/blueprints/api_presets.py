"""Expose the routing presets catalogue to the client."""

from flask import Blueprint, jsonify

from server.routing import presets

bp = Blueprint("api_presets", __name__, url_prefix="/api")


@bp.route("/routing-presets", methods=["GET"])
def get_presets():
    return jsonify(presets.list_presets()), 200
