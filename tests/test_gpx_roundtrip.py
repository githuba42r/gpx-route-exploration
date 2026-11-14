"""Round-trip tests for rich GPX export/import (M4)."""

import os
from unittest.mock import patch

from lxml import etree

from server.routing.gpx_writer import encode_polyline, write_track_gpx

NS = "{http://www.topografix.com/GPX/1/1}"


def _legs():
    return [
        {"polyline": encode_polyline([(-27.4, 152.9), (-27.41, 152.91)], precision=6)},
        {"polyline": encode_polyline([(-27.41, 152.91), (-27.42, 152.92)], precision=6)},
    ]


def _parse(path):
    return etree.parse(str(path)).getroot()


def test_writer_emits_wpt_between_metadata_and_trk(tmp_path):
    path = tmp_path / "o.gpx"
    wps = [
        {"name": "A", "lat": -27.4, "lon": 152.9, "kind": "stop"},
        {"name": "B", "lat": -27.41, "lon": 152.91, "kind": "waypoint"},
    ]
    write_track_gpx(str(path), title="T", legs=_legs(), waypoints=wps)
    root = _parse(path)
    tags = [etree.QName(c).localname for c in root]
    assert tags == ["metadata", "wpt", "wpt", "trk"]
    types = [w.find(f"{NS}type").text for w in root.findall(f"{NS}wpt")]
    assert types == ["stop", "waypoint"]
    first = root.find(f"{NS}wpt")
    assert [etree.QName(c).localname for c in first] == ["name", "type"]


def test_writer_wpt_omits_desc_when_empty(tmp_path):
    path = tmp_path / "o.gpx"
    wps = [
        {"name": "A", "lat": -27.4, "lon": 152.9, "kind": "stop", "description": None},
        {"name": "B", "lat": -27.41, "lon": 152.91, "kind": "stop",
         "description": "Café & <view>"},
    ]
    write_track_gpx(str(path), title="T", legs=_legs(), waypoints=wps)
    a, b = _parse(path).findall(f"{NS}wpt")
    assert a.find(f"{NS}desc") is None
    assert b.find(f"{NS}desc").text == "Café & <view>"
    assert [etree.QName(c).localname for c in b] == ["name", "desc", "type"]


def test_writer_without_waypoints_has_no_wpt(tmp_path):
    path = tmp_path / "o.gpx"
    write_track_gpx(str(path), title="T", legs=_legs(), waypoints=None)
    root = _parse(path)
    assert root.findall(f"{NS}wpt") == []
    assert len(root.findall(f".//{NS}trkpt")) == 3


def _one_leg_valhalla_response():
    leg = encode_polyline([(-27.40, 152.90), (-27.42, 152.92)], precision=6)
    return {"trip": {"legs": [{"summary": {"length": 2.0, "time": 400.0}, "shape": leg}],
                     "summary": {"length": 2.0, "time": 400.0}}}


def test_generate_writes_wpt_for_included_waypoints_only(client, app):
    rid = client.post("/api/routes", json={"title": "Rec", "profile": "bicycle"}).get_json()["id"]
    ids = []
    for name, lat, lon in [("A", -27.40, 152.90), ("B", -27.41, 152.91), ("C", -27.42, 152.92)]:
        r = client.post(f"/api/routes/{rid}/waypoints",
                        json={"name": name, "lat": lat, "lon": lon, "kind": "stop"})
        ids.append(r.get_json()["id"])
    r = client.patch(f"/api/routes/{rid}/waypoints/{ids[1]}", json={"included": 0})
    assert r.status_code == 200, r.data
    with patch("server.routing.valhalla_client.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = _one_leg_valhalla_response()
        mock_post.return_value.raise_for_status = lambda: None
        resp = client.post(f"/api/routes/{rid}/generate")
    assert resp.status_code == 200, resp.data
    stored = None
    for root_dir, _, files in os.walk(os.path.join(app.config["DATA_DIR"], "gpx")):
        for f in files:
            if f.endswith(".gpx") and os.path.getsize(os.path.join(root_dir, f)) > 0:
                stored = os.path.join(root_dir, f)
    assert stored
    names = [w.find(f"{NS}name").text for w in _parse(stored).findall(f"{NS}wpt")]
    assert names == ["A", "C"]
