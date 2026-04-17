import os
import sqlite3
from flask import g, current_app


def get_db():
    if "db" not in g:
        db_path = os.path.join(current_app.config["DATA_DIR"], "routes.db")
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _apply_runtime_migrations(db):
    """Additive, idempotent column-level migrations for existing deployments
    where a plain CREATE TABLE IF NOT EXISTS wouldn't pick up new columns."""
    migrations = [
        # Added alongside the per-stop arrival-time edit feature on the
        # Create page. SQLite doesn't have IF NOT EXISTS for ADD COLUMN,
        # so we probe via PRAGMA table_info.
        ("route_waypoints", "arrival_time", "TEXT"),
    ]
    for table, column, coltype in migrations:
        cols = {r[1] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


def init_db(app):
    with app.app_context():
        db = get_db()
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        if os.path.exists(schema_path):
            with open(schema_path) as f:
                db.executescript(f.read())
        _apply_runtime_migrations(db)
        db.commit()


def init_app(app):
    init_db(app)
    app.teardown_appcontext(close_db)
