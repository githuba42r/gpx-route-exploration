"""Tests for GPX -> recipe conversion (server/gpx_recipe.py + endpoint)."""

import io
import os
from unittest.mock import patch

import pytest

from server.gpx_recipe import extract_waypoints
from server.routing.gpx_writer import encode_polyline


def _gpx(points):
    pts = "".join(f'<trkpt lat="{la}" lon="{lo}"></trkpt>' for la, lo in points)
    return (
        '<?xml version="1.0"?><gpx version="1.1" creator="t" '
        'xmlns="http://www.topografix.com/GPX/1/1">'
        f"<trk><trkseg>{pts}</trkseg></trk></gpx>"
    ).encode()


def _straight(n):
    return [(-27.0 - i * 0.001, 152.0) for i in range(n)]


def test_extract_even_by_distance():
    pts = _straight(11)
    out = extract_waypoints(_gpx(pts), count=6)
    assert [(w["lat"], w["lon"]) for w in out] == [pts[i] for i in (0, 2, 4, 6, 8, 10)]
    assert [w["name"] for w in out] == [f"Point {i}" for i in range(1, 7)]


def test_extract_fewer_points_than_count_returns_all():
    pts = _straight(4)
    out = extract_waypoints(_gpx(pts), count=6)
    assert [(w["lat"], w["lon"]) for w in out] == pts


def test_extract_two_point_track():
    pts = _straight(2)
    out = extract_waypoints(_gpx(pts), count=6)
    assert [(w["lat"], w["lon"]) for w in out] == pts


def test_extract_rejects_invalid_xml_and_short_tracks():
    with pytest.raises(ValueError):
        extract_waypoints(b"not xml at all")
    with pytest.raises(ValueError):
        extract_waypoints(_gpx([]))
    with pytest.raises(ValueError):
        extract_waypoints(_gpx(_straight(1)))
    with pytest.raises(ValueError):
        extract_waypoints(_gpx(_straight(5)), count=1)


def test_extract_uneven_spacing_uses_distance_not_index():
    # 50 points packed in the first 0.0049 deg, then 5 points spread to 0.1 deg.
    pts = [(-27.0 - i * 0.0001, 152.0) for i in range(50)]
    pts += [(-27.0 - 0.02 * k, 152.0) for k in range(1, 6)]
    out = extract_waypoints(_gpx(pts), count=3)
    assert out[0]["lat"] == pts[0][0] and out[-1]["lat"] == pts[-1][0]
    # Middle point sits near half the distance (~-27.05), not index-middle (~-27.0045).
    assert out[1]["lat"] < -27.04


def _upload(client, data, user="user-a"):
    return client.post(
        "/api/routes",
        data={"file": (io.BytesIO(data), "t.gpx"), "title": "T"},
        content_type="multipart/form-data",
        headers={"Remote-User": user},
    )


def _stored(app, storage_name):
    for root, _, files in os.walk(os.path.join(app.config["DATA_DIR"], "gpx")):
        if storage_name in files:
            return os.path.join(root, storage_name)
    return None


def _fixture_points(sample_gpx):
    import re
    return [(float(a), float(b)) for a, b in
            re.findall(rb'<trkpt lat="([^"]+)" lon="([^"]+)"', sample_gpx)]


def test_convert_default_creates_six_waypoints(client, sample_gpx):
    rid = _upload(client, sample_gpx).get_json()["id"]
    resp = client.post(f"/api/routes/{rid}/convert-to-recipe", headers={"Remote-User": "user-a"})
    assert resp.status_code == 200, resp.data
    body = resp.get_json()
    assert body["route_id"] == rid and body["count"] == 6
    wps = body["waypoints"]
    assert len(wps) == 6
    assert [w["position"] for w in wps] == list(range(6))
    assert all(w["kind"] == "waypoint" and w["included"] == 1 for w in wps)
    pts = _fixture_points(sample_gpx)
    assert (wps[0]["lat"], wps[0]["lon"]) == pts[0]
    assert (wps[-1]["lat"], wps[-1]["lon"]) == pts[-1]
    got = client.get(f"/api/routes/{rid}", headers={"Remote-User": "user-a"}).get_json()
    assert got["has_recipe"]
    listed = client.get(f"/api/routes/{rid}/waypoints", headers={"Remote-User": "user-a"}).get_json()
    assert len(listed) == 6


