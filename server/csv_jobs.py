import json
import logging
import threading
import time
import uuid

from server.geocode_client import GeocodeError, geocode_address
from server.models import waypoints as wp_model

log = logging.getLogger(__name__)

JOB_TTL_S = 600

_jobs = {}
_jobs_lock = threading.Lock()


class Job:
    def __init__(self, id, user_id, route_id, append, total):
        self.id = id
        self.user_id = user_id
        self.route_id = route_id
        self.append = append
        self.total = total
        self.events = []
        self.done = False
        self.finished_at = None
        self.cond = threading.Condition()

    def emit(self, name, data):
        with self.cond:
            self.events.append((name, data))
            self.cond.notify_all()


def _purge_old_jobs():
    now = time.time()
    with _jobs_lock:
        stale = [jid for jid, j in _jobs.items()
                 if j.done and j.finished_at is not None
                 and now - j.finished_at > JOB_TTL_S]
        for jid in stale:
            del _jobs[jid]


def start_job(app, *, user_id, route_id, rows, append):
    _purge_old_jobs()
    job = Job(uuid.uuid4().hex, user_id, route_id, append, len(rows))
    with _jobs_lock:
        _jobs[job.id] = job
    threading.Thread(target=run_job, args=(app, job, rows), daemon=True).start()
    return job


def get_job(job_id, user_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None or job.user_id != user_id:
        return None
    return job


def _resolve(row):
    """Return (status, lat, lon, error) for a row."""
    if row.get("error"):
        return "failed", None, None, row["error"]
    if row.get("lat") is not None and row.get("lon") is not None:
        return "direct", row["lat"], row["lon"], None
    address = row.get("address")
    try:
        result = geocode_address(address)
    except GeocodeError:
        return "failed", None, None, "geocoding service unavailable"
    except Exception:
        log.exception("Unexpected error geocoding CSV row")
        return "failed", None, None, "unexpected error"
    if result is None:
        return "failed", None, None, f"no match for '{address}'"
    return "geocoded", result["lat"], result["lon"], None


def _process_row(job, row):
    status, lat, lon, error = _resolve(row)
    name = row.get("name") or row.get("address") or f"Row {row.get('index')}"
    description = row.get("description")
    if status == "failed":
        note = f"Import failed: {error}"
        description = f"{description}\n{note}" if description else note
    wp = wp_model.append_waypoint(
        job.route_id, name=name, lat=lat, lon=lon, kind="stop",
        address=row.get("address"), description=description,
        included=0 if status == "failed" else 1,
    )
    job.emit("row", {
        "index": row.get("index"), "status": status, "lat": lat, "lon": lon,
        "waypoint_id": wp["id"], "name": name, "error": error,
    })
    return status


def run_job(app, job, rows):
    failed = 0
    ok = 0
    try:
        with app.app_context():
            for row in rows:
                try:
                    status = _process_row(job, row)
                except Exception:
                    log.exception("CSV import row failed")
                    failed += 1
                    job.emit("row", {
                        "index": row.get("index"), "status": "failed",
                        "lat": None, "lon": None, "waypoint_id": None,
                        "name": row.get("name"), "error": "unexpected error",
                    })
                    continue
                if status == "failed":
                    failed += 1
                else:
                    ok += 1
    except Exception:
        log.exception("CSV import job crashed")
    finally:
        done = {"route_id": job.route_id, "total": job.total, "failed": failed}
        done["appended" if job.append else "created"] = ok
        with job.cond:
            job.events.append(("done", done))
            job.done = True
            job.finished_at = time.time()
            job.cond.notify_all()


def _frame(name, data):
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


def iter_events(job, heartbeat_s=15.0):
    idx = 0
    while True:
        with job.cond:
            deadline = time.monotonic() + heartbeat_s
            while idx >= len(job.events):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                job.cond.wait(remaining)
            pending = job.events[idx:]
        if not pending:
            yield ": keep-alive\n\n"
            continue
        for name, data in pending:
            idx += 1
            yield _frame(name, data)
            if name == "done":
                return
