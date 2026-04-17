"""Schema and model tests for route_waypoints, route_options, route_legs."""

from server.models import get_db
from server.models import _apply_runtime_migrations


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


from server.models import waypoints as wp_model
from server.models.categories import ensure_default_category
from server.models.routes import create_route


def _create_stub_route(app, title="Plan test"):
    """Insert a bare routes row to act as a parent FK."""
    user_id = "anonymous"
    cat = ensure_default_category(user_id)
    return create_route(
        user_id=user_id,
        category_id=cat["id"],
        filename=f"{title}.gpx",
        storage_name=f"stub-{title.replace(' ', '-')}.gpx",
        title=title,
    )


def test_append_waypoint_assigns_positions(app):
    with app.app_context():
        route = _create_stub_route(app)
        w1 = wp_model.append_waypoint(route["id"], name="A", lat=-27.4, lon=152.9, kind="stop")
        w2 = wp_model.append_waypoint(route["id"], name="B", lat=-27.5, lon=152.8, kind="waypoint")
        assert w1["position"] == 0
        assert w2["position"] == 1


def test_list_waypoints_ordered(app):
    with app.app_context():
        route = _create_stub_route(app)
        wp_model.append_waypoint(route["id"], name="B", lat=-27.5, lon=152.8, kind="waypoint")
        wp_model.append_waypoint(route["id"], name="A", lat=-27.4, lon=152.9, kind="stop")
        rows = wp_model.list_waypoints(route["id"])
        assert [r["name"] for r in rows] == ["B", "A"]
        assert [r["position"] for r in rows] == [0, 1]


def test_update_waypoint_fields(app):
    with app.app_context():
        route = _create_stub_route(app)
        w = wp_model.append_waypoint(route["id"], name="A", lat=0, lon=0, kind="waypoint")
        updated = wp_model.update_waypoint(
            w["id"], route["id"],
            name="A2", kind="stop", lat=-27.0, lon=152.0,
            dwell_minutes=10, included=1,
        )
        assert updated["name"] == "A2"
        assert updated["kind"] == "stop"
        assert updated["dwell_minutes"] == 10


def test_delete_waypoint_and_reindex(app):
    with app.app_context():
        route = _create_stub_route(app)
        w0 = wp_model.append_waypoint(route["id"], name="A", lat=0, lon=0, kind="stop")
        w1 = wp_model.append_waypoint(route["id"], name="B", lat=0, lon=0, kind="stop")
        w2 = wp_model.append_waypoint(route["id"], name="C", lat=0, lon=0, kind="stop")
        wp_model.delete_waypoint(w1["id"], route["id"])
        rows = wp_model.list_waypoints(route["id"])
        assert [r["name"] for r in rows] == ["A", "C"]
        assert [r["position"] for r in rows] == [0, 1]


def test_reorder_waypoints(app):
    with app.app_context():
        route = _create_stub_route(app)
        ids = [wp_model.append_waypoint(route["id"], name=n, lat=0, lon=0, kind="stop")["id"] for n in ["A", "B", "C"]]
        wp_model.reorder_waypoints(route["id"], [ids[2], ids[0], ids[1]])
        rows = wp_model.list_waypoints(route["id"])
        assert [r["name"] for r in rows] == ["C", "A", "B"]


def test_get_or_create_options_defaults(app):
    with app.app_context():
        route = _create_stub_route(app)
        opts = wp_model.get_or_create_options(route["id"])
        assert opts["profile"] == "bicycle"
        assert opts["costing_preset"] == "hybrid"
        assert opts["round_trip"] == 0


def test_update_options(app):
    with app.app_context():
        route = _create_stub_route(app)
        wp_model.get_or_create_options(route["id"])
        updated = wp_model.update_options(route["id"], round_trip=1, profile="pedestrian")
        assert updated["round_trip"] == 1
        assert updated["profile"] == "pedestrian"


# ---------- runtime migrations + nullable-clear + arrival_time ----------

def test_arrival_time_column_exists_after_init(app):
    """The schema (plus the runtime migration for older DBs) guarantees an
    arrival_time column on route_waypoints."""
    with app.app_context():
        db = get_db()
        cols = {r[1] for r in db.execute("PRAGMA table_info(route_waypoints)").fetchall()}
        assert "arrival_time" in cols