def test_convert_leaves_gpx_file_untouched(client, app, sample_gpx):
    up = _upload(client, sample_gpx).get_json()
    client.post(f"/api/routes/{up['id']}/convert-to-recipe", headers={"Remote-User": "user-a"})
    path = _stored(app, up["storage_name"])
    with open(path, "rb") as f:
        assert f.read() == sample_gpx


def test_convert_custom_count_and_bad_counts(client, sample_gpx):
    h = {"Remote-User": "user-a"}
    rid = _upload(client, sample_gpx).get_json()["id"]
    url = f"/api/routes/{rid}/convert-to-recipe"
    for bad in (0, 1, 51, "abc", 2.5):
        r = client.post(url, json={"count": bad}, headers=h)
        assert r.status_code == 400, bad
        assert "error" in r.get_json()
    assert client.get(f"/api/routes/{rid}/waypoints", headers=h).get_json() == []
    r = client.post(url, json={"count": 3}, headers=h)
    assert r.status_code == 200 and len(r.get_json()["waypoints"]) == 3

    rid2 = _upload(client, sample_gpx).get_json()["id"]
    r = client.post(f"/api/routes/{rid2}/convert-to-recipe", json={}, headers=h)
    assert r.status_code == 200 and r.get_json()["count"] == 6


def test_convert_twice_is_409_and_creates_no_duplicates(client, sample_gpx):
    h = {"Remote-User": "user-a"}
    rid = _upload(client, sample_gpx).get_json()["id"]
    url = f"/api/routes/{rid}/convert-to-recipe"
    assert client.post(url, headers=h).status_code == 200
    r = client.post(url, headers=h)
    assert r.status_code == 409
    assert r.get_json() == {"error": "Route already has a recipe"}
    assert len(client.get(f"/api/routes/{rid}/waypoints", headers=h).get_json()) == 6


def test_convert_unknown_foreign_and_fileless_routes(client, sample_gpx):
    r = client.post("/api/routes/99999/convert-to-recipe", headers={"Remote-User": "user-a"})
    assert r.status_code == 404 and r.get_json() == {"error": "Not found"}

    rid = _upload(client, sample_gpx, user="user-a").get_json()["id"]
    r = client.post(f"/api/routes/{rid}/convert-to-recipe", headers={"Remote-User": "user-b"})
    assert r.status_code == 404 and r.get_json() == {"error": "Not found"}

    rid = client.post("/api/routes", json={"title": "R"}, headers={"Remote-User": "user-a"}).get_json()["id"]
    r = client.post(f"/api/routes/{rid}/convert-to-recipe", headers={"Remote-User": "user-a"})
    assert r.status_code == 404
    assert r.get_json() == {"error": "Route has no GPX file"}


def test_converted_route_can_generate_and_keeps_original_backup(client, app, sample_gpx):
    up = _upload(client, sample_gpx).get_json()
    rid = up["id"]
    h = {"Remote-User": "user-a"}
    assert client.post(f"/api/routes/{rid}/convert-to-recipe", headers=h).status_code == 200
    legs = [
        {"summary": {"length": 1.0, "time": 300.0},
         "shape": encode_polyline([(-27.40 - i * 0.01, 152.9), (-27.41 - i * 0.01, 152.9)], precision=6)}
        for i in range(5)
    ]
    fake = {"trip": {"legs": legs, "summary": {"length": 5.0, "time": 1500.0}}}
    with patch("server.routing.valhalla_client.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = fake
        mock_post.return_value.raise_for_status = lambda: None
        resp = client.post(f"/api/routes/{rid}/generate", headers=h)
    assert resp.status_code == 200, resp.data
    assert resp.get_json()["legs_count"] == 5
    orig = _stored(app, up["storage_name"] + ".orig")
    assert orig is not None
    with open(orig, "rb") as f:
        assert f.read() == sample_gpx
