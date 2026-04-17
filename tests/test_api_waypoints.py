"""REST tests for /api/routes/<id>/waypoints."""

import io


def _make_route(client):
    # Upload a minimal GPX to get a route row, then edit its recipe.
    gpx_bytes = b'<?xml version="1.0"?><gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">' \
                b'<metadata><name>API WP Test</name></metadata>' \
                b'<trk><trkseg><trkpt lat="-27.4" lon="152.9"><ele>10</ele></trkpt>' \
                b'<trkpt lat="-27.41" lon="152.91"><ele>11</ele></trkpt></trkseg></trk></gpx>'
    r = client.post(
        "/api/routes",
        data={"title": "API WP Test", "file": (io.BytesIO(gpx_bytes), "s.gpx")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 201, r.data
    return r.get_json()["id"]


def test_list_empty_waypoints(client):
    rid = _make_route(client)
    r = client.get(f"/api/routes/{rid}/waypoints")
    assert r.status_code == 200
    assert r.get_json() == []


def test_post_waypoint_appends(client):
    rid = _make_route(client)
    r = client.post(
        f"/api/routes/{rid}/waypoints",
        json={"name": "Home", "lat": -27.4, "lon": 152.9, "kind": "stop"},
    )
    assert r.status_code == 201
    body = r.get_json()
    assert body["name"] == "Home"
    assert body["position"] == 0
    assert body["kind"] == "stop"


def test_patch_waypoint(client):
    rid = _make_route(client)
    r = client.post(
        f"/api/routes/{rid}/waypoints",
        json={"name": "A", "lat": 0, "lon": 0, "kind": "waypoint"},
    )
    wid = r.get_json()["id"]
    r = client.patch(
        f"/api/routes/{rid}/waypoints/{wid}",
        json={"name": "A-updated", "kind": "stop", "dwell_minutes": 5},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["name"] == "A-updated"
    assert body["kind"] == "stop"
    assert body["dwell_minutes"] == 5


def test_delete_waypoint_repacks_positions(client):
    rid = _make_route(client)
    ids = []
    for n in ["A", "B", "C"]:
        r = client.post(
            f"/api/routes/{rid}/waypoints",
            json={"name": n, "lat": 0, "lon": 0, "kind": "stop"},
        )
        ids.append(r.get_json()["id"])
    r = client.delete(f"/api/routes/{rid}/waypoints/{ids[1]}")
    assert r.status_code == 204
    listing = client.get(f"/api/routes/{rid}/waypoints").get_json()
    assert [w["name"] for w in listing] == ["A", "C"]
    assert [w["position"] for w in listing] == [0, 1]


def test_put_reorders(client):
    rid = _make_route(client)
    ids = []
    for n in ["A", "B", "C"]:
        r = client.post(
            f"/api/routes/{rid}/waypoints",
            json={"name": n, "lat": 0, "lon": 0, "kind": "stop"},
        )
        ids.append(r.get_json()["id"])
    r = client.put(
        f"/api/routes/{rid}/waypoints",
        json={"order": [ids[2], ids[0], ids[1]]},
    )
    assert r.status_code == 200
    listing = r.get_json()
    assert [w["name"] for w in listing] == ["C", "A", "B"]


def test_post_rejects_unknown_kind(client):
    rid = _make_route(client)
    r = client.post(
        f"/api/routes/{rid}/waypoints",
        json={"name": "x", "lat": 0, "lon": 0, "kind": "nonsense"},
    )
    assert r.status_code == 400


def test_patch_unknown_waypoint_404(client):
    rid = _make_route(client)
    r = client.patch(f"/api/routes/{rid}/waypoints/99999", json={"name": "n"})
    assert r.status_code == 404
