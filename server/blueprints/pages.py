from flask import Blueprint, render_template, redirect, url_for
from server.auth import get_current_user
from server.models.categories import ensure_default_category
from server.models.routes import get_route, touch_last_accessed

bp = Blueprint("pages", __name__)


@bp.route("/")
def library():
    ensure_default_category(get_current_user())
    return render_template("library.html")


@bp.route("/route/<int:route_id>")
def analysis(route_id):
    user_id = get_current_user()
    ensure_default_category(user_id)
    route = get_route(user_id, route_id)
    if not route:
        return redirect(url_for("pages.library"))
    touch_last_accessed(user_id, route_id)
    # Edit button is only enabled when this route has a recipe (i.e. at
    # least one row in route_waypoints) — M2 can't edit pure-GPX uploads.
    from server.models import waypoints as wp_model
    has_recipe = bool(wp_model.list_waypoints(route_id))
    return render_template("analysis.html", route=route, has_recipe=has_recipe)


@bp.route("/create")
def create_page():
    return render_template("create.html")
