import io
import os

import pytest
from PIL import Image

from server import create_app

A = {"Remote-User": "user-a"}
B = {"Remote-User": "user-b"}


def _img(fmt="PNG", size=(800, 400), color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt)
    return buf.getvalue()


MIME = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}


def _mk(client, headers=A):
    return client.post("/api/bookmarks", json={"name": "P", "lat": 1, "lon": 2}, headers=headers).get_json()


def _up(client, bid, data=None, fmt="PNG", headers=A, filename="pic.png", mime=None):
    data = _img(fmt) if data is None else data
    return client.post(
        f"/api/bookmarks/{bid}/photos",
        data={"file": (io.BytesIO(data), filename, mime or MIME.get(fmt, "image/png"))},
        content_type="multipart/form-data",
        headers=headers,
    )


def _files(app):
    root = os.path.join(app.config["DATA_DIR"], "bookmarks")
    out = []
    for d, _, fs in os.walk(root):
        out += [os.path.join(d, f) for f in fs]
    return out


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_upload_formats(client, app, fmt):
    b = _mk(client)
    r = _up(client, b["id"], fmt=fmt)
    assert r.status_code == 201, r.get_json()
    p = r.get_json()
    assert set(p) >= {"id", "position", "mime_type", "byte_size", "url", "thumb_url"}
    assert p["mime_type"] == MIME[fmt] and p["position"] == 0
    assert p["url"] == f"/api/bookmarks/{b['id']}/photos/{p['id']}"
    assert p["thumb_url"].endswith("?thumb=1")
    thumbs = [f for f in _files(app) if f.endswith(".thumb.jpg")]
    assert len(thumbs) == 1
    with Image.open(thumbs[0]) as im:
        assert im.format == "JPEG" and max(im.size) <= 320
    assert len(_files(app)) == 2


def test_mime_by_content_not_header(client, app):
    b = _mk(client)
    # PNG bytes labelled jpeg with .jpg name -> stored as png
    r = _up(client, b["id"], fmt="PNG", filename="x.jpg", mime="image/jpeg")
    assert r.status_code == 201 and r.get_json()["mime_type"] == "image/png"
    assert any(f.endswith(".png") for f in _files(app))


def test_rejections_write_nothing(client, app):
    b = _mk(client)
    assert _up(client, b["id"], data=b"just text", mime="image/jpeg", filename="a.jpg").status_code in (400, 415)
    assert _up(client, b["id"], data=b"", mime="image/png").status_code == 400
    assert _up(client, b["id"], data=b"GIF89a....", mime="image/gif", filename="a.gif").status_code in (400, 415)
    gif = io.BytesIO()
    Image.new("RGB", (4, 4)).save(gif, "GIF")
    assert _up(client, b["id"], data=gif.getvalue(), mime="image/png").status_code == 415
    assert _up(client, b["id"], data=_img()[:50], mime="image/png").status_code == 400  # truncated
    r = client.post(f"/api/bookmarks/{b['id']}/photos", data={}, content_type="multipart/form-data", headers=A)
    assert r.status_code == 400
    assert _files(app) == []
    assert client.get(f"/api/bookmarks/{b['id']}", headers=A).get_json()["photos"] == []


def test_oversize_413(tmp_path):
    app = create_app({"DATA_DIR": str(tmp_path / "d"), "TESTING": True, "BACKUP_ENABLED": False,
                      "BOOKMARK_PHOTO_MAX_BYTES": 1000})
    with app.app_context():
        c = app.test_client()
        b = _mk(c)
        big = _img(size=(600, 600))
        assert len(big) > 1000 or True
        big = big + b"\0" * 5000
        assert _up(c, b["id"], data=big).status_code == 413
        assert _files(app) == []


def test_oversize_bounded_read_without_content_length(tmp_path, monkeypatch):
    app = create_app({"DATA_DIR": str(tmp_path / "d"), "TESTING": True, "BACKUP_ENABLED": False,
                      "BOOKMARK_PHOTO_MAX_BYTES": 1000})
    with app.app_context():
        c = app.test_client()
        b = _mk(c)
        from server.blueprints import api_bookmarks
        monkeypatch.setattr(api_bookmarks, "_declared_length", lambda: None)
        assert _up(c, b["id"], data=_img() + b"\0" * 5000).status_code == 413
        assert _files(app) == []


def test_decompression_bomb_400(client, app, monkeypatch):
    b = _mk(client)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
    assert _up(client, b["id"], data=_img(size=(800, 400))).status_code == 400
    assert _files(app) == []


def test_evil_filename_ignored(client, app):
    b = _mk(client)
    r = _up(client, b["id"], filename="../../evil.jpg")
    assert r.status_code == 201
    files = _files(app)
    root = os.path.realpath(os.path.join(app.config["DATA_DIR"], "bookmarks"))
    assert all(os.path.realpath(f).startswith(root + os.sep) for f in files)
    assert not any("evil" in os.path.basename(f) for f in files)
    assert not os.path.exists(os.path.join(app.config["DATA_DIR"], "evil.jpg"))
    folder = {os.path.dirname(f) for f in files}
    assert len(folder) == 1 and os.path.basename(folder.pop()) == client.get(
        f"/api/bookmarks/{b['id']}", headers=A).get_json()["uuid"]


def test_hostile_user_id_stays_in_root(client, app):
    h = {"Remote-User": "../../x"}
    b = _mk(client, h)
    assert _up(client, b["id"], headers=h).status_code == 201
    root = os.path.realpath(os.path.join(app.config["DATA_DIR"], "bookmarks"))
    assert all(os.path.realpath(f).startswith(root + os.sep) for f in _files(app))


