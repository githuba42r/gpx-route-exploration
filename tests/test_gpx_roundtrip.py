"""Round-trip tests for rich GPX export/import (M4)."""

import io
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


# --- Parser: <wpt> entries -------------------------------------------------

from server.gpx_parser import parse_gpx  # noqa: E402

_TRK = (
    "<trk><trkseg>"
    '<trkpt lat="-27.4467" lon="152.9293"><ele>68.2</ele></trkpt>'
    '<trkpt lat="-27.4475" lon="152.9290"><ele>72.5</ele></trkpt>'
    '<trkpt lat="-27.4483" lon="152.9285"><ele>78.0</ele></trkpt>'
    "</trkseg></trk>"
)


def _gpx_with(wpts: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<gpx version="1.1" creator="t" xmlns="http://www.topografix.com/GPX/1/1">'
        f"<metadata><name>T</name></metadata>{wpts}{_TRK}</gpx>"
    ).encode()


def test_parse_reads_wpt_kind_name_description():
    data = _gpx_with(
        '<wpt lat="-27.4" lon="152.9"><name>Cafe</name><desc>Coffee</desc>'
        "<type>stop</type></wpt>"
        '<wpt lat="-27.5" lon="153.0"><name>Turn</name><type>waypoint</type></wpt>'
    )
    wps = parse_gpx(data)["waypoints"]
    assert wps == [
        {"name": "Cafe", "lat": -27.4, "lon": 152.9, "kind": "stop", "description": "Coffee"},
        {"name": "Turn", "lat": -27.5, "lon": 153.0, "kind": "waypoint", "description": None},
    ]


def test_parse_wpt_unknown_or_missing_type_is_waypoint():
    data = _gpx_with(
        '<wpt lat="1" lon="2"><name>A</name><type>Summit</type></wpt>'
        '<wpt lat="1" lon="2"><name>B</name><type>STOP </type></wpt>'
        '<wpt lat="1" lon="2"><name>C</name></wpt>'
    )
    kinds = [w["kind"] for w in parse_gpx(data)["waypoints"]]
    assert kinds == ["waypoint", "stop", "waypoint"]


def test_parse_wpt_missing_name_gets_generated_name():
    data = _gpx_with('<wpt lat="1" lon="2"></wpt>')
    assert parse_gpx(data)["waypoints"][0]["name"] == "Waypoint 1"


def test_parse_wpt_bad_coordinates_skipped():
    data = _gpx_with(
        '<wpt lon="2"><name>nolat</name></wpt>'
        '<wpt lat="abc" lon="2"><name>abc</name></wpt>'
        '<wpt lat="91" lon="2"><name>hi</name></wpt>'
        '<wpt lat="1" lon="181"><name>wide</name></wpt>'
        '<wpt lat="1" lon="2"><name>ok</name></wpt>'
    )
    wps = parse_gpx(data)["waypoints"]
    assert [w["name"] for w in wps] == ["ok"]


def test_parse_without_wpt_returns_empty_list():
    with open("tests/fixtures/sample.gpx", "rb") as f:
        assert parse_gpx(f.read())["waypoints"] == []


# --- Upload: recipe from <wpt> ---------------------------------------------

def _upload(client, data: bytes):
    return client.post(
        "/api/routes",
        data={"file": (io.BytesIO(data), "r.gpx"), "title": "T"},
        content_type="multipart/form-data",
    )


def test_upload_with_wpt_creates_recipe(client):
    data = _gpx_with(
        '<wpt lat="-27.4" lon="152.9"><name>A</name><type>stop</type></wpt>'
        '<wpt lat="-27.41" lon="152.91"><name>B</name><type>waypoint</type></wpt>'
        '<wpt lat="-27.42" lon="152.92"><name>C</name></wpt>'
    )
    resp = _upload(client, data)
    assert resp.status_code == 201
    rid = resp.get_json()["id"]
    wps = client.get(f"/api/routes/{rid}/waypoints").get_json()
    assert isinstance(wps, list)
    assert [w["kind"] for w in wps] == ["stop", "waypoint", "waypoint"]
    assert [w["position"] for w in wps] == [0, 1, 2]
    assert client.get(f"/api/routes/{rid}").get_json()["has_recipe"] is True


