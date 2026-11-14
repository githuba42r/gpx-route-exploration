import json
import os

from flask import Blueprint, Response, current_app, jsonify, request

from server.auth import get_current_user
from server.csv_import import CsvImportError, parse_csv
from server.geocode_client import GeocodeError, geocode_search
from server.csv_jobs import get_job, iter_events, start_job
from server.models.categories import ensure_default_category, get_category
from server.models.routes import create_recipe_route, get_route

bp = Blueprint("api_geocode", __name__, url_prefix="/api/geocode")


def _err(message, status):
    return jsonify({"error": message}), status


@bp.route("/csv", methods=["POST"])
def upload_csv():
    user_id = get_current_user()
    file = request.files.get("file")
    if file is None:
        return _err("No file provided", 400)
    try:
        mapping = json.loads(request.form.get("mapping") or "")
    except ValueError:
        return _err("mapping must be a JSON object", 400)
    if not isinstance(mapping, dict):
        return _err("mapping must be a JSON object", 400)

    max_bytes = current_app.config["CSV_MAX_BYTES"]
    data = file.read(max_bytes + 1)
    if len(data) > max_bytes:
        return _err(f"File too large (maximum {max_bytes} bytes)", 413)

    try:
        rows = parse_csv(data, mapping, max_rows=current_app.config["CSV_MAX_ROWS"])
    except CsvImportError as exc:
        return _err(str(exc), 400)

    route_id_param = request.args.get("route_id")
    append = route_id_param is not None
    if append:
        try:
            route = get_route(user_id, int(route_id_param))
        except ValueError:
            route = None
        if route is None:
            return _err("Route not found", 404)
    else:
        category_id = request.form.get("category_id")
        if category_id:
            try:
                category = get_category(user_id, int(category_id))
            except ValueError:
                category = None
            if category is None:
                return _err("Category not found", 404)
        else:
            category = ensure_default_category(user_id)
        title = (request.form.get("title") or "").strip()
        if not title:
            title = os.path.splitext(os.path.basename(file.filename or ""))[0].strip()
        if not title:
            title = "Imported stops"
        route = create_recipe_route(user_id, category, title)

    job = start_job(
        current_app._get_current_object(),
        user_id=user_id, route_id=route["id"], rows=rows, append=append,
    )
    return jsonify({"job_id": job.id, "route_id": route["id"], "append": append}), 202


@bp.route("/csv/<job_id>/stream", methods=["GET"])
def stream_csv(job_id):
    job = get_job(job_id, get_current_user())
    if job is None:
        return _err("Job not found", 404)
    return Response(
        iter_events(job),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@bp.route("/search", methods=["GET"])
def search():
    get_current_user()
    q = (request.args.get("q") or "").strip()
    if len(q) < 3:
        return jsonify([])
    try:
        limit = int(request.args.get("limit", 5))
    except ValueError:
        limit = 5
    limit = max(1, min(10, limit))
    try:
        return jsonify(geocode_search(q, limit))
    except GeocodeError:
        return _err("Address search is unavailable", 502)
