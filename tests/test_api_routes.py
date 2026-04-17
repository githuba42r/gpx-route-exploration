import io
import pytest


def upload(client, sample_gpx, title="My Route", user="user-a", filename="test.gpx"):
    headers = {"Remote-User": user}
    data = {"file": (io.BytesIO(sample_gpx), filename)}
    if title is not None:
        data["title"] = title
    return client.post(
        "/api/routes",
        data=data,
        content_type="multipart/form-data",
        headers=headers,
    )


def test_upload_gpx(client, sample_gpx):
    resp = upload(client, sample_gpx, title="My Route")
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["title"] == "My Route"
    assert body["distance_km"] is not None
    assert body["point_count"] == 10
    assert body["max_elevation"] is not None


def test_upload_uses_gpx_name_as_default_title(client, sample_gpx):
    resp = upload(client, sample_gpx, title=None)
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["title"] == "Test Route"


def test_upload_requires_title_when_gpx_has_none(client, sample_gpx_no_name):
    resp = upload(client, sample_gpx_no_name, title=None)
    assert resp.status_code == 400
    body = resp.get_json()
    assert "title" in body["error"].lower() or "required" in body["error"].lower()


def test_upload_invalid_file(client):
    headers = {"Remote-User": "user-a"}
    resp = client.post(
        "/api/routes",
        data={"file": (io.BytesIO(b"not gpx content"), "bad.gpx"), "title": "Bad"},
        content_type="multipart/form-data",
        headers=headers,
    )
    assert resp.status_code == 400


def test_list_routes(client, sample_gpx):
    upload(client, sample_gpx, title="Route 1")
    upload(client, sample_gpx, title="Route 2")
    resp = client.get("/api/routes", headers={"Remote-User": "user-a"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body) == 2
    titles = {r["title"] for r in body}
    assert titles == {"Route 1", "Route 2"}


def test_get_route(client, sample_gpx):
    up = upload(client, sample_gpx, title="Single Route")
    route_id = up.get_json()["id"]
    resp = client.get(f"/api/routes/{route_id}", headers={"Remote-User": "user-a"})
    assert resp.status_code == 200
    assert resp.get_json()["title"] == "Single Route"


def test_get_route_not_found(client):
    resp = client.get("/api/routes/999999", headers={"Remote-User": "user-a"})
    assert resp.status_code == 404


def test_update_route_metadata(client, sample_gpx):
    up = upload(client, sample_gpx, title="Old Title")
    route_id = up.get_json()["id"]
    resp = client.patch(
        f"/api/routes/{route_id}",
        json={"title": "New Title", "description": "A desc", "notes": "Some notes"},
        headers={"Remote-User": "user-a"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["title"] == "New Title"
    assert body["description"] == "A desc"
    assert body["notes"] == "Some notes"


def test_delete_route(client, sample_gpx):
    up = upload(client, sample_gpx, title="To Delete")
    route_id = up.get_json()["id"]

    del_resp = client.delete(f"/api/routes/{route_id}", headers={"Remote-User": "user-a"})
    assert del_resp.status_code == 204

    get_resp = client.get(f"/api/routes/{route_id}", headers={"Remote-User": "user-a"})
    assert get_resp.status_code == 404


def test_serve_gpx(client, sample_gpx):
    up = upload(client, sample_gpx, title="Serveable")
    route_id = up.get_json()["id"]
    resp = client.get(f"/api/gpx/{route_id}", headers={"Remote-User": "user-a"})
    assert resp.status_code == 200
    assert b"<gpx" in resp.data


def test_user_routes_isolated(client, sample_gpx):
    upload(client, sample_gpx, title="User A Route", user="user-a")
    resp = client.get("/api/routes", headers={"Remote-User": "user-b"})
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_cross_user_route_access_denied(client, sample_gpx):
    up = upload(client, sample_gpx, title="Private", user="user-a")
    route_id = up.get_json()["id"]
    resp = client.get(f"/api/routes/{route_id}", headers={"Remote-User": "user-b"})
    assert resp.status_code == 404


def test_create_recipe_only_route(client):
    r = client.post(
        "/api/routes",
        json={"title": "Recipe only", "profile": "bicycle"},
        content_type="application/json",
    )
    assert r.status_code == 201, r.data
    body = r.get_json()
    assert body["title"] == "Recipe only"
    # storage_name must be populated (used later for the generated GPX path).
    assert body["storage_name"]
    # The route is retrievable via the existing GET endpoint.
    rid = body["id"]
    got = client.get(f"/api/routes/{rid}").get_json()
    assert "id" in got


def test_data_dir_resolved_to_absolute_path(app):
    """Regression: a relative DATA_DIR (e.g. ./data from .env.development)
    broke /api/gpx/<id> because Flask's send_file resolved the relative
    path against the app root_path (server/) instead of the process CWD,
    returning 500 FileNotFoundError. create_app must absolute-ise DATA_DIR."""
    import os
    with app.app_context():
        d = app.config["DATA_DIR"]
        assert os.path.isabs(d), f"DATA_DIR still relative: {d!r}"


def test_serve_gpx_after_upload_does_not_500(client):
    """End-to-end smoke: upload a GPX, then GET /api/gpx/<id>. Used to 500
    with FileNotFoundError when DATA_DIR was a relative path."""
    import io
    gpx = (b'<?xml version="1.0"?><gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">'
           b'<trk><trkseg><trkpt lat="-27.4" lon="152.9"><ele>10</ele></trkpt>'
           b'<trkpt lat="-27.41" lon="152.91"><ele>11</ele></trkpt></trkseg></trk></gpx>')
    r = client.post(
        "/api/routes",
        data={"title": "serve-gpx", "file": (io.BytesIO(gpx), "r.gpx")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 201, r.data
    rid = r.get_json()["id"]
    resp = client.get(f"/api/gpx/{rid}")
    assert resp.status_code == 200, resp.data
    assert b"<trkpt" in resp.data


def test_get_route_includes_has_recipe(client):
    r = client.post(
        "/api/routes",
        json={"title": "Recipe"},
        content_type="application/json",
    )
    rid = r.get_json()["id"]
    got = client.get(f"/api/routes/{rid}").get_json()
    assert got["has_recipe"] is False
    client.post(
        f"/api/routes/{rid}/waypoints",
        json={"name": "A", "lat": 0, "lon": 0, "kind": "stop"},
    )
    got = client.get(f"/api/routes/{rid}").get_json()
    assert got["has_recipe"] is True
