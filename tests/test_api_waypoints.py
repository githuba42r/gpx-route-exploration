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


def test_post_with_position_inserts_and_shifts(client):
    """POST /waypoints with a `position` field inserts at that slot and
    shifts subsequent rows up by one — used by the line-drag feature."""
    rid = _make_route(client)
    for i, name in enumerate(["A", "B", "C"]):
        r = client.post(
            f"/api/routes/{rid}/waypoints",
            json={"name": name, "lat": i, "lon": i, "kind": "stop"},
        )
        assert r.status_code == 201

    r = client.post(
        f"/api/routes/{rid}/waypoints",
        json={"name": "X", "lat": 0.5, "lon": 0.5,
              "kind": "waypoint", "position": 1},
    )
    assert r.status_code == 201
    assert r.get_json()["position"] == 1

    listing = client.get(f"/api/routes/{rid}/waypoints").get_json()
    assert [w["name"] for w in listing] == ["A", "X", "B", "C"]
    assert [w["position"] for w in listing] == [0, 1, 2, 3]


def test_post_without_position_still_appends(client):
    """Back-compat: omitting position keeps the M1 append-at-tail behaviour."""
    rid = _make_route(client)
    client.post(f"/api/routes/{rid}/waypoints",
                json={"name": "A", "lat": 0, "lon": 0, "kind": "stop"})
    r = client.post(f"/api/routes/{rid}/waypoints",
                    json={"name": "B", "lat": 1, "lon": 1, "kind": "stop"})
    assert r.status_code == 201
    assert r.get_json()["position"] == 1


def test_post_waypoint_accepts_linked_to_previous(client, app):
    """POST /waypoints accepts linked_to_previous=0 to opt out of linkage."""
    rid = client.post("/api/routes", json={"title": "L"},
                      content_type="application/json").get_json()["id"]
    resp = client.post(f"/api/routes/{rid}/waypoints", json={
        "name": "W", "lat": 0, "lon": 0, "kind": "waypoint",
        "linked_to_previous": 0,
    })
    assert resp.status_code == 201
    assert resp.get_json()["linked_to_previous"] == 0


def test_post_waypoint_defaults_linked_to_previous_to_1(client, app):
    rid = client.post("/api/routes", json={"title": "L"},
                      content_type="application/json").get_json()["id"]
    resp = client.post(f"/api/routes/{rid}/waypoints", json={
        "name": "W", "lat": 0, "lon": 0, "kind": "waypoint",
    })
    assert resp.status_code == 201
    assert resp.get_json()["linked_to_previous"] == 1


def test_patch_waypoint_can_toggle_link(client, app):
    rid = client.post("/api/routes", json={"title": "L"},
                      content_type="application/json").get_json()["id"]
    w = client.post(f"/api/routes/{rid}/waypoints", json={
        "name": "W", "lat": 0, "lon": 0, "kind": "waypoint",
    }).get_json()
    resp = client.patch(f"/api/routes/{rid}/waypoints/{w['id']}",
                        json={"linked_to_previous": 0})
    assert resp.status_code == 200
    assert resp.get_json()["linked_to_previous"] == 0
    # Toggle back.
    resp = client.patch(f"/api/routes/{rid}/waypoints/{w['id']}",
                        json={"linked_to_previous": True})
    assert resp.get_json()["linked_to_previous"] == 1
