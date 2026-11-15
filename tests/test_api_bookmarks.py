import io

A = {"Remote-User": "user-a"}
B = {"Remote-User": "user-b"}


def _mk(client, headers=A, **kw):
    body = {"name": "Cafe", "lat": 10.0, "lon": 20.0}
    body.update(kw)
    return client.post("/api/bookmarks", json=body, headers=headers)


def test_create_get_list(client):
    r = _mk(client, description="nice", tags=["Food", "food", "Rest"])
    assert r.status_code == 201
    b = r.get_json()
    assert b["name"] == "Cafe" and b["description"] == "nice"
    assert sorted(t["name"] for t in b["tags"]) == ["Food", "Rest"]
    g = client.get(f"/api/bookmarks/{b['id']}", headers=A)
    assert g.status_code == 200 and g.get_json()["photos"] == []
    lst = client.get("/api/bookmarks", headers=A).get_json()
    assert len(lst) == 1 and lst[0]["photo_count"] == 0 and lst[0]["thumb_url"] is None
    assert sorted(lst[0]["tags"]) == ["Food", "Rest"]


def test_list_ordered_by_updated(client):
    a = _mk(client, name="A").get_json()
    _mk(client, name="B")
    from server.models import get_db
    get_db().execute("UPDATE bookmarks SET updated_at='2020-01-01 00:00:00'")
    get_db().commit()
    client.patch(f"/api/bookmarks/{a['id']}", json={"name": "A2"}, headers=A)
    assert [x["name"] for x in client.get("/api/bookmarks", headers=A).get_json()] == ["A2", "B"]


def test_patch_and_delete(client):
    b = _mk(client).get_json()
    r = client.patch(f"/api/bookmarks/{b['id']}", json={"lat": 5, "description": "z"}, headers=A)
    assert r.status_code == 200 and r.get_json()["lat"] == 5 and r.get_json()["name"] == "Cafe"
    assert client.patch(f"/api/bookmarks/{b['id']}", json={"lat": 99}, headers=A).status_code == 400
    assert client.patch(f"/api/bookmarks/{b['id']}", json={}, headers=A).status_code == 400
    assert client.delete(f"/api/bookmarks/{b['id']}", headers=A).status_code == 204
    assert client.get(f"/api/bookmarks/{b['id']}", headers=A).status_code == 404


def test_validation_on_create(client):
    for body in [
        {"name": "x", "lat": 91, "lon": 0},
        {"name": "x", "lat": 0, "lon": "x"},
        {"name": "x", "lat": 0, "lon": float("nan")},
        {"name": "", "lat": 0, "lon": 0},
        {"name": "a" * 121, "lat": 0, "lon": 0},
    ]:
        r = client.post("/api/bookmarks", json=body, headers=A)
        assert r.status_code == 400 and "error" in r.get_json()
    assert client.post("/api/bookmarks", data="notjson", headers=A).status_code == 400
    assert _mk(client, tags="notalist").status_code == 400
    assert client.get("/api/bookmarks", headers=A).get_json() == []


def test_tags_put_and_cloud(client):
    b = _mk(client).get_json()
    r = client.put(f"/api/bookmarks/{b['id']}/tags", json={"tags": ["Hill", "Cafe"]}, headers=A)
    assert r.status_code == 200
    assert [t["name"] for t in r.get_json()] == ["Cafe", "Hill"]
    r = client.put(f"/api/bookmarks/{b['id']}/tags", json={"tags": ["Hill"]}, headers=A)
    assert [t["name"] for t in r.get_json()] == ["Hill"]
    cloud = {t["name"]: t["usage_count"] for t in client.get("/api/tags", headers=A).get_json()}
    assert cloud["Hill"] == 1
    assert client.put(f"/api/bookmarks/{b['id']}/tags", json={"tags": "x"}, headers=A).status_code == 400
    tid = [t for t in client.get("/api/tags", headers=A).get_json() if t["name"] == "Hill"][0]["id"]
    assert client.delete(f"/api/tags/{tid}", headers=A).status_code == 204
    assert client.get(f"/api/bookmarks/{b['id']}", headers=A).get_json()["tags"] == []


def test_cross_user_404(client):
    b = _mk(client).get_json()
    i = b["id"]
    assert client.get(f"/api/bookmarks/{i}", headers=B).status_code == 404
    assert client.patch(f"/api/bookmarks/{i}", json={"name": "x"}, headers=B).status_code == 404
    assert client.put(f"/api/bookmarks/{i}/tags", json={"tags": ["a"]}, headers=B).status_code == 404
    assert client.delete(f"/api/bookmarks/{i}", headers=B).status_code == 404
    assert client.get("/api/bookmarks", headers=B).get_json() == []
    assert client.get(f"/api/bookmarks/{i}", headers=A).status_code == 200
    assert client.get("/api/bookmarks/99999", headers=A).status_code == 404


def _route_with_wp(client, sample_gpx, headers=A):
    rid = client.post("/api/routes", data={"file": (io.BytesIO(sample_gpx), "t.gpx"), "title": "T"},
                      content_type="multipart/form-data", headers=headers).get_json()["id"]
    wp = client.post(f"/api/routes/{rid}/waypoints",
                     json={"kind": "stop", "name": "Pub", "lat": 1.25, "lon": 2.5, "description": "ale"},
                     headers=headers)
    assert wp.status_code == 201
    return wp.get_json()["id"]


def test_from_waypoint(client, sample_gpx):
    wid = _route_with_wp(client, sample_gpx)
    r = client.post(f"/api/bookmarks/from-waypoint/{wid}", headers=A)
    assert r.status_code == 201
    b = r.get_json()
    assert (b["name"], b["lat"], b["lon"], b["description"]) == ("Pub", 1.25, 2.5, "ale")
    assert client.post(f"/api/bookmarks/from-waypoint/{wid}", headers=B).status_code == 404
    assert client.post("/api/bookmarks/from-waypoint/99999", headers=A).status_code == 404
    assert len(client.get("/api/bookmarks", headers=A).get_json()) == 1
