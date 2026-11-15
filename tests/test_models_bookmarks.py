import math

import pytest

from server.models import bookmarks as bm
from server.models import get_db
from server.models import tags as tag_model


def test_tables_exist(app):
    db = get_db()
    names = {r[0] for r in db.execute("SELECT name FROM sqlite_master").fetchall()}
    assert {"bookmarks", "bookmark_tags", "bookmark_photos",
            "idx_bookmarks_user", "idx_bookmark_photos_bookmark"} <= names


def test_create_get_list_delete(app):
    b = bm.create_bookmark("u1", name="Cafe", lat=1.5, lon=2.5, description="d")
    assert len(b["uuid"]) == 32
    assert bm.get_bookmark("u1", b["id"])["name"] == "Cafe"
    assert bm.get_bookmark("u2", b["id"]) is None
    lst = bm.list_bookmarks("u1")
    assert lst[0]["tags"] == [] and lst[0]["photo_count"] == 0
    assert lst[0]["thumb_url"] is None
    assert bm.list_bookmarks("u2") == []
    assert bm.delete_bookmark("u2", b["id"]) is None
    deleted = bm.delete_bookmark("u1", b["id"])
    assert deleted["uuid"] == b["uuid"]
    assert bm.get_bookmark("u1", b["id"]) is None


def test_update_bumps_updated_at_and_orders(app):
    a = bm.create_bookmark("u1", name="A", lat=0, lon=0)
    b = bm.create_bookmark("u1", name="B", lat=0, lon=0)
    db = get_db()
    db.execute("UPDATE bookmarks SET updated_at='2020-01-01 00:00:00'")
    db.commit()
    upd = bm.update_bookmark("u1", a["id"], name="A2")
    assert upd["name"] == "A2"
    assert upd["updated_at"] > "2020-01-01 00:00:00"
    assert [x["name"] for x in bm.list_bookmarks("u1")][0] == "A2"
    assert bm.update_bookmark("u2", a["id"], name="x") is None


def test_tags_replace_and_cascade(app):
    b = bm.create_bookmark("u1", name="A", lat=0, lon=0)
    db = get_db()
    db.execute("UPDATE bookmarks SET updated_at='2020-01-01 00:00:00'")
    db.commit()
    tag_model.set_bookmark_tags("u1", b["id"], ["Cafe", "cafe", "View"])
    assert [t["name"] for t in tag_model.get_bookmark_tags("u1", b["id"])] == ["Cafe", "View"]
    assert bm.get_bookmark("u1", b["id"])["updated_at"] > "2020-01-01 00:00:00"
    assert sorted(t["name"] for t in bm.list_bookmarks("u1")[0]["tags"]) == ["Cafe", "View"]
    counts = {t["name"]: t["usage_count"] for t in tag_model.get_tags_with_counts("u1")}
    assert counts == {"Cafe": 1, "View": 1}
    tag_model.set_bookmark_tags("u1", b["id"], ["View"])
    assert [t["name"] for t in tag_model.get_bookmark_tags("u1", b["id"])] == ["View"]
    assert tag_model.get_bookmark_tags("u2", b["id"]) == []
    bm.delete_bookmark("u1", b["id"])
    assert db.execute("SELECT COUNT(*) FROM bookmark_tags").fetchone()[0] == 0


def test_delete_tag_cleans_bookmark_tags(app):
    b = bm.create_bookmark("u1", name="A", lat=0, lon=0)
    tag_model.set_bookmark_tags("u1", b["id"], ["X"])
    tid = tag_model.get_bookmark_tags("u1", b["id"])[0]["id"]
    tag_model.delete_tag("u1", tid)
    assert get_db().execute("SELECT COUNT(*) FROM bookmark_tags").fetchone()[0] == 0
    assert bm.list_bookmarks("u1")[0]["tags"] == []


@pytest.mark.parametrize("data", [
    {"name": "x", "lat": 91, "lon": 0},
    {"name": "x", "lat": -91, "lon": 0},
    {"name": "x", "lat": 0, "lon": 181},
    {"name": "x", "lat": 0, "lon": "x"},
    {"name": "x", "lat": "1", "lon": 0},
    {"name": "x", "lat": True, "lon": 0},
    {"name": "x", "lat": float("nan"), "lon": 0},
    {"name": "x", "lat": 0, "lon": math.inf},
    {"name": "x", "lat": None, "lon": 0},
    {"name": "   ", "lat": 0, "lon": 0},
    {"name": "a" * 121, "lat": 0, "lon": 0},
    {"name": 5, "lat": 0, "lon": 0},
    {"lat": 0, "lon": 0},
    {"name": "x", "lat": 0, "lon": 0, "description": "d" * 2001},
    {"name": "x", "lat": 0, "lon": 0, "description": 7},
])
def test_validate_rejects(data):
    clean, err = bm.validate_bookmark_fields(data, partial=False)
    assert clean is None and err


def test_validate_ok_and_partial():
    clean, err = bm.validate_bookmark_fields(
        {"name": "  Hi ", "lat": 90, "lon": -180, "description": "d" * 2000}, partial=False)
    assert err is None and clean["name"] == "Hi" and clean["lat"] == 90.0
    clean, err = bm.validate_bookmark_fields({"lat": 5}, partial=True)
    assert err is None and clean == {"lat": 5.0}
    clean, err = bm.validate_bookmark_fields({"name": ""}, partial=True)
    assert err
    clean, err = bm.validate_bookmark_fields({}, partial=True)
    assert err
