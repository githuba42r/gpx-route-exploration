"""M8: opening a pre-M8 database adds the bookmark tables without touching existing rows."""

import os
import sqlite3

import pytest

from server import create_app

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "pre_m8_schema.sql")


def test_pre_m8_db_gains_bookmark_tables_and_keeps_rows(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    db_path = str(data / "routes.db")
    conn = sqlite3.connect(db_path)
    with open(FIXTURE) as f:
        conn.executescript(f.read())
    pre = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert "bookmarks" not in pre
    conn.execute("INSERT INTO tags (user_id, name, name_lower) VALUES ('u1', 'Hills', 'hills')")
    conn.execute("INSERT INTO categories (user_id, name, slug) VALUES ('u1', 'Default', 'default')")
    conn.execute("INSERT INTO routes (user_id, category_id, title, filename, storage_name) "
                 "VALUES ('u1', 1, 'Old route', 'x.gpx', 'abc.gpx')")
    conn.execute("INSERT INTO route_tags (route_id, tag_id) VALUES (1, 1)")
    conn.commit()
    tags_before = conn.execute("SELECT * FROM tags ORDER BY id").fetchall()
    routes_before = conn.execute("SELECT * FROM routes ORDER BY id").fetchall()
    conn.close()

    create_app(config_override={"DATA_DIR": str(data), "TESTING": True, "BACKUP_ENABLED": False})

    conn = sqlite3.connect(db_path)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert {"bookmarks", "bookmark_tags", "bookmark_photos",
            "idx_bookmarks_user", "idx_bookmark_photos_bookmark"} <= names
    assert conn.execute("SELECT * FROM tags ORDER BY id").fetchall() == tags_before
    assert conn.execute("SELECT * FROM routes ORDER BY id").fetchall() == routes_before
    assert conn.execute("SELECT * FROM route_tags").fetchall() == [(1, 1)]
    conn.execute("INSERT INTO bookmarks (uuid, user_id, name, lat, lon) VALUES ('same','u1','A',0,0)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO bookmarks (uuid, user_id, name, lat, lon) VALUES ('same','u2','B',0,0)")
    conn.close()
