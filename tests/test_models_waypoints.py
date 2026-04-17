"""Schema and model tests for route_waypoints, route_options, route_legs."""

from server.models import get_db


def _tables(db):
    rows = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return {r[0] for r in rows}


def test_m1_tables_exist(app):
    with app.app_context():
        db = get_db()
        tables = _tables(db)
        assert "route_waypoints" in tables
        assert "route_options" in tables
        assert "route_legs" in tables


def test_route_waypoints_columns(app):
    with app.app_context():
        db = get_db()
        cols = {r[1] for r in db.execute("PRAGMA table_info(route_waypoints)").fetchall()}
        expected = {
            "id", "route_id", "position", "kind", "name", "address",
            "lat", "lon", "included", "pin_role", "dwell_minutes", "description",
        }
        assert expected.issubset(cols), f"missing: {expected - cols}"


def test_route_options_columns(app):
    with app.app_context():
        db = get_db()
        cols = {r[1] for r in db.execute("PRAGMA table_info(route_options)").fetchall()}
        expected = {
            "route_id", "profile", "costing_preset", "costing_options",
            "round_trip", "max_gradient_warn", "last_optimised_at", "last_generated_at",
        }
        assert expected.issubset(cols), f"missing: {expected - cols}"


def test_route_legs_columns(app):
    with app.app_context():
        db = get_db()
        cols = {r[1] for r in db.execute("PRAGMA table_info(route_legs)").fetchall()}
        expected = {
            "route_id", "from_position", "to_position",
            "distance_m", "duration_s", "polyline",
            "max_grade_pct", "warnings",
        }
        assert expected.issubset(cols), f"missing: {expected - cols}"