def test_upload_without_wpt_has_no_recipe(client):
    with open("tests/fixtures/sample.gpx", "rb") as f:
        resp = _upload(client, f.read())
    assert resp.status_code == 201
    rid = resp.get_json()["id"]
    wps = client.get(f"/api/routes/{rid}/waypoints").get_json()
    assert isinstance(wps, list)
    assert wps == []
    assert client.get(f"/api/routes/{rid}").get_json()["has_recipe"] is False


def test_upload_with_only_bad_wpt_still_succeeds(client):
    data = _gpx_with(
        '<wpt lat="abc" lon="2"><name>x</name></wpt>'
        '<wpt lat="91" lon="2"><name>y</name></wpt>'
    )
    resp = _upload(client, data)
    assert resp.status_code == 201
    rid = resp.get_json()["id"]
    assert client.get(f"/api/routes/{rid}").get_json()["has_recipe"] is False


# --- Export endpoint + round trip -------------------------------------------

def test_export_serves_stored_file_as_attachment(client):
    with open("tests/fixtures/sample.gpx", "rb") as f:
        original = f.read()
    rid = _upload(client, original).get_json()["id"]
    resp = client.get(f"/api/routes/{rid}/export.gpx")
    assert resp.status_code == 200
    assert resp.data == original
    assert "attachment" in resp.headers["Content-Disposition"]
    assert resp.mimetype == "application/gpx+xml"


def test_export_unknown_route_404(client):
    resp = client.get("/api/routes/99999/export.gpx")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Not found"}


def test_export_never_generated_recipe_route_404(client):
    rid = client.post("/api/routes", json={"title": "Rec", "profile": "bicycle"}).get_json()["id"]
    resp = client.get(f"/api/routes/{rid}/export.gpx")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Route has no GPX file yet — generate it first"}


def test_roundtrip_recipe_survives_export_and_reimport(client):
    rid = client.post("/api/routes", json={"title": "Rec", "profile": "bicycle"}).get_json()["id"]
    specs = [
        ("Start", -27.400000, 152.900000, "stop", None),
        ("Café & <Bar>", -27.410000, 152.910000, "stop", "Say \"hi\" 🚴"),
        ("Via one", -27.420000, 152.920000, "waypoint", None),
        ("Hill", -27.430000, 152.930000, "stop", "Steep"),
        ("Via two", -27.440000, 152.940000, "waypoint", ""),
    ]
    for name, lat, lon, kind, desc in specs:
        body = {"name": name, "lat": lat, "lon": lon, "kind": kind}
        if desc is not None:
            body["description"] = desc
        r = client.post(f"/api/routes/{rid}/waypoints", json=body)
        assert r.status_code in (200, 201), r.data

    legs = []
    for (_, la1, lo1, *_r), (_, la2, lo2, *_r2) in zip(specs, specs[1:]):
        shape = encode_polyline([(la1, lo1), (la2, lo2)], precision=6)
        legs.append({"summary": {"length": 1.0, "time": 100.0}, "shape": shape})
    fake = {"trip": {"legs": legs, "summary": {"length": 4.0, "time": 400.0}}}
    with patch("server.routing.valhalla_client.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = fake
        mock_post.return_value.raise_for_status = lambda: None
        resp = client.post(f"/api/routes/{rid}/generate")
    assert resp.status_code == 200, resp.data

    exp = client.get(f"/api/routes/{rid}/export.gpx")
    assert exp.status_code == 200
    new_id = _upload(client, exp.data).get_json()["id"]

    def norm(route_id):
        wps = client.get(f"/api/routes/{route_id}/waypoints").get_json()
        return [(w["name"], round(w["lat"], 6), round(w["lon"], 6), w["kind"],
                 (w.get("description") or None)) for w in wps]

    original = norm(rid)
    assert len(original) == 5
    assert norm(new_id) == original
