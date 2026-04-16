import os
import shutil
import sqlite3

from flask import Blueprint, current_app, jsonify, request

from server.auth import get_current_user
from server.models.categories import (
    create_category,
    delete_category,
    ensure_default_category,
    get_categories,
    get_category,
    rename_category,
)

bp = Blueprint("api_categories", __name__, url_prefix="/api")


@bp.before_request
def ensure_default():
    ensure_default_category(get_current_user())


@bp.route("/categories", methods=["GET"])
def list_categories():
    user_id = get_current_user()
    categories = get_categories(user_id)
    return jsonify(categories), 200


@bp.route("/categories", methods=["POST"])
def create_category_endpoint():
    user_id = get_current_user()
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    description = (data.get("description") or "").strip()

    try:
        category = create_category(user_id, name, description)
    except sqlite3.IntegrityError:
        return jsonify({"error": "Category already exists"}), 409

    # Create filesystem folder
    data_dir = current_app.config["DATA_DIR"]
    folder = os.path.join(data_dir, "gpx", user_id, category["slug"])
    os.makedirs(folder, exist_ok=True)

    return jsonify(category), 201


@bp.route("/categories/<int:category_id>", methods=["PATCH"])
def update_category_endpoint(category_id):
    user_id = get_current_user()
    category = get_category(user_id, category_id)
    if category is None:
        return jsonify({"error": "Category not found"}), 404

    data = request.get_json(silent=True) or {}
    new_name = data.get("name")
    new_description = data.get("description")

    if new_name is not None and category["slug"] == "default":
        return jsonify({"error": "Cannot rename the Default category"}), 400

    old_slug = category["slug"]

    try:
        updated = rename_category(user_id, category_id, name=new_name, description=new_description)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    # If name changed, rename folder on disk
    if new_name is not None and updated["slug"] != old_slug:
        data_dir = current_app.config["DATA_DIR"]
        old_folder = os.path.join(data_dir, "gpx", user_id, old_slug)
        new_folder = os.path.join(data_dir, "gpx", user_id, updated["slug"])
        if os.path.isdir(old_folder):
            os.rename(old_folder, new_folder)

    return jsonify(updated), 200


@bp.route("/categories/<int:category_id>", methods=["DELETE"])
def delete_category_endpoint(category_id):
    user_id = get_current_user()
    category = get_category(user_id, category_id)
    if category is None:
        return jsonify({"error": "Category not found"}), 404

    if category["slug"] == "default":
        return jsonify({"error": "Cannot delete the Default category"}), 400

    move_to_default = request.args.get("move_to_default", "").lower() == "true"

    # If moving files, we need to do it before the DB update
    data_dir = current_app.config["DATA_DIR"]
    category_folder = os.path.join(data_dir, "gpx", user_id, category["slug"])

    if move_to_default:
        default = ensure_default_category(user_id)
        default_folder = os.path.join(data_dir, "gpx", user_id, default["slug"])
        os.makedirs(default_folder, exist_ok=True)
        if os.path.isdir(category_folder):
            for fname in os.listdir(category_folder):
                src = os.path.join(category_folder, fname)
                dst = os.path.join(default_folder, fname)
                shutil.move(src, dst)

    try:
        delete_category(user_id, category_id, move_to_default=move_to_default)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    # Remove now-empty folder
    if os.path.isdir(category_folder):
        try:
            os.rmdir(category_folder)
        except OSError:
            pass  # not empty or doesn't exist — leave it

    return "", 204
