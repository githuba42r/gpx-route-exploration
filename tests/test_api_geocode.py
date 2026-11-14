import io
import json
from unittest.mock import MagicMock, patch

import pytest
import requests

MAP_COORDS = {"name": "Name", "lat": "Lat", "lon": "Lon"}
MAP_ADDR = {"name": "Name", "address": "Address", "lat": "Lat", "lon": "Lon"}
H = {"Remote-User": "user-a"}


@pytest.fixture(autouse=True)
def _no_rate_limit(app):
    app.config["NOMINATIM_RATE_LIMIT_MS"] = 0


def post_csv(client, text, mapping, filename="stops.csv", query="", headers=H, **form):
    data = {"file": (io.BytesIO(text.encode()), filename), "mapping": json.dumps(mapping)}
    data.update(form)
    return client.post(f"/api/geocode/csv{query}", data=data,
                       content_type="multipart/form-data", headers=headers)


def parse_sse(text):
    events = []
    for frame in text.split("\n\n"):
        ev = data = None
        for line in frame.splitlines():
            if line.startswith("event: "):
                ev = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if ev:
            events.append((ev, data))
    return events


def run(client, resp, headers=H):
    assert resp.status_code == 202, resp.data
    body = resp.get_json()
    s = client.get(f"/api/geocode/csv/{body['job_id']}/stream", headers=headers)
    assert s.status_code == 200
    assert s.mimetype == "text/event-stream"
    return body, parse_sse(s.get_data(as_text=True))


def waypoints(client, route_id):
    r = client.get(f"/api/routes/{route_id}/waypoints", headers=H)
    assert r.status_code == 200, r.data
    body = r.get_json()
    return body["waypoints"] if isinstance(body, dict) else body


def hit(lat, lon):
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = [{"lat": str(lat), "lon": str(lon), "display_name": "X"}]
    return m


CSV3 = "Name,Lat,Lon\nA,1.0,2.0\nB,3.0,4.0\nC,5.0,6.0\n"


def test_new_route_import_returns_202_and_streams_rows_then_done(client):
    body, events = run(client, post_csv(client, CSV3, MAP_COORDS))
    assert body["job_id"] and body["route_id"] and body["append"] is False
    assert [e for e, _ in events] == ["row", "row", "row", "done"]
    assert events[-1][1]["created"] == 3
    wps = waypoints(client, body["route_id"])
    assert len(wps) == 3 and all(w["included"] for w in wps)
    route = client.get(f"/api/routes/{body['route_id']}", headers=H).get_json()
    assert route["title"] == "stops"


def test_mixed_addresses_and_coordinates_with_cache(client):
    text = "Name,Address,Lat,Lon\nA,1 Main St,,\nB,1 MAIN ST,,\nC,,5.0,6.0\n"
    with patch("server.geocode_client.requests.get", return_value=hit(10, 20)) as g:
        body, events = run(client, post_csv(client, text, MAP_ADDR))
    assert g.call_count == 1
    assert events[-1][1]["created"] == 3
    wps = waypoints(client, body["route_id"])
    assert len(wps) == 3 and all(w["included"] for w in wps)


def test_failed_rows_are_visible_not_dropped(client):
    text = "Name,Lat,Lon\nA,1.0,2.0\nBroken,,\n"
    body, events = run(client, post_csv(client, text, MAP_COORDS))
    assert events[-1][1]["failed"] == 1
    wps = waypoints(client, body["route_id"])
    bad = [w for w in wps if not w["included"]]
    assert len(bad) == 1
    assert bad[0]["lat"] is None and bad[0]["lon"] is None
    assert "Import failed:" in bad[0]["description"]


def test_append_mode_adds_after_existing_waypoints_without_creating_a_route(client):
    first, _ = run(client, post_csv(client, "Name,Lat,Lon\nA,1,2\nB,3,4\n", MAP_COORDS))
    rid = first["route_id"]
    text = "Name,Lat,Lon\n" + "".join(f"P{i},{i},{i}\n" for i in range(5))
    body, events = run(client, post_csv(client, text, MAP_COORDS, query=f"?route_id={rid}"))
    assert body["route_id"] == rid and body["append"] is True
    assert events[-1][1]["appended"] == 5
    assert len(waypoints(client, rid)) == 7
    assert len(client.get("/api/routes", headers=H).get_json()) == 1


def test_validation_errors_create_no_route(client, app):
    def empty():
        assert client.get("/api/routes", headers=H).get_json() == []

    r = client.post("/api/geocode/csv", data={"mapping": "{}"},
                    content_type="multipart/form-data", headers=H)
    assert r.status_code == 400 and r.get_json()["error"]
    empty()
    r = client.post("/api/geocode/csv",
                    data={"file": (io.BytesIO(CSV3.encode()), "a.csv"), "mapping": "nope"},
                    content_type="multipart/form-data", headers=H)
    assert r.status_code == 400
    empty()
    assert post_csv(client, CSV3, {"name": "Name"}).status_code == 400
    empty()
    assert post_csv(client, "Name,Lat,Lon\n", MAP_COORDS).status_code == 400
    empty()
    app.config["CSV_MAX_ROWS"] = 2
    assert post_csv(client, CSV3, MAP_COORDS).status_code == 400
    empty()
    app.config["CSV_MAX_ROWS"] = 500
    app.config["CSV_MAX_BYTES"] = 10
    assert post_csv(client, CSV3, MAP_COORDS).status_code == 413
    empty()


def test_append_to_unknown_or_foreign_route_404_and_stream_404(client):
    assert post_csv(client, CSV3, MAP_COORDS, query="?route_id=9999").status_code == 404
    body, _ = run(client, post_csv(client, CSV3, MAP_COORDS))
    other = {"Remote-User": "user-b"}
    r = post_csv(client, CSV3, MAP_COORDS, query=f"?route_id={body['route_id']}", headers=other)
    assert r.status_code == 404
    assert client.get("/api/geocode/csv/nope/stream", headers=H).status_code == 404
    assert client.get(f"/api/geocode/csv/{body['job_id']}/stream", headers=other).status_code == 404


def test_nominatim_down_mid_import_job_still_completes(client):
    text = "Name,Address\nA,1 Main St\nB,2 Main St\n"
    with patch("server.geocode_client.requests.get", side_effect=requests.ConnectionError("down")):
        body, events = run(client, post_csv(client, text, {"name": "Name", "address": "Address"}))
    assert events[-1][0] == "done"
    assert events[-1][1]["failed"] == 2
