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


def init_db(app):
    with app.app_context():
        db = get_db()
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        if os.path.exists(schema_path):
            with open(schema_path) as f:
                db.executescript(f.read())
            db.commit()


def init_app(app):
    init_db(app)
    app.teardown_appcontext(close_db)