def test_order_reorder_delete_compact(client, app):
    b = _mk(client)
    ids = [_up(client, b["id"], fmt=f).get_json()["id"] for f in ("PNG", "JPEG", "WEBP")]
    d = client.get(f"/api/bookmarks/{b['id']}", headers=A).get_json()
    assert [p["id"] for p in d["photos"]] == ids and [p["position"] for p in d["photos"]] == [0, 1, 2]
    assert set(d["photos"][0]) >= {"id", "position", "mime_type", "byte_size", "caption", "url", "thumb_url"}
    lst = client.get("/api/bookmarks", headers=A).get_json()[0]
    assert lst["photo_count"] == 3
    assert lst["thumb_url"] == f"/api/bookmarks/{b['id']}/photos/{ids[0]}?thumb=1"

    new = [ids[2], ids[0], ids[1]]
    r = client.put(f"/api/bookmarks/{b['id']}/photos/order", json={"ids": new}, headers=A)
    assert r.status_code == 200
    d = client.get(f"/api/bookmarks/{b['id']}", headers=A).get_json()
    assert [p["id"] for p in d["photos"]] == new
    for bad in ([ids[0]], new + [999], [new[0], new[0], new[1]], "x", None):
        assert client.put(f"/api/bookmarks/{b['id']}/photos/order", json={"ids": bad},
                          headers=A).status_code == 400
    assert [p["id"] for p in client.get(f"/api/bookmarks/{b['id']}", headers=A).get_json()["photos"]] == new

    assert client.delete(f"/api/bookmarks/{b['id']}/photos/{new[1]}", headers=A).status_code == 204
    d = client.get(f"/api/bookmarks/{b['id']}", headers=A).get_json()
    assert [p["id"] for p in d["photos"]] == [new[0], new[2]]
    assert [p["position"] for p in d["photos"]] == [0, 1]
    assert len(_files(app)) == 4
    assert client.delete(f"/api/bookmarks/{b['id']}/photos/{new[1]}", headers=A).status_code == 404
    # next upload goes to the tail
    assert _up(client, b["id"]).get_json()["position"] == 2


def test_delete_bookmark_removes_folder(client, app):
    b = _mk(client)
    _up(client, b["id"])
    _up(client, b["id"])
    assert len(_files(app)) == 4
    assert client.delete(f"/api/bookmarks/{b['id']}", headers=A).status_code == 204
    assert _files(app) == []
    from server.models import get_db
    assert get_db().execute("SELECT COUNT(*) FROM bookmark_photos").fetchone()[0] == 0


def test_serve_full_and_thumb(client):
    b = _mk(client)
    raw = _img("JPEG", size=(900, 900))
    p = _up(client, b["id"], data=raw, fmt="JPEG").get_json()
    r = client.get(p["url"], headers=A)
    assert r.status_code == 200 and r.data == raw
    assert r.headers["Content-Type"] == "image/jpeg"
    assert r.headers["Cache-Control"] == "private, max-age=3600"
    t = client.get(p["thumb_url"], headers=A)
    assert t.status_code == 200 and t.headers["Content-Type"] == "image/jpeg"
    assert t.data != raw
    with Image.open(io.BytesIO(t.data)) as im:
        assert max(im.size) <= 320
    assert t.headers["Cache-Control"] == "private, max-age=3600"
    pn = _up(client, b["id"], fmt="PNG").get_json()
    assert client.get(pn["url"], headers=A).headers["Content-Type"] == "image/png"


def test_serve_thumb_falls_back_when_missing(client, app):
    b = _mk(client)
    p = _up(client, b["id"]).get_json()
    for f in _files(app):
        if f.endswith(".thumb.jpg"):
            os.remove(f)
    r = client.get(p["thumb_url"], headers=A)
    assert r.status_code == 200 and r.headers["Content-Type"] == "image/png"


def test_photo_must_belong_to_bookmark(client):
    b1, b2 = _mk(client), _mk(client)
    p = _up(client, b1["id"]).get_json()
    assert client.get(f"/api/bookmarks/{b2['id']}/photos/{p['id']}", headers=A).status_code == 404
    assert client.delete(f"/api/bookmarks/{b2['id']}/photos/{p['id']}", headers=A).status_code == 404
    assert client.get(p["url"], headers=A).status_code == 200


def test_cross_user_404(client, app):
    b = _mk(client)
    p = _up(client, b["id"]).get_json()
    n = len(_files(app))
    assert _up(client, b["id"], headers=B).status_code == 404
    assert client.get(p["url"], headers=B).status_code == 404
    assert client.get(p["thumb_url"], headers=B).status_code == 404
    assert client.delete(f"/api/bookmarks/{b['id']}/photos/{p['id']}", headers=B).status_code == 404
    assert client.put(f"/api/bookmarks/{b['id']}/photos/order", json={"ids": [p["id"]]},
                      headers=B).status_code == 404
    assert len(_files(app)) == n
    assert client.get(p["url"], headers=A).status_code == 200


def test_no_pillow_fallback(client, app, monkeypatch):
    from server import bookmark_photos
    monkeypatch.setattr(bookmark_photos, "PILLOW_AVAILABLE", False)
    monkeypatch.setattr(bookmark_photos, "_warned", False)
    b = _mk(client)
    raw = _img()
    r = _up(client, b["id"], data=raw)
    assert r.status_code == 201
    assert not any(f.endswith(".thumb.jpg") for f in _files(app))
    t = client.get(r.get_json()["thumb_url"], headers=A)
    assert t.status_code == 200 and t.data == raw


def test_db_failure_cleans_files(client, app, monkeypatch):
    b = _mk(client)
    from server.models import bookmarks as bm

    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(bm, "add_photo", boom)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    r = _up(client, b["id"])
    assert r.status_code == 500
    assert _files(app) == []