def test_runtime_migration_adds_arrival_time_on_preexisting_db(app):
    """Simulate an older DB that has route_waypoints without arrival_time, and
    verify _apply_runtime_migrations adds it — without dropping any data."""
    with app.app_context():
        db = get_db()
        # Seed a waypoint on a stub route so we can assert data survives the ALTER.
        route = _create_stub_route(app, title="Migrate test")
        w = wp_model.append_waypoint(route["id"], name="A", lat=0, lon=0, kind="stop")

        # Recreate the table without the column to simulate an older deployment.
        db.executescript("""
            CREATE TABLE route_waypoints_old AS SELECT
              id, route_id, position, kind, name, address, lat, lon,
              included, pin_role, dwell_minutes, description
            FROM route_waypoints;
            DROP TABLE route_waypoints;
            CREATE TABLE route_waypoints (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              route_id INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
              position INTEGER NOT NULL,
              kind TEXT NOT NULL CHECK(kind IN ('stop','waypoint')),
              name TEXT NOT NULL,
              address TEXT, lat REAL, lon REAL,
              included INTEGER NOT NULL DEFAULT 1,
              pin_role TEXT,
              dwell_minutes INTEGER NOT NULL DEFAULT 0,
              description TEXT,
              UNIQUE(route_id, position)
            );
            INSERT INTO route_waypoints SELECT * FROM route_waypoints_old;
            DROP TABLE route_waypoints_old;
        """)
        db.commit()

        # Verify the column is missing pre-migration.
        cols_before = {r[1] for r in db.execute("PRAGMA table_info(route_waypoints)").fetchall()}
        assert "arrival_time" not in cols_before

        _apply_runtime_migrations(db)
        db.commit()

        cols_after = {r[1] for r in db.execute("PRAGMA table_info(route_waypoints)").fetchall()}
        assert "arrival_time" in cols_after
        # Pre-existing rows preserved.
        row = db.execute("SELECT name FROM route_waypoints WHERE id = ?", (w["id"],)).fetchone()
        assert row and row["name"] == "A"


def test_runtime_migration_is_idempotent(app):
    """Running _apply_runtime_migrations twice must not error or change anything."""
    with app.app_context():
        db = get_db()
        cols_before = sorted(r[1] for r in db.execute("PRAGMA table_info(route_waypoints)").fetchall())
        _apply_runtime_migrations(db)
        _apply_runtime_migrations(db)  # idempotent
        db.commit()
        cols_after = sorted(r[1] for r in db.execute("PRAGMA table_info(route_waypoints)").fetchall())
        assert cols_before == cols_after


def test_arrival_time_round_trips_via_update_waypoint(app):
    """arrival_time accepts an ISO 8601 string and reads back identically."""
    with app.app_context():
        route = _create_stub_route(app)
        w = wp_model.append_waypoint(route["id"], name="Café", lat=0, lon=0, kind="stop")
        iso = "2026-05-01T09:30:00Z"
        updated = wp_model.update_waypoint(w["id"], route["id"], arrival_time=iso)
        assert updated["arrival_time"] == iso
        # Reading back via get.
        fetched = wp_model.get_waypoint(w["id"], route["id"])
        assert fetched["arrival_time"] == iso


def test_update_waypoint_clears_nullable_fields(app):
    """Passing None for pin_role / address / description / arrival_time must
    actually clear them, not be filtered out as a "no-op" update."""
    with app.app_context():
        route = _create_stub_route(app)
        w = wp_model.append_waypoint(
            route["id"], name="A", lat=0, lon=0, kind="stop",
            address="123 Main St", description="notes",
        )
        # Populate nullable fields.
        w = wp_model.update_waypoint(w["id"], route["id"],
                                     pin_role="start", arrival_time="2026-05-01T09:30:00Z")
        assert w["pin_role"] == "start"
        assert w["address"] == "123 Main St"
        assert w["description"] == "notes"
        assert w["arrival_time"] == "2026-05-01T09:30:00Z"

        # Clear all four.
        cleared = wp_model.update_waypoint(
            w["id"], route["id"],
            pin_role=None, address=None, description=None, arrival_time=None,
        )
        assert cleared["pin_role"] is None
        assert cleared["address"] is None
        assert cleared["description"] is None
        assert cleared["arrival_time"] is None
        # Non-NULLABLE fields (name, kind, lat, lon) should NOT be touched —
        # explicit None for them is still filtered because the NULLABLE set
        # only covers the intentionally-nullable columns.
        assert cleared["name"] == "A"
        assert cleared["kind"] == "stop"
