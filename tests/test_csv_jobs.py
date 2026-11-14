import json
from unittest.mock import patch

from server import csv_jobs
from server.csv_jobs import Job, run_job, iter_events, get_job
from server.geocode_client import GeocodeError
from server.models import waypoints as wp_model


def _route(client):
    return client.post("/api/routes", json={"title": "T"}).get_json()["id"]


def _row(i, **kw):
    base = {"index": i, "name": f"S{i}", "address": None, "lat": 51.0 + i,
            "lon": -1.0, "description": None, "error": None}
    base.update(kw)
    return base


def _job(route_id, total, append=False):
    return Job("j1", "u1", route_id, append, total)


def _events(job, name):
    return [d for n, d in job.events if n == name]


def test_direct_rows_become_included_stops_in_order(app, client):
    rid = _route(client)
    rows = [_row(i) for i in range(3)]
    job = _job(rid, 3)
    run_job(app, job, rows)
    wps = wp_model.list_waypoints(rid)
    assert [w["position"] for w in wps] == [0, 1, 2]
    assert all(w["kind"] == "stop" and w["included"] == 1 for w in wps)
    assert [n for n, _ in job.events] == ["row", "row", "row", "done"]
    done = _events(job, "done")[0]
    assert done["created"] == 3 and done["total"] == 3 and done["failed"] == 0
    assert done["route_id"] == rid
    assert job.done is True
    assert _events(job, "row")[0]["status"] == "direct"


def test_append_mode_continues_after_existing_waypoints(app, client):
    rid = _route(client)
    for i in range(2):
        wp_model.append_waypoint(rid, name=f"M{i}", lat=1, lon=1, kind="stop")
    job = _job(rid, 3, append=True)
    run_job(app, job, [_row(i) for i in range(3)])
    wps = wp_model.list_waypoints(rid)
    assert [w["position"] for w in wps] == [0, 1, 2, 3, 4]
    done = _events(job, "done")[0]
    assert done["appended"] == 3 and "created" not in done


def test_geocoded_row_uses_result_and_keeps_address(app, client):
    rid = _route(client)
    row = _row(0, address="1 High St", lat=None, lon=None, description="d")
    job = _job(rid, 1)
    with patch("server.csv_jobs.geocode_address",
               return_value={"lat": 50.5, "lon": -2.5, "display_name": "x"}):
        run_job(app, job, [row])
    w = wp_model.list_waypoints(rid)[0]
    assert (w["lat"], w["lon"]) == (50.5, -2.5)
    assert w["address"] == "1 High St" and w["description"] == "d"
    assert _events(job, "row")[0]["status"] == "geocoded"


def test_failed_rows_kept_excluded_with_note(app, client):
    rid = _route(client)
    rows = [
        _row(0, lat=None, lon=None, error="bad lat", description="orig"),
        _row(1, address="nowhere", lat=None, lon=None),
        _row(2, address="boom", lat=None, lon=None),
    ]
    job = _job(rid, 3)

    def fake(addr):
        if addr == "nowhere":
            return None
        raise GeocodeError("down")

    with patch("server.csv_jobs.geocode_address", side_effect=fake):
        run_job(app, job, rows)
    wps = wp_model.list_waypoints(rid)
    assert len(wps) == 3
    for w in wps:
        assert w["included"] == 0 and w["lat"] is None and w["lon"] is None
        assert "Import failed:" in w["description"]
    assert wps[0]["description"] == "orig\nImport failed: bad lat"
    assert "no match for 'nowhere'" in wps[1]["description"]
    assert "geocoding service unavailable" in wps[2]["description"]
    done = _events(job, "done")[0]
    assert done["failed"] == 3 and done["created"] == 0
    assert all(e["status"] == "failed" for e in _events(job, "row"))


def test_unexpected_exception_in_one_row_does_not_stop_the_job(app, client):
    rid = _route(client)
    rows = [_row(0, address="a", lat=None, lon=None),
            _row(1, address="b", lat=None, lon=None)]
    job = _job(rid, 2)

    def fake(addr):
        if addr == "a":
            raise RuntimeError("kaboom")
        return {"lat": 1.0, "lon": 2.0, "display_name": None}

    with patch("server.csv_jobs.geocode_address", side_effect=fake):
        run_job(app, job, rows)
    r = _events(job, "row")
    assert r[0]["status"] == "failed" and r[0]["error"] == "unexpected error"
    assert r[1]["status"] == "geocoded"
    done = _events(job, "done")[0]
    assert done["failed"] == 1 and done["created"] == 1


def test_iter_events_yields_sse_frames_and_stops_after_done(app, client):
    rid = _route(client)
    job = _job(rid, 1)
    run_job(app, job, [_row(0)])
    frames = list(iter_events(job))
    assert len(frames) == 2
    row = job.events[0][1]
    assert frames[0] == f"event: row\ndata: {json.dumps(row)}\n\n"
    done = job.events[-1][1]
    assert frames[1] == f"event: done\ndata: {json.dumps(done)}\n\n"


def test_iter_events_heartbeat_when_idle():
    job = _job(1, 1)
    gen = iter_events(job, heartbeat_s=0.05)
    assert next(gen) == ": keep-alive\n\n"


def test_get_job_is_scoped_to_its_user(app, client):
    rid = _route(client)
    with patch.object(csv_jobs, "run_job"):
        job = csv_jobs.start_job(app, user_id="u1", route_id=rid, rows=[],
                                 append=False)
    assert get_job(job.id, "u1") is job
    assert get_job(job.id, "u2") is None
    assert get_job("nope", "u1") is None
