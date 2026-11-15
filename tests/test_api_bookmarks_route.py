"""POST /api/routes/<id>/waypoints/from-bookmark."""

import io

A = {"Remote-User": "user-a"}
B = {"Remote-User": "user-b"}

GPX = (b'<?xml version="1.0"?><gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">'
       b'<metadata><name>T</name></metadata><trk><trkseg><trkpt lat="-27.4" lon="152.9"><ele>1</ele></trkpt>'
       b'<trkpt lat="-27.41" lon="152.91"><ele>2</ele></trkpt></trkseg></trk></gpx>')


def _route(client, headers=A):
    r = client.post("/api/routes",
                    data={"title": "T", "file": (io.BytesIO(GPX), "s.gpx")},
                    content_type="multipart/form-data", headers=headers)
    assert r.status_code == 201, r.data
    return r.get_json()["id"]


def _bm(client, headers=A, **kw):
    body = {"name": "Cafe", "lat": 10.5, "lon": 20.5, "description": "nice"}
    body.update(kw)
    r = client.post("/api/bookmarks", json=body, headers=headers)
    assert r.status_code == 201
    return r.get_json()


def _add(client, rid, headers=A, **body):
    return client.post(f"/api/routes/{rid}/waypoints/from-bookmark", json=body, headers=headers)


def _wps(client, rid):
    return client.get(f"/api/routes/{rid}/waypoints", headers=A).get_json()


def test_append_default_kind_and_copy(client):
    rid, b = _route(client), _bm(client)
    r = _add(client, rid, bookmark_id=b["id"])
    assert r.status_code == 201
    w = r.get_json()
    assert w["kind"] == "stop" and w["position"] == 0
    assert (w["name"], w["lat"], w["lon"], w["description"]) == ("Cafe", 10.5, 20.5, "nice")
    assert w["address"] is None


def test_insert_at_position_shifts(client):
    rid, b = _route(client), _bm(client)
    for _ in range(2):
        assert _add(client, rid, bookmark_id=b["id"]).status_code == 201
    r = _add(client, rid, bookmark_id=b["id"], position=1, kind="waypoint")
    assert r.status_code == 201
    w = r.get_json()
    assert w["position"] == 1 and w["kind"] == "waypoint"
    assert [x["position"] for x in _wps(client, rid)] == [0, 1, 2]
    assert _wps(client, rid)[1]["id"] == w["id"]
    # head and tail bounds are valid
    assert _add(client, rid, bookmark_id=b["id"], position=0).status_code == 201
    assert _add(client, rid, bookmark_id=b["id"], position=4).status_code == 201


def test_no_live_link(client):
    rid, b = _route(client), _bm(client)
    w = _add(client, rid, bookmark_id=b["id"]).get_json()
    client.patch(f"/api/bookmarks/{b['id']}", json={"name": "Changed", "lat": 1}, headers=A)
    got = _wps(client, rid)[0]
    assert got["id"] == w["id"] and got["name"] == "Cafe" and got["lat"] == 10.5


def test_validation_400(client):
    rid, b = _route(client), _bm(client)
    bid = b["id"]
    bad = [
        {"bookmark_id": bid, "position": -1},
        {"bookmark_id": bid, "position": 99},
        {"bookmark_id": bid, "position": True},
        {"bookmark_id": bid, "position": "0"},
        {"bookmark_id": bid, "kind": "bogus"},
        {"bookmark_id": str(bid)},
        {"bookmark_id": True},
        {"bookmark_id": None},
        {},
    ]
    for body in bad:
        assert _add(client, rid, **body).status_code == 400, body
    assert _wps(client, rid) == []


def test_not_found(client):
    rid, b = _route(client), _bm(client)
    rb = _route(client, headers=B)
    bb = _bm(client, headers=B)
    foreign_bm = _add(client, rid, bookmark_id=bb["id"])
    unknown_bm = _add(client, rid, bookmark_id=99999)
    assert foreign_bm.status_code == 404 and unknown_bm.status_code == 404
    assert foreign_bm.get_json() == unknown_bm.get_json()
    assert _add(client, rb, bookmark_id=b["id"]).status_code == 404  # foreign route
    assert _add(client, 99999, bookmark_id=b["id"]).status_code == 404
    # route 404 takes precedence over body validation
    assert _add(client, rb, bookmark_id="x").status_code == 404
    assert _wps(client, rid) == []
