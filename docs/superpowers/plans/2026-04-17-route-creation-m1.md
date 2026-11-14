# Route Creation M1: Recipe Schema + Manual Route Creation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce the recipe schema (`route_waypoints` + `route_options` + `route_legs`) and ship a dedicated Create Route page where users click on a map to add stops and waypoints, then save and generate a detailed GPX via Valhalla. At the end of this plan, a user can go Library → "+ New Route" → click 3–5 places on a map → Save → Generate → land on the existing Analysis page and see the detailed road-snapped route with gradient colouring.

**Architecture:** Three new tables alongside the existing `routes` table carry the recipe (ordered waypoints, routing options, cached leg polylines). Three new Flask blueprints handle waypoint CRUD and Valhalla-backed route generation. A new `src/js/create/` frontend page shares editor components with `src/js/shared/` — the same modules will be reused by M2's inline Edit panel on the Analysis page. Click-to-add drops a waypoint (default kind `waypoint`) at the clicked lat/lon; right-click promotes to stop. Save persists the recipe only; Generate is the explicit action that hits Valhalla and writes the detailed GPX.

**Tech Stack:** Flask 3 + SQLite (existing), Leaflet 1.9.4 (existing, CDN), SortableJS 1.15 (new npm dep for drag-reorder), esbuild (existing bundler), pytest + Playwright (existing test stacks).

**Non-scope for M1** (deferred to later milestones, called out here to prevent scope creep):
- Full profile picker (locked to `bicycle` in M1; UI element present but disabled — M3 unlocks).
- NN + 2-opt optimisation (button present but disabled — M3).
- Include/exclude per-waypoint toggles (M3).
- Round-trip toggle (M3).
- Inline Edit panel on the Analysis page (M2).
- Rich GPX export with `<wpt>` entries (M4 — M1 writes track-only GPX).
- CSV upload (M5).
- Address autocomplete, right-click menus, loading indicators beyond a simple spinner (M6).
- Mobile responsive layout (M7).

---

## File structure

**Create:**
- `server/models/waypoints.py` — CRUD helpers for `route_waypoints`, `route_options`, `route_legs`.
- `server/blueprints/api_waypoints.py` — REST endpoints for waypoint CRUD.
- `server/blueprints/api_routing.py` — `/generate` endpoint; Valhalla integration.
- `server/routing/__init__.py` — new package marker.
- `server/routing/valhalla_client.py` — thin Valhalla HTTP client (request shape + response parsing + error mapping).
- `server/routing/gpx_writer.py` — writes a GPX 1.1 track file from decoded polylines. M1 version writes `<trk><trkseg><trkpt>` only; M4 will extend with `<wpt>`.
- `server/templates/create.html` — the Create Route page template.
- `src/js/create/app.js` — Create page entry point (bundled as `create.min.js`).
- `src/js/create/map.js` — Leaflet map init for the Create page.
- `src/js/shared/waypoint-markers.js` — stop/waypoint Leaflet `L.divIcon` factories.
- `src/js/shared/waypoint-editor.js` — sidebar editor widget (list, tabs, drag-reorder, collapse).
- `src/js/shared/route-api.js` — thin client for `/api/routes/...`, `/api/routes/.../waypoints`, `/api/routes/.../generate`.
- `src/css/create.css` — Create page styles (sidebar, tabs, icons, collapse).
- `src/css/create-bundle.css` — CSS bundle entry for the Create page.
- `tests/test_models_waypoints.py` — unit tests for the model layer.
- `tests/test_api_waypoints.py` — unit tests for waypoint CRUD blueprint.
- `tests/test_api_routing.py` — unit tests for `/generate` with mocked Valhalla.
- `tests/test_routing_valhalla_client.py` — tests for the Valhalla client in isolation (request shape, error handling).
- `tests/test_routing_gpx_writer.py` — tests for GPX writer.
- `tests/test_ui_create.py` — Playwright E2E tests for the Create page.
- `tests/fixtures/valhalla_response_sample.json` — a realistic mocked Valhalla response used across unit tests.

**Modify:**
- `server/models/schema.sql` — add three tables at the bottom (idempotent `CREATE TABLE IF NOT EXISTS`).
- `server/blueprints/__init__.py` — register two new blueprints.
- `server/blueprints/api_routes.py` — extend `POST /api/routes` to also accept a JSON body (no file) for creating recipe-only routes.
- `server/blueprints/pages.py` — add `GET /create` route serving `create.html`.
- `src/js/library/library-app.js` — add a "+ New Route" button that navigates to `/create`.
- `build.js` — add `create.min.js` + `create.min.css` bundle entries.
- `package.json` — add `sortablejs` dependency.
- `tests/test_api_routes.py` — extend: JSON POST path creates a recipe-only route.

---

### Task 1: Branch verification and SortableJS dependency

**Files:**
- Modify: `package.json`

- [ ] **Step 1: Verify the branch**

```bash
git rev-parse --abbrev-ref HEAD
```

Expected: `feature/route-creation`. If not, `git checkout feature/route-creation` first. The plan assumes this branch.

- [ ] **Step 2: Confirm working tree is clean and up-to-date**

```bash
git status --short && git log --oneline -3
```

Expected: no working-tree changes, last commit is the M7 mobile addition (`94c9843` or later).

- [ ] **Step 3: Install SortableJS as a dev dependency**

Sortable isn't a runtime npm dep of the server — it's bundled into the frontend by esbuild. Adding it as a regular dep is correct.

```bash
npm install sortablejs@^1.15
```

- [ ] **Step 4: Verify it's listed**

```bash
grep sortablejs package.json
```

Expected: a `"sortablejs": "^1.15...."` line.

- [ ] **Step 5: Commit**

```bash
git add package.json package-lock.json
git commit -m "chore: add sortablejs for drag-reorder in Create page"
```

---

### Task 2: Schema migration for route_waypoints, route_options, route_legs

**Files:**
- Modify: `server/models/schema.sql` (append three `CREATE TABLE IF NOT EXISTS` blocks)
- Test: `tests/test_models_waypoints.py` (create — test the schema is applied by init)

- [ ] **Step 1: Write the failing schema-exists test**

Create `tests/test_models_waypoints.py`:

```python
"""Schema and model tests for route_waypoints, route_options, route_legs."""

from server.models import get_db


def _tables(db):
    rows = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return {r[0] for r in rows}


def test_m1_tables_exist(app):
    with app.app_context():
        db = get_db()
        tables = _tables(db)
        assert "route_waypoints" in tables
        assert "route_options" in tables
        assert "route_legs" in tables


def test_route_waypoints_columns(app):
    with app.app_context():
        db = get_db()
        cols = {r[1] for r in db.execute("PRAGMA table_info(route_waypoints)").fetchall()}
        expected = {
            "id", "route_id", "position", "kind", "name", "address",
            "lat", "lon", "included", "pin_role", "dwell_minutes", "description",
        }
        assert expected.issubset(cols), f"missing: {expected - cols}"


def test_route_options_columns(app):
    with app.app_context():
        db = get_db()
        cols = {r[1] for r in db.execute("PRAGMA table_info(route_options)").fetchall()}
        # M1 includes all columns even though costing UI is M3 — additive-only schema.
        expected = {
            "route_id", "profile", "costing_preset", "costing_options",
            "round_trip", "max_gradient_warn", "last_optimised_at", "last_generated_at",
        }
        assert expected.issubset(cols), f"missing: {expected - cols}"


def test_route_legs_columns(app):
    with app.app_context():
        db = get_db()
        cols = {r[1] for r in db.execute("PRAGMA table_info(route_legs)").fetchall()}
        expected = {
            "route_id", "from_position", "to_position",
            "distance_m", "duration_s", "polyline",
            "max_grade_pct", "warnings",
        }
        assert expected.issubset(cols), f"missing: {expected - cols}"
```

- [ ] **Step 2: Run the tests, confirm they fail**

```bash
source .venv/bin/activate
pytest tests/test_models_waypoints.py -v
```

Expected: 4 failures (tables missing).

- [ ] **Step 3: Extend `server/models/schema.sql`**

Append at the end of the file:

```sql
CREATE TABLE IF NOT EXISTS route_waypoints (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id        INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
    position        INTEGER NOT NULL,
    kind            TEXT    NOT NULL CHECK(kind IN ('stop', 'waypoint')),
    name            TEXT    NOT NULL,
    address         TEXT,
    lat             REAL,
    lon             REAL,
    included        INTEGER NOT NULL DEFAULT 1 CHECK(included IN (0, 1)),
    pin_role        TEXT    CHECK(pin_role IN ('start', 'end') OR pin_role IS NULL),
    dwell_minutes   INTEGER NOT NULL DEFAULT 0,
    description     TEXT,
    UNIQUE(route_id, position)
);
CREATE INDEX IF NOT EXISTS idx_waypoints_route ON route_waypoints(route_id);

CREATE TABLE IF NOT EXISTS route_options (
    route_id          INTEGER PRIMARY KEY REFERENCES routes(id) ON DELETE CASCADE,
    profile           TEXT    NOT NULL DEFAULT 'bicycle' CHECK(profile IN ('bicycle','pedestrian','auto')),
    costing_preset    TEXT    NOT NULL DEFAULT 'hybrid' CHECK(costing_preset IN ('road','gravel-mtb','easy','hike','drive','custom','hybrid')),
    costing_options   TEXT,
    round_trip        INTEGER NOT NULL DEFAULT 0 CHECK(round_trip IN (0, 1)),
    max_gradient_warn REAL,
    last_optimised_at INTEGER,
    last_generated_at INTEGER
);

CREATE TABLE IF NOT EXISTS route_legs (
    route_id        INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
    from_position   INTEGER NOT NULL,
    to_position     INTEGER NOT NULL,
    distance_m      REAL    NOT NULL,
    duration_s      REAL    NOT NULL,
    polyline        TEXT    NOT NULL,
    max_grade_pct   REAL,
    warnings        TEXT,
    PRIMARY KEY (route_id, from_position, to_position)
);
```

- [ ] **Step 4: Run the tests, confirm they pass**

```bash
pytest tests/test_models_waypoints.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Regression check — confirm existing tests still pass**

```bash
pytest tests/ --ignore=tests/test_ui_library.py --ignore=tests/test_ui_analysis.py -q
```

Expected: all green (schema is additive so nothing should break).

- [ ] **Step 6: Commit**

```bash
git add server/models/schema.sql tests/test_models_waypoints.py
git commit -m "feat(schema): add route_waypoints, route_options, route_legs tables"
```

---

### Task 3: Waypoints model — CRUD helpers

**Files:**
- Create: `server/models/waypoints.py`
- Modify: `tests/test_models_waypoints.py`

- [ ] **Step 1: Write failing CRUD tests**

Append to `tests/test_models_waypoints.py`:

```python
from server.models import waypoints as wp_model
from server.models.categories import ensure_default_category
from server.models.routes import create_route


def _create_stub_route(app, title="Plan test"):
    """Insert a bare routes row to act as a parent FK."""
    user_id = "anonymous"
    cat = ensure_default_category(user_id)
    return create_route(
        user_id=user_id,
        category_id=cat["id"],
        filename=f"{title}.gpx",
        storage_name=f"stub-{title.replace(' ', '-')}.gpx",
        title=title,
    )


def test_append_waypoint_assigns_positions(app):
    with app.app_context():
        route = _create_stub_route(app)
        w1 = wp_model.append_waypoint(route["id"], name="A", lat=-27.4, lon=152.9, kind="stop")
        w2 = wp_model.append_waypoint(route["id"], name="B", lat=-27.5, lon=152.8, kind="waypoint")
        assert w1["position"] == 0
        assert w2["position"] == 1


def test_list_waypoints_ordered(app):
    with app.app_context():
        route = _create_stub_route(app)
        wp_model.append_waypoint(route["id"], name="B", lat=-27.5, lon=152.8, kind="waypoint")
        wp_model.append_waypoint(route["id"], name="A", lat=-27.4, lon=152.9, kind="stop")
        rows = wp_model.list_waypoints(route["id"])
        assert [r["name"] for r in rows] == ["B", "A"]
        assert [r["position"] for r in rows] == [0, 1]


def test_update_waypoint_fields(app):
    with app.app_context():
        route = _create_stub_route(app)
        w = wp_model.append_waypoint(route["id"], name="A", lat=0, lon=0, kind="waypoint")
        updated = wp_model.update_waypoint(
            w["id"], route["id"],
            name="A2", kind="stop", lat=-27.0, lon=152.0,
            dwell_minutes=10, included=1,
        )
        assert updated["name"] == "A2"
        assert updated["kind"] == "stop"
        assert updated["dwell_minutes"] == 10


def test_delete_waypoint_and_reindex(app):
    with app.app_context():
        route = _create_stub_route(app)
        w0 = wp_model.append_waypoint(route["id"], name="A", lat=0, lon=0, kind="stop")
        w1 = wp_model.append_waypoint(route["id"], name="B", lat=0, lon=0, kind="stop")
        w2 = wp_model.append_waypoint(route["id"], name="C", lat=0, lon=0, kind="stop")
        wp_model.delete_waypoint(w1["id"], route["id"])
        rows = wp_model.list_waypoints(route["id"])
        assert [r["name"] for r in rows] == ["A", "C"]
        assert [r["position"] for r in rows] == [0, 1]


def test_reorder_waypoints(app):
    with app.app_context():
        route = _create_stub_route(app)
        ids = [wp_model.append_waypoint(route["id"], name=n, lat=0, lon=0, kind="stop")["id"] for n in ["A", "B", "C"]]
        wp_model.reorder_waypoints(route["id"], [ids[2], ids[0], ids[1]])
        rows = wp_model.list_waypoints(route["id"])
        assert [r["name"] for r in rows] == ["C", "A", "B"]


def test_get_or_create_options_defaults(app):
    with app.app_context():
        route = _create_stub_route(app)
        opts = wp_model.get_or_create_options(route["id"])
        assert opts["profile"] == "bicycle"
        assert opts["costing_preset"] == "hybrid"
        assert opts["round_trip"] == 0


def test_update_options(app):
    with app.app_context():
        route = _create_stub_route(app)
        wp_model.get_or_create_options(route["id"])
        updated = wp_model.update_options(route["id"], round_trip=1, profile="pedestrian")
        assert updated["round_trip"] == 1
        assert updated["profile"] == "pedestrian"
```

- [ ] **Step 2: Run, confirm failures**

```bash
pytest tests/test_models_waypoints.py -v
```

Expected: the new 7 tests fail (ImportError for `waypoints`).

- [ ] **Step 3: Implement `server/models/waypoints.py`**

```python
"""CRUD helpers for route_waypoints, route_options, route_legs."""

from server.models import get_db


# ---------- route_waypoints ----------

def _row_to_dict(row):
    return dict(row) if row else None


def list_waypoints(route_id):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM route_waypoints WHERE route_id = ? ORDER BY position",
        (route_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_waypoint(waypoint_id, route_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM route_waypoints WHERE id = ? AND route_id = ?",
        (waypoint_id, route_id),
    ).fetchone()
    return _row_to_dict(row)


def append_waypoint(route_id, *, name, lat, lon, kind,
                    address=None, description=None,
                    included=1, pin_role=None, dwell_minutes=0):
    db = get_db()
    next_pos_row = db.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 AS p FROM route_waypoints WHERE route_id = ?",
        (route_id,),
    ).fetchone()
    position = next_pos_row["p"]
    cur = db.execute(
        """
        INSERT INTO route_waypoints (
            route_id, position, kind, name, address, lat, lon,
            included, pin_role, dwell_minutes, description
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (route_id, position, kind, name, address, lat, lon,
         included, pin_role, dwell_minutes, description),
    )
    db.commit()
    return get_waypoint(cur.lastrowid, route_id)


def update_waypoint(waypoint_id, route_id, **fields):
    """Update any subset of: name, address, kind, lat, lon, included,
    pin_role, dwell_minutes, description. Position is handled separately
    via reorder_waypoints."""
    allowed = {"name", "address", "kind", "lat", "lon",
               "included", "pin_role", "dwell_minutes", "description"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_waypoint(waypoint_id, route_id)
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [waypoint_id, route_id]
    db = get_db()
    db.execute(
        f"UPDATE route_waypoints SET {set_clause} WHERE id = ? AND route_id = ?",
        params,
    )
    db.commit()
    return get_waypoint(waypoint_id, route_id)


def delete_waypoint(waypoint_id, route_id):
    db = get_db()
    deleted = db.execute(
        "DELETE FROM route_waypoints WHERE id = ? AND route_id = ?",
        (waypoint_id, route_id),
    ).rowcount
    if not deleted:
        db.commit()
        return False
    # Re-pack positions 0..N-1
    rows = db.execute(
        "SELECT id FROM route_waypoints WHERE route_id = ? ORDER BY position",
        (route_id,),
    ).fetchall()
    for new_pos, row in enumerate(rows):
        db.execute(
            "UPDATE route_waypoints SET position = ? WHERE id = ?",
            (new_pos, row["id"]),
        )
    db.commit()
    return True


def reorder_waypoints(route_id, ordered_ids):
    """Replace the full position ordering. `ordered_ids` must contain
    every waypoint id in the route, in the desired order. Uses a
    two-phase update (stage negative, then final) to avoid tripping the
    UNIQUE(route_id, position) constraint."""
    db = get_db()
    existing = [r["id"] for r in db.execute(
        "SELECT id FROM route_waypoints WHERE route_id = ?", (route_id,),
    ).fetchall()]
    if set(existing) != set(ordered_ids):
        raise ValueError("ordered_ids must contain exactly the route's waypoint ids")
    # Phase 1: move all to negative positions
    for i, wid in enumerate(ordered_ids):
        db.execute(
            "UPDATE route_waypoints SET position = ? WHERE id = ? AND route_id = ?",
            (-(i + 1), wid, route_id),
        )
    # Phase 2: set final positions
    for i, wid in enumerate(ordered_ids):
        db.execute(
            "UPDATE route_waypoints SET position = ? WHERE id = ? AND route_id = ?",
            (i, wid, route_id),
        )
    db.commit()


# ---------- route_options ----------

def get_or_create_options(route_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM route_options WHERE route_id = ?", (route_id,),
    ).fetchone()
    if row is None:
        db.execute("INSERT INTO route_options (route_id) VALUES (?)", (route_id,))
        db.commit()
        row = db.execute(
            "SELECT * FROM route_options WHERE route_id = ?", (route_id,),
        ).fetchone()
    return dict(row)


def update_options(route_id, **fields):
    allowed = {"profile", "costing_preset", "costing_options",
               "round_trip", "max_gradient_warn",
               "last_optimised_at", "last_generated_at"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_or_create_options(route_id)
    # Ensure a row exists first.
    get_or_create_options(route_id)
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [route_id]
    db = get_db()
    db.execute(
        f"UPDATE route_options SET {set_clause} WHERE route_id = ?",
        params,
    )
    db.commit()
    return get_or_create_options(route_id)


# ---------- route_legs ----------

def replace_legs(route_id, legs):
    """Delete all existing legs for the route and insert the new set.
    `legs` is a list of dicts with keys:
      from_position, to_position, distance_m, duration_s, polyline,
      max_grade_pct (optional), warnings (optional — JSON string)."""
    db = get_db()
    db.execute("DELETE FROM route_legs WHERE route_id = ?", (route_id,))
    for leg in legs:
        db.execute(
            """
            INSERT INTO route_legs (
                route_id, from_position, to_position,
                distance_m, duration_s, polyline,
                max_grade_pct, warnings
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                route_id,
                leg["from_position"], leg["to_position"],
                leg["distance_m"], leg["duration_s"], leg["polyline"],
                leg.get("max_grade_pct"),
                leg.get("warnings"),
            ),
        )
    db.commit()


def list_legs(route_id):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM route_legs WHERE route_id = ? ORDER BY from_position",
        (route_id,),
    ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Run, confirm all pass**

```bash
pytest tests/test_models_waypoints.py -v
```

Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add server/models/waypoints.py tests/test_models_waypoints.py
git commit -m "feat(models): CRUD helpers for route_waypoints, route_options, route_legs"
```

---

### Task 4: api_waypoints blueprint — REST CRUD

**Files:**
- Create: `server/blueprints/api_waypoints.py`
- Create: `tests/test_api_waypoints.py`
- Modify: `server/blueprints/__init__.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_api_waypoints.py`:

```python
"""REST tests for /api/routes/<id>/waypoints."""

import pytest


def _make_route(client):
    # Upload a minimal GPX to get a route row, then edit its recipe.
    # We'll switch to JSON creation in Task 6; for now use the existing upload path.
    from tests.conftest import sample_gpx  # noqa — shared fixture path
    gpx_bytes = b'<?xml version="1.0"?><gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">' \
                b'<metadata><name>API WP Test</name></metadata>' \
                b'<trk><trkseg><trkpt lat="-27.4" lon="152.9"><ele>10</ele></trkpt>' \
                b'<trkpt lat="-27.41" lon="152.91"><ele>11</ele></trkpt></trkseg></trk></gpx>'
    r = client.post(
        "/api/routes",
        data={"title": "API WP Test", "file": (__import__("io").BytesIO(gpx_bytes), "s.gpx")},
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
```

- [ ] **Step 2: Run, confirm failures**

```bash
pytest tests/test_api_waypoints.py -v
```

Expected: all 7 tests fail with 404 (blueprint not registered yet).

- [ ] **Step 3: Implement the blueprint**

Create `server/blueprints/api_waypoints.py`:

```python
"""REST endpoints for a route's waypoint recipe."""

from flask import Blueprint, jsonify, request

from server.auth import get_current_user
from server.models.routes import get_route
from server.models import waypoints as wp_model

bp = Blueprint("api_waypoints", __name__, url_prefix="/api")

VALID_KINDS = {"stop", "waypoint"}


def _require_route(route_id):
    user_id = get_current_user()
    route = get_route(user_id, route_id)
    if route is None:
        return None, (jsonify({"error": "Not found"}), 404)
    return route, None


@bp.route("/routes/<int:route_id>/waypoints", methods=["GET"])
def list_waypoints(route_id):
    _, err = _require_route(route_id)
    if err:
        return err
    return jsonify(wp_model.list_waypoints(route_id)), 200


@bp.route("/routes/<int:route_id>/waypoints", methods=["POST"])
def append_waypoint(route_id):
    _, err = _require_route(route_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    kind = data.get("kind")
    if kind not in VALID_KINDS:
        return jsonify({"error": "kind must be 'stop' or 'waypoint'"}), 400
    try:
        wp = wp_model.append_waypoint(
            route_id,
            name=data.get("name") or "Waypoint",
            lat=data.get("lat"),
            lon=data.get("lon"),
            kind=kind,
            address=data.get("address"),
            description=data.get("description"),
            dwell_minutes=int(data.get("dwell_minutes") or 0),
            pin_role=data.get("pin_role"),
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(wp), 201


@bp.route("/routes/<int:route_id>/waypoints/<int:wpt_id>", methods=["PATCH"])
def patch_waypoint(route_id, wpt_id):
    _, err = _require_route(route_id)
    if err:
        return err
    existing = wp_model.get_waypoint(wpt_id, route_id)
    if existing is None:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json(silent=True) or {}
    if "kind" in data and data["kind"] not in VALID_KINDS:
        return jsonify({"error": "kind must be 'stop' or 'waypoint'"}), 400
    updated = wp_model.update_waypoint(wpt_id, route_id, **data)
    return jsonify(updated), 200


@bp.route("/routes/<int:route_id>/waypoints/<int:wpt_id>", methods=["DELETE"])
def delete_waypoint(route_id, wpt_id):
    _, err = _require_route(route_id)
    if err:
        return err
    existing = wp_model.get_waypoint(wpt_id, route_id)
    if existing is None:
        return jsonify({"error": "Not found"}), 404
    wp_model.delete_waypoint(wpt_id, route_id)
    return "", 204


@bp.route("/routes/<int:route_id>/waypoints", methods=["PUT"])
def reorder_waypoints(route_id):
    _, err = _require_route(route_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    order = data.get("order")
    if not isinstance(order, list) or not all(isinstance(i, int) for i in order):
        return jsonify({"error": "order must be a list of waypoint ids"}), 400
    try:
        wp_model.reorder_waypoints(route_id, order)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(wp_model.list_waypoints(route_id)), 200
```

- [ ] **Step 4: Register the blueprint**

Edit `server/blueprints/__init__.py` — add the new imports and registration lines:

```python
def register_blueprints(app):
    from server.blueprints.api_routes import bp as routes_bp
    from server.blueprints.api_gpx import bp as gpx_bp
    from server.blueprints.api_categories import bp as categories_bp
    from server.blueprints.api_tags import bp as tags_bp
    from server.blueprints.api_waypoints import bp as waypoints_bp
    from server.blueprints.proxy import bp as proxy_bp
    app.register_blueprint(routes_bp)
    app.register_blueprint(gpx_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(tags_bp)
    app.register_blueprint(waypoints_bp)
    app.register_blueprint(proxy_bp)

    from server.blueprints.pages import bp as pages_bp
    app.register_blueprint(pages_bp)
```

- [ ] **Step 5: Run, confirm all pass**

```bash
pytest tests/test_api_waypoints.py -v
```

Expected: 7 passed.

- [ ] **Step 6: Regression check**

```bash
pytest tests/ --ignore=tests/test_ui_library.py --ignore=tests/test_ui_analysis.py -q
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add server/blueprints/api_waypoints.py server/blueprints/__init__.py tests/test_api_waypoints.py
git commit -m "feat(api): waypoint CRUD blueprint at /api/routes/<id>/waypoints"
```

---

### Task 5: Recipe-only route creation via JSON POST /api/routes

**Files:**
- Modify: `server/blueprints/api_routes.py`
- Modify: `tests/test_api_routes.py`

The existing `POST /api/routes` requires a file. We need a second creation path: JSON body only, creates an empty recipe route (no file on disk yet).

- [ ] **Step 1: Write failing test**

Append to `tests/test_api_routes.py`:

```python
def test_create_recipe_only_route(client):
    r = client.post(
        "/api/routes",
        json={"title": "Recipe only", "profile": "bicycle"},
        content_type="application/json",
    )
    assert r.status_code == 201, r.data
    body = r.get_json()
    assert body["title"] == "Recipe only"
    # No file yet — but storage_name must be populated (for future generate).
    assert body["storage_name"]
    # A corresponding route_options row should exist with default profile.
    rid = body["id"]
    opts = client.get(f"/api/routes/{rid}").get_json()
    assert "id" in opts
```

- [ ] **Step 2: Run, confirm it fails**

```bash
pytest tests/test_api_routes.py::test_create_recipe_only_route -v
```

Expected: fails — the existing route only handles multipart form.

- [ ] **Step 3: Modify `server/blueprints/api_routes.py`**

At the top of `upload_route()`, branch on content type. Replace the current function body:

```python
@bp.route("/routes", methods=["POST"])
def upload_route():
    user_id = get_current_user()

    # --- JSON recipe-only creation (M1) ---
    if request.is_json:
        return _create_recipe_only(user_id, request.get_json() or {})

    # --- Existing multipart upload path (unchanged below) ---
    file = request.files.get("file")
    if file is None:
        return jsonify({"error": "No file provided"}), 400
    raw = file.read()

    try:
        stats = parse_gpx(raw)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    title = (request.form.get("title") or "").strip()
    if not title:
        title = (stats.get("name") or "").strip()
    if not title:
        return jsonify({"error": "title is required when GPX has no <name>"}), 400

    category_id_param = request.form.get("category_id")
    if category_id_param:
        category = get_category(user_id, int(category_id_param))
        if category is None:
            return jsonify({"error": "Category not found"}), 404
    else:
        category = ensure_default_category(user_id)

    category_slug = category["slug"]
    data_dir = current_app.config["DATA_DIR"]
    store_dir = os.path.join(data_dir, "gpx", user_id, category_slug)
    os.makedirs(store_dir, exist_ok=True)

    storage_name = f"{uuid.uuid4().hex}.gpx"
    file_path = os.path.join(store_dir, storage_name)
    with open(file_path, "wb") as f:
        f.write(raw)

    original_filename = file.filename or "upload.gpx"
    route = create_route(
        user_id=user_id,
        category_id=category["id"],
        filename=original_filename,
        storage_name=storage_name,
        title=title,
        distance_km=stats.get("distance_km"),
        min_elevation=stats.get("min_elevation"),
        max_elevation=stats.get("max_elevation"),
        max_gradient_asc=stats.get("max_gradient_asc"),
        max_gradient_desc=stats.get("max_gradient_desc"),
        point_count=stats.get("point_count"),
    )
    return jsonify(route), 201


def _create_recipe_only(user_id, data):
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    profile = data.get("profile") or "bicycle"
    if profile not in ("bicycle", "pedestrian", "auto"):
        return jsonify({"error": f"invalid profile: {profile}"}), 400

    category_id_param = data.get("category_id")
    if category_id_param:
        category = get_category(user_id, int(category_id_param))
        if category is None:
            return jsonify({"error": "Category not found"}), 404
    else:
        category = ensure_default_category(user_id)

    storage_name = f"{uuid.uuid4().hex}.gpx"
    filename = f"{title}.gpx"

    route = create_route(
        user_id=user_id,
        category_id=category["id"],
        filename=filename,
        storage_name=storage_name,
        title=title,
    )
    # Seed route_options with the requested profile.
    from server.models import waypoints as wp_model
    wp_model.update_options(route["id"], profile=profile)
    return jsonify(route), 201
```

- [ ] **Step 4: Run, confirm the new test passes and old ones still pass**

```bash
pytest tests/test_api_routes.py -v
```

Expected: all green including the new test.

- [ ] **Step 5: Commit**

```bash
git add server/blueprints/api_routes.py tests/test_api_routes.py
git commit -m "feat(api): POST /api/routes accepts JSON for recipe-only creation"
```

---

### Task 6: Valhalla client module

**Files:**
- Create: `server/routing/__init__.py`
- Create: `server/routing/valhalla_client.py`
- Create: `tests/fixtures/valhalla_response_sample.json`
- Create: `tests/test_routing_valhalla_client.py`

- [ ] **Step 1: Create the package init**

```bash
mkdir -p server/routing
```

Create `server/routing/__init__.py` as an empty file:

```python
"""Routing utilities — Valhalla client, GPX writer, optimiser (M3)."""
```

- [ ] **Step 2: Create a realistic Valhalla response fixture**

Create `tests/fixtures/valhalla_response_sample.json`:

```json
{
  "trip": {
    "legs": [
      {
        "summary": {
          "length": 2.0,
          "time": 360.0
        },
        "shape": "kpfxFvc|iZ@?@??A??@?@??A??@?@??A?"
      },
      {
        "summary": {
          "length": 1.5,
          "time": 300.0
        },
        "shape": "gmfxFbc|iZ@?@??A??@?@??A?"
      }
    ],
    "summary": {
      "length": 3.5,
      "time": 660.0
    }
  }
}
```

(Note: the shapes here are short-encoded placeholders; tests only need length ≥ 1 when decoded. Polyline decoding is tested separately via a known-good string.)

- [ ] **Step 3: Write failing client tests**

Create `tests/test_routing_valhalla_client.py`:

```python
"""Tests for server.routing.valhalla_client."""

import json
import os
from unittest.mock import patch, MagicMock

import pytest

from server.routing import valhalla_client as vc

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _mock_requests_post(response_json, status_code=200):
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = response_json
    m.raise_for_status = lambda: None
    if status_code >= 400:
        def _raise():
            from requests import HTTPError
            raise HTTPError(f"HTTP {status_code}")
        m.raise_for_status = _raise
    return m


def test_request_body_shape():
    """The client must compose a Valhalla /route body with locations,
    costing, costing_options, and elevation_interval."""
    body = vc.build_request_body(
        waypoints=[(-27.4, 152.9), (-27.5, 152.8)],
        profile="bicycle",
        costing_options={"use_hills": 0.5},
    )
    assert body["costing"] == "bicycle"
    assert body["costing_options"]["bicycle"]["use_hills"] == 0.5
    assert body["locations"] == [
        {"lat": -27.4, "lon": 152.9, "type": "break"},
        {"lat": -27.5, "lon": 152.8, "type": "break"},
    ]
    # M1: always ask for elevation samples; post-processing runs in M3.
    assert body["elevation_interval"] == 10


def test_call_success(app):
    with open(os.path.join(FIXTURES, "valhalla_response_sample.json")) as f:
        fake = json.load(f)
    with app.app_context(), patch("server.routing.valhalla_client.requests.post",
                                  return_value=_mock_requests_post(fake)):
        resp = vc.call_route(
            waypoints=[(-27.4, 152.9), (-27.5, 152.8), (-27.6, 152.7)],
            profile="bicycle",
        )
    assert resp["trip"]["legs"][0]["summary"]["length"] == 2.0
    assert len(resp["trip"]["legs"]) == 2


def test_call_http_error(app):
    with app.app_context(), patch("server.routing.valhalla_client.requests.post",
                                  return_value=_mock_requests_post({"error": "nope"}, 400)):
        with pytest.raises(vc.ValhallaError):
            vc.call_route(
                waypoints=[(0.0, 0.0), (0.0, 0.0)],
                profile="bicycle",
            )


def test_call_fewer_than_two_waypoints_rejected(app):
    with app.app_context():
        with pytest.raises(ValueError):
            vc.call_route(waypoints=[(0.0, 0.0)], profile="bicycle")


def test_parse_legs_decodes_shape():
    """A response with two legs must produce two leg dicts with
    polyline set to the original shape string."""
    with open(os.path.join(FIXTURES, "valhalla_response_sample.json")) as f:
        fake = json.load(f)
    legs = vc.parse_legs(fake)
    assert len(legs) == 2
    assert legs[0]["distance_m"] == 2000.0  # km → m
    assert legs[0]["duration_s"] == 360.0
    assert legs[0]["polyline"] == fake["trip"]["legs"][0]["shape"]
```

- [ ] **Step 4: Run, confirm failures**

```bash
pytest tests/test_routing_valhalla_client.py -v
```

Expected: all fail (module missing).

- [ ] **Step 5: Implement the client**

Create `server/routing/valhalla_client.py`:

```python
"""Thin Valhalla /route HTTP client."""

import requests
from flask import current_app


class ValhallaError(Exception):
    """Raised when Valhalla returns a non-2xx or malformed response."""


def build_request_body(waypoints, profile, costing_options=None, round_trip=False):
    """Compose the Valhalla /route request body.

    waypoints: list of (lat, lon) tuples. Minimum 2.
    profile: 'bicycle' | 'pedestrian' | 'auto'.
    costing_options: dict merged into costing_options[profile]. M1 passes {}.
    round_trip: if True, append first waypoint at the end to close the loop.
    """
    locs = [{"lat": lat, "lon": lon, "type": "break"} for lat, lon in waypoints]
    if round_trip and waypoints:
        lat, lon = waypoints[0]
        locs.append({"lat": lat, "lon": lon, "type": "break"})

    body = {
        "locations": locs,
        "costing": profile,
        "costing_options": {profile: dict(costing_options or {})},
        "elevation_interval": 10,
    }
    return body


def call_route(waypoints, profile, costing_options=None, round_trip=False, timeout=30):
    """Call Valhalla /route and return the parsed JSON response."""
    if len(waypoints) < 2:
        raise ValueError("at least 2 waypoints required")
    body = build_request_body(waypoints, profile, costing_options, round_trip)
    url = current_app.config["VALHALLA_URL"].rstrip("/") + "/route"
    try:
        r = requests.post(url, json=body, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException as e:
        raise ValhallaError(str(e)) from e
    return r.json()


def parse_legs(response):
    """Convert a Valhalla response into a list of leg dicts ready for
    route_legs insertion. The caller assigns from_position/to_position."""
    trip = response.get("trip") or {}
    legs = trip.get("legs") or []
    out = []
    for leg in legs:
        summary = leg.get("summary") or {}
        length_km = summary.get("length", 0.0)
        time_s = summary.get("time", 0.0)
        shape = leg.get("shape") or ""
        out.append({
            "distance_m": float(length_km) * 1000.0,
            "duration_s": float(time_s),
            "polyline": shape,
        })
    return out
```

- [ ] **Step 6: Run, confirm all pass**

```bash
pytest tests/test_routing_valhalla_client.py -v
```

Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
git add server/routing/__init__.py server/routing/valhalla_client.py tests/test_routing_valhalla_client.py tests/fixtures/valhalla_response_sample.json
git commit -m "feat(routing): Valhalla /route client with request builder and leg parser"
```

---

### Task 7: GPX writer (M1 — track only)

**Files:**
- Create: `server/routing/gpx_writer.py`
- Create: `tests/test_routing_gpx_writer.py`

Valhalla leg shapes are Google-polyline encoded with a **precision 6** default (0.000001°). The server needs to decode them to `(lat, lon)` tuples and write a GPX trk with those points. Elevation will arrive in M3 when we switch to `elevation_interval` samples; M1 writes trkpts without `<ele>`.

- [ ] **Step 1: Write failing tests**

Create `tests/test_routing_gpx_writer.py`:

```python
"""Tests for server.routing.gpx_writer."""

from server.routing.gpx_writer import decode_polyline, write_track_gpx


def test_decode_polyline_simple():
    # Known-good encoding at precision 6: single point (45.0, -122.0)
    # Encoded via Google's algorithm for precision 6.
    enc = "_p~iF~ps|U"  # This is precision 5; we test our precision.
    # We'll use a round-trip: encode, then decode, and check we recover.
    from server.routing.gpx_writer import encode_polyline
    points = [(45.0, -122.0), (45.01, -122.01)]
    encoded = encode_polyline(points, precision=6)
    decoded = decode_polyline(encoded, precision=6)
    assert len(decoded) == 2
    assert abs(decoded[0][0] - 45.0) < 1e-5
    assert abs(decoded[0][1] - (-122.0)) < 1e-5


def test_write_track_gpx_produces_valid_xml(tmp_path):
    from server.routing.gpx_writer import encode_polyline
    legs = [
        {"polyline": encode_polyline([(-27.4, 152.9), (-27.41, 152.91)], precision=6)},
        {"polyline": encode_polyline([(-27.41, 152.91), (-27.42, 152.92)], precision=6)},
    ]
    path = tmp_path / "out.gpx"
    write_track_gpx(str(path), title="Test Route", legs=legs, precision=6)
    content = path.read_text()
    assert content.startswith('<?xml')
    assert '<trk>' in content
    assert '<name>Test Route</name>' in content
    # Two legs concatenated → three distinct trkpts (leg boundary deduped).
    assert content.count('<trkpt') == 3
```

- [ ] **Step 2: Run, confirm fail**

```bash
pytest tests/test_routing_gpx_writer.py -v
```

Expected: fail — module missing.

- [ ] **Step 3: Implement the writer**

Create `server/routing/gpx_writer.py`:

```python
"""GPX 1.1 writer. M1 writes <trk> only. M4 extends with <wpt> entries."""

import xml.etree.ElementTree as ET
from xml.dom import minidom


def decode_polyline(encoded, precision=6):
    """Decode a Google Encoded Polyline string into a list of (lat, lon)."""
    factor = 10 ** precision
    coords = []
    lat = lng = 0
    i = 0
    while i < len(encoded):
        for _ in range(2):
            result = 0
            shift = 0
            while True:
                b = ord(encoded[i]) - 63
                i += 1
                result |= (b & 0x1f) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else (result >> 1)
            if _ == 0:
                lat += delta
            else:
                lng += delta
        coords.append((lat / factor, lng / factor))
    return coords


def encode_polyline(points, precision=6):
    """Encode a list of (lat, lon) tuples into a Google Encoded Polyline."""
    factor = 10 ** precision
    result = []
    last_lat = last_lng = 0
    for lat, lng in points:
        lat_i = int(round(lat * factor))
        lng_i = int(round(lng * factor))
        dlat = lat_i - last_lat
        dlng = lng_i - last_lng
        last_lat, last_lng = lat_i, lng_i
        for v in (dlat, dlng):
            v = ~(v << 1) if v < 0 else (v << 1)
            while v >= 0x20:
                result.append(chr((0x20 | (v & 0x1f)) + 63))
                v >>= 5
            result.append(chr(v + 63))
    return "".join(result)


def write_track_gpx(path, *, title, legs, precision=6):
    """Write a track-only GPX file.

    legs: list of dicts, each with a 'polyline' key (encoded polyline).
          Consecutive legs are concatenated and the duplicate boundary
          point is dropped.
    """
    all_points = []
    for i, leg in enumerate(legs):
        decoded = decode_polyline(leg["polyline"], precision=precision)
        if i > 0 and decoded and all_points and all_points[-1] == decoded[0]:
            decoded = decoded[1:]
        all_points.extend(decoded)

    ns = "http://www.topografix.com/GPX/1/1"
    ET.register_namespace("", ns)
    gpx = ET.Element("gpx", {
        "version": "1.1",
        "creator": "GPX Route Exploration",
        "xmlns": ns,
    })
    meta = ET.SubElement(gpx, "metadata")
    ET.SubElement(meta, "name").text = title

    trk = ET.SubElement(gpx, "trk")
    ET.SubElement(trk, "name").text = title
    trkseg = ET.SubElement(trk, "trkseg")
    for lat, lon in all_points:
        ET.SubElement(trkseg, "trkpt", {"lat": f"{lat:.7f}", "lon": f"{lon:.7f}"})

    xml_bytes = ET.tostring(gpx, encoding="utf-8", xml_declaration=True)
    pretty = minidom.parseString(xml_bytes).toprettyxml(indent="  ", encoding="utf-8")
    with open(path, "wb") as f:
        f.write(pretty)
```

- [ ] **Step 4: Run, confirm pass**

```bash
pytest tests/test_routing_gpx_writer.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add server/routing/gpx_writer.py tests/test_routing_gpx_writer.py
git commit -m "feat(routing): GPX writer + polyline codec (track only, M1 scope)"
```

---

### Task 8: api_routing blueprint — POST /api/routes/<id>/generate

**Files:**
- Create: `server/blueprints/api_routing.py`
- Create: `tests/test_api_routing.py`
- Modify: `server/blueprints/__init__.py`

- [ ] **Step 1: Write failing generate test**

Create `tests/test_api_routing.py`:

```python
"""Tests for POST /api/routes/<id>/generate."""

import json
import os
from unittest.mock import patch

from server.routing.gpx_writer import encode_polyline

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _fake_valhalla_response():
    """Build a fake response with two legs whose decoded points are known."""
    leg1 = encode_polyline([(-27.40, 152.90), (-27.405, 152.905), (-27.41, 152.91)], precision=6)
    leg2 = encode_polyline([(-27.41, 152.91), (-27.42, 152.92)], precision=6)
    return {
        "trip": {
            "legs": [
                {"summary": {"length": 1.0, "time": 300.0}, "shape": leg1},
                {"summary": {"length": 0.8, "time": 240.0}, "shape": leg2},
            ],
            "summary": {"length": 1.8, "time": 540.0},
        }
    }


def _create_route_with_three_waypoints(client):
    r = client.post(
        "/api/routes",
        json={"title": "Gen test", "profile": "bicycle"},
        content_type="application/json",
    )
    rid = r.get_json()["id"]
    for name, lat, lon in [("A", -27.40, 152.90), ("B", -27.41, 152.91), ("C", -27.42, 152.92)]:
        client.post(
            f"/api/routes/{rid}/waypoints",
            json={"name": name, "lat": lat, "lon": lon, "kind": "stop"},
        )
    return rid


def test_generate_rejects_when_fewer_than_two_waypoints(client):
    r = client.post(
        "/api/routes",
        json={"title": "No WP"},
        content_type="application/json",
    )
    rid = r.get_json()["id"]
    resp = client.post(f"/api/routes/{rid}/generate")
    assert resp.status_code == 400


def test_generate_writes_legs_and_gpx_file(client, app):
    rid = _create_route_with_three_waypoints(client)
    fake = _fake_valhalla_response()
    with patch("server.routing.valhalla_client.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = fake
        mock_post.return_value.raise_for_status = lambda: None
        resp = client.post(f"/api/routes/{rid}/generate")
    assert resp.status_code == 200, resp.data
    body = resp.get_json()
    assert body["legs_count"] == 2
    assert body["distance_km"] == 1.8
    assert "gpx_url" in body

    # DB: route_legs populated
    r = client.get(f"/api/routes/{rid}/legs")
    assert r.status_code == 200
    legs = r.get_json()
    assert len(legs) == 2
    assert legs[0]["from_position"] == 0 and legs[0]["to_position"] == 1
    assert legs[1]["from_position"] == 1 and legs[1]["to_position"] == 2

    # File: written under DATA_DIR/gpx/<user>/<cat>/<storage_name>
    data_dir = app.config["DATA_DIR"]
    stored = None
    for root, _, files in os.walk(os.path.join(data_dir, "gpx")):
        for f in files:
            if f.endswith(".gpx") and os.path.getsize(os.path.join(root, f)) > 0:
                stored = os.path.join(root, f)
    assert stored, "GPX file was not written"
    content = open(stored).read()
    assert "<trk>" in content and "<trkpt" in content


def test_generate_valhalla_error_returns_502(client):
    rid = _create_route_with_three_waypoints(client)
    with patch("server.routing.valhalla_client.requests.post") as mock_post:
        import requests
        mock_post.return_value.raise_for_status.side_effect = requests.HTTPError("upstream fail")
        mock_post.return_value.status_code = 500
        resp = client.post(f"/api/routes/{rid}/generate")
    assert resp.status_code == 502
```

- [ ] **Step 2: Run, confirm all three fail**

```bash
pytest tests/test_api_routing.py -v
```

Expected: all fail (blueprint not registered).

- [ ] **Step 3: Implement the blueprint**

Create `server/blueprints/api_routing.py`:

```python
"""Route generation endpoints — calls Valhalla and writes the detailed GPX."""

import os
import time

from flask import Blueprint, current_app, jsonify, request

from server.auth import get_current_user
from server.models import waypoints as wp_model
from server.models.routes import get_route
from server.models.categories import get_category
from server.routing import valhalla_client as vc
from server.routing.gpx_writer import write_track_gpx

bp = Blueprint("api_routing", __name__, url_prefix="/api")


def _resolve_gpx_path(app, user_id, route):
    """Find or create the on-disk path for the route's GPX file."""
    category = get_category(user_id, route["category_id"])
    data_dir = app.config["DATA_DIR"]
    store_dir = os.path.join(data_dir, "gpx", user_id, category["slug"])
    os.makedirs(store_dir, exist_ok=True)
    return os.path.join(store_dir, route["storage_name"])


@bp.route("/routes/<int:route_id>/generate", methods=["POST"])
def generate_route(route_id):
    user_id = get_current_user()
    route = get_route(user_id, route_id)
    if route is None:
        return jsonify({"error": "Not found"}), 404

    wps = [w for w in wp_model.list_waypoints(route_id) if w.get("included", 1)]
    if len(wps) < 2:
        return jsonify({"error": "at least 2 included waypoints required"}), 400
    missing = [w["id"] for w in wps if w.get("lat") is None or w.get("lon") is None]
    if missing:
        return jsonify({"error": f"waypoints without coordinates: {missing}"}), 400

    opts = wp_model.get_or_create_options(route_id)
    profile = opts["profile"]

    try:
        response = vc.call_route(
            waypoints=[(w["lat"], w["lon"]) for w in wps],
            profile=profile,
            costing_options={},  # M3 wires the full costing options
            round_trip=bool(opts.get("round_trip")),
        )
    except vc.ValhallaError as e:
        return jsonify({"error": f"Valhalla upstream error: {e}"}), 502

    parsed_legs = vc.parse_legs(response)
    if len(parsed_legs) != len(wps) - 1 and not opts.get("round_trip"):
        return jsonify({"error": f"Valhalla returned {len(parsed_legs)} legs, expected {len(wps)-1}"}), 502

    # Persist legs
    legs_rows = []
    for i, leg in enumerate(parsed_legs):
        legs_rows.append({
            "from_position": wps[i]["position"],
            "to_position": wps[(i + 1) % len(wps)]["position"],
            "distance_m": leg["distance_m"],
            "duration_s": leg["duration_s"],
            "polyline": leg["polyline"],
        })
    wp_model.replace_legs(route_id, legs_rows)
    wp_model.update_options(route_id, last_generated_at=int(time.time()))

    # Write GPX
    gpx_path = _resolve_gpx_path(current_app, user_id, route)
    write_track_gpx(gpx_path, title=route["title"], legs=parsed_legs)

    summary = (response.get("trip") or {}).get("summary") or {}
    distance_km = float(summary.get("length") or 0.0)
    duration_s = float(summary.get("time") or 0.0)

    return jsonify({
        "route_id": route_id,
        "legs_count": len(parsed_legs),
        "distance_km": distance_km,
        "duration_s": duration_s,
        "gpx_url": f"/api/gpx/{route_id}",
    }), 200


@bp.route("/routes/<int:route_id>/legs", methods=["GET"])
def list_legs(route_id):
    user_id = get_current_user()
    route = get_route(user_id, route_id)
    if route is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(wp_model.list_legs(route_id)), 200
```

- [ ] **Step 4: Register the new blueprint**

Edit `server/blueprints/__init__.py` to add the routing blueprint:

```python
def register_blueprints(app):
    from server.blueprints.api_routes import bp as routes_bp
    from server.blueprints.api_gpx import bp as gpx_bp
    from server.blueprints.api_categories import bp as categories_bp
    from server.blueprints.api_tags import bp as tags_bp
    from server.blueprints.api_waypoints import bp as waypoints_bp
    from server.blueprints.api_routing import bp as routing_bp
    from server.blueprints.proxy import bp as proxy_bp
    app.register_blueprint(routes_bp)
    app.register_blueprint(gpx_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(tags_bp)
    app.register_blueprint(waypoints_bp)
    app.register_blueprint(routing_bp)
    app.register_blueprint(proxy_bp)

    from server.blueprints.pages import bp as pages_bp
    app.register_blueprint(pages_bp)
```

- [ ] **Step 5: Run the new tests and full regression**

```bash
pytest tests/test_api_routing.py -v
pytest tests/ --ignore=tests/test_ui_library.py --ignore=tests/test_ui_analysis.py --ignore=tests/test_ui_create.py -q
```

Expected: routing tests pass; full regression green.

- [ ] **Step 6: Commit**

```bash
git add server/blueprints/api_routing.py server/blueprints/__init__.py tests/test_api_routing.py
git commit -m "feat(api): POST /api/routes/<id>/generate calls Valhalla, writes GPX, persists legs"
```

---

### Task 9: Shared waypoint-markers module (Leaflet divIcons)

**Files:**
- Create: `src/js/shared/waypoint-markers.js`

No JS unit test runner is configured in this project — shared JS is validated end-to-end by Playwright. This module is pure functions + Leaflet factories, validated by the M1 Playwright test in Task 18.

- [ ] **Step 1: Create the module**

Create `src/js/shared/waypoint-markers.js`:

```javascript
// --- Leaflet marker factories for stops and waypoints ---
//
// Icons are HTML divIcons so we can style with CSS. Per spec the stop
// is an octagon (red) and the waypoint is a diamond (cyan). The number
// shown inside is the 1-based visit order.

function stopIconHtml(n, { isStart = false, isEnd = false } = {}) {
  const cls = `wpe-marker wpe-stop${isStart ? ' wpe-start' : ''}${isEnd ? ' wpe-end' : ''}`;
  return `<div class="${cls}">${n}</div>`;
}

function waypointIconHtml(n) {
  return `<div class="wpe-marker wpe-waypoint"><span>${n}</span></div>`;
}

export function makeStopMarker(lat, lon, n, opts = {}) {
  const icon = L.divIcon({
    className: '',
    html: stopIconHtml(n, opts),
    iconSize: [30, 30],
    iconAnchor: [15, 15],
  });
  return L.marker([lat, lon], { icon, draggable: !!opts.draggable });
}

export function makeWaypointMarker(lat, lon, n, opts = {}) {
  const icon = L.divIcon({
    className: '',
    html: waypointIconHtml(n),
    iconSize: [20, 20],
    iconAnchor: [10, 10],
  });
  return L.marker([lat, lon], { icon, draggable: !!opts.draggable });
}

/**
 * Build or replace markers for a route's waypoints.
 * @param {L.Map} map
 * @param {Array} waypoints — each { id, kind, lat, lon, pin_role }
 * @param {L.Marker[]} existingLayers — replaced in place
 * @param {Function} onClick — optional click handler: (waypoint) => void
 * @param {Function} onContextMenu — optional right-click handler: (waypoint) => void
 * @param {Function} onDragEnd — optional drag-end handler: (waypoint, {lat,lon}) => void
 * @returns updated layer array
 */
export function renderMarkers(map, waypoints, existingLayers,
                              { onClick, onContextMenu, onDragEnd, draggable = false } = {}) {
  existingLayers.forEach(m => map.removeLayer(m));
  const layers = [];
  waypoints.forEach((w, i) => {
    if (w.lat == null || w.lon == null) return;
    const n = i + 1;
    const make = w.kind === 'stop' ? makeStopMarker : makeWaypointMarker;
    const marker = make(w.lat, w.lon, n, {
      isStart: w.pin_role === 'start',
      isEnd: w.pin_role === 'end',
      draggable,
    });
    marker.addTo(map);
    marker._waypointId = w.id;
    if (onClick) marker.on('click', () => onClick(w));
    if (onContextMenu) {
      marker.on('contextmenu', (e) => {
        // Stop the default browser menu from popping up over Leaflet.
        if (e.originalEvent) e.originalEvent.preventDefault();
        onContextMenu(w);
      });
    }
    if (onDragEnd) marker.on('dragend', (e) => {
      const { lat, lng } = e.target.getLatLng();
      onDragEnd(w, { lat, lon: lng });
    });
    layers.push(marker);
  });
  return layers;
}
```

- [ ] **Step 2: Commit**

```bash
git add src/js/shared/waypoint-markers.js
git commit -m "feat(frontend): shared Leaflet marker factories for stops and waypoints"
```

---

### Task 10: Shared route-api client module

**Files:**
- Create: `src/js/shared/route-api.js`

- [ ] **Step 1: Create the module**

```javascript
// --- Thin client for /api/routes/... endpoints ---

async function json(method, url, body) {
  const resp = await fetch(url, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`${method} ${url} → ${resp.status}: ${text}`);
  }
  if (resp.status === 204) return null;
  return resp.json();
}

export function createRouteRecipe({ title, profile = 'bicycle', categoryId = null }) {
  const body = { title, profile };
  if (categoryId) body.category_id = categoryId;
  return json('POST', '/api/routes', body);
}

export function getRoute(routeId) {
  return json('GET', `/api/routes/${routeId}`);
}

export function listWaypoints(routeId) {
  return json('GET', `/api/routes/${routeId}/waypoints`);
}

export function appendWaypoint(routeId, { name, lat, lon, kind, address, description }) {
  return json('POST', `/api/routes/${routeId}/waypoints`,
              { name, lat, lon, kind, address, description });
}

export function patchWaypoint(routeId, wptId, patch) {
  return json('PATCH', `/api/routes/${routeId}/waypoints/${wptId}`, patch);
}

export function deleteWaypoint(routeId, wptId) {
  return json('DELETE', `/api/routes/${routeId}/waypoints/${wptId}`);
}

export function reorderWaypoints(routeId, orderedIds) {
  return json('PUT', `/api/routes/${routeId}/waypoints`, { order: orderedIds });
}

export function generateRoute(routeId) {
  return json('POST', `/api/routes/${routeId}/generate`);
}
```

- [ ] **Step 2: Commit**

```bash
git add src/js/shared/route-api.js
git commit -m "feat(frontend): shared route-api client for waypoint CRUD and generate"
```

---

### Task 11: Shared waypoint-editor sidebar widget

**Files:**
- Create: `src/js/shared/waypoint-editor.js`

This is the biggest frontend module. It renders the sidebar list, tabs, collapse, and wires drag-reorder via SortableJS.

- [ ] **Step 1: Create the module**

```javascript
// --- Shared sidebar editor: list, tabs, drag-reorder, collapse ---
//
// Consumed by src/js/create/app.js (M1) and src/js/analysis/edit-panel.js (M2).
// Emits callbacks for reorder / update / remove — owning page decides how to
// persist (call API directly in create, or buffer as an in-memory working copy
// in the edit panel).

import Sortable from 'sortablejs';

const TAB_ALL = 'all';
const TAB_STOPS = 'stops';
const TAB_WAYPOINTS = 'waypoints';

/**
 * Mount the editor into the given container element.
 * @param {HTMLElement} container
 * @param {Object} handlers  { onReorder(orderedIds), onUpdate(wptId, patch),
 *                             onRemove(wptId), onCollapseToggle(isCollapsed) }
 * @returns an API: { setWaypoints(list), setTotals({distance, time}),
 *                     getState(): {collapsed, tab} }
 */
export function mountWaypointEditor(container, handlers = {}) {
  container.innerHTML = `
    <div class="wpe">
      <div class="wpe-head">
        <strong>Route stops &amp; waypoints</strong>
        <button class="wpe-collapse" title="Collapse panel" type="button">▶</button>
      </div>
      <div class="wpe-tabs">
        <div class="wpe-tab active" data-tab="${TAB_ALL}">All<span class="wpe-count" data-count="all">(0)</span></div>
        <div class="wpe-tab" data-tab="${TAB_STOPS}">🛑 Stops<span class="wpe-count" data-count="stops">(0)</span></div>
        <div class="wpe-tab" data-tab="${TAB_WAYPOINTS}">◆ Waypoints<span class="wpe-count" data-count="waypoints">(0)</span></div>
      </div>
      <div class="wpe-totals">
        <span>Distance: <strong data-totals-distance>—</strong></span>
        <span>Drive: <strong data-totals-time>—</strong></span>
      </div>
      <ul class="wpe-list"></ul>
      <div class="wpe-empty">Click the map to add your first waypoint.</div>
    </div>
  `;

  const listEl = container.querySelector('.wpe-list');
  const emptyEl = container.querySelector('.wpe-empty');
  const collapseBtn = container.querySelector('.wpe-collapse');
  const totalsDist = container.querySelector('[data-totals-distance]');
  const totalsTime = container.querySelector('[data-totals-time]');
  const counts = {
    [TAB_ALL]:        container.querySelector('[data-count="all"]'),
    [TAB_STOPS]:      container.querySelector('[data-count="stops"]'),
    [TAB_WAYPOINTS]:  container.querySelector('[data-count="waypoints"]'),
  };

  let state = {
    waypoints: [],
    tab: TAB_ALL,
    collapsed: false,
  };

  // --- Tab switching ---
  container.querySelectorAll('.wpe-tab').forEach(tabEl => {
    tabEl.addEventListener('click', () => {
      state.tab = tabEl.dataset.tab;
      container.querySelectorAll('.wpe-tab').forEach(t => t.classList.toggle('active', t === tabEl));
      render();
    });
  });

  // --- Collapse toggle ---
  collapseBtn.addEventListener('click', () => {
    state.collapsed = !state.collapsed;
    container.classList.toggle('wpe-collapsed', state.collapsed);
    collapseBtn.textContent = state.collapsed ? '◀' : '▶';
    if (handlers.onCollapseToggle) handlers.onCollapseToggle(state.collapsed);
  });

  // --- Sortable (drag to reorder) ---
  Sortable.create(listEl, {
    handle: '.wpe-handle',
    animation: 150,
    onEnd: () => {
      const orderedIds = Array.from(listEl.querySelectorAll('[data-wpt-id]'))
        .map(el => Number(el.dataset.wptId));
      // Re-map from filtered order to full order if a tab is active.
      // Simpler: reorder only runs while TAB_ALL is active (disable on filter).
      if (state.tab === TAB_ALL && handlers.onReorder) {
        handlers.onReorder(orderedIds);
      } else {
        // Revert visually by re-rendering from state.
        render();
      }
    },
  });

  function render() {
    const filtered = state.waypoints.filter(w =>
      state.tab === TAB_ALL
      || (state.tab === TAB_STOPS && w.kind === 'stop')
      || (state.tab === TAB_WAYPOINTS && w.kind === 'waypoint')
    );
    emptyEl.style.display = state.waypoints.length ? 'none' : '';
    listEl.innerHTML = '';
    filtered.forEach((w, visibleIdx) => {
      const actualIdx = state.waypoints.indexOf(w);
      const visitN = actualIdx + 1;
      const li = document.createElement('li');
      li.className = `wpe-item wpe-item-${w.kind}`;
      li.dataset.wptId = w.id;
      li.innerHTML = `
        <span class="wpe-handle" title="Drag to reorder">⋮⋮</span>
        <span class="wpe-icon wpe-icon-${w.kind}">${w.kind === 'stop' ? visitN : `<span>${visitN}</span>`}</span>
        <div class="wpe-body">
          <div class="wpe-name">${escape(w.name)}${w.pin_role ? ` <span class="wpe-badge">${w.pin_role === 'start' ? 'Start' : 'End'}</span>` : ''}</div>
          <div class="wpe-sub">${escape(w.address || (w.lat != null ? `${w.lat.toFixed(4)}, ${w.lon.toFixed(4)}` : ''))}</div>
        </div>
        <button class="wpe-remove" title="Remove" type="button">✕</button>
      `;
      li.querySelector('.wpe-remove').addEventListener('click', (e) => {
        e.stopPropagation();
        if (handlers.onRemove) handlers.onRemove(w.id);
      });
      listEl.appendChild(li);
    });

    counts[TAB_ALL].textContent = `(${state.waypoints.length})`;
    counts[TAB_STOPS].textContent = `(${state.waypoints.filter(w => w.kind === 'stop').length})`;
    counts[TAB_WAYPOINTS].textContent = `(${state.waypoints.filter(w => w.kind === 'waypoint').length})`;
  }

  function escape(s) {
    return String(s || '').replace(/[&<>"']/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  return {
    setWaypoints(list) {
      state.waypoints = list.slice();
      render();
    },
    setTotals({ distanceKm, durationS }) {
      totalsDist.textContent = distanceKm != null ? `${distanceKm.toFixed(1)} km` : '—';
      totalsTime.textContent = durationS != null ? `${Math.round(durationS / 60)} min` : '—';
    },
    getState() {
      return { collapsed: state.collapsed, tab: state.tab };
    },
  };
}
```

- [ ] **Step 2: Commit**

```bash
git add src/js/shared/waypoint-editor.js
git commit -m "feat(frontend): shared waypoint-editor sidebar (list, tabs, drag-reorder, collapse)"
```

---

### Task 12: Create page template and CSS

**Files:**
- Create: `server/templates/create.html`
- Create: `src/css/create.css`
- Create: `src/css/create-bundle.css`

- [ ] **Step 1: Create the template**

Create `server/templates/create.html`:

```html
{% extends "_base.html" %}
{% block title %}New Route — GPX Route Exploration{% endblock %}
{% block css %}
<link rel="stylesheet" href="/static/dist/create.min.css">
{% endblock %}
{% block nav_items %}
<a href="/">&larr; Library</a>
<span class="nav-route-title">New Route</span>
{% endblock %}
{% block content %}
<div id="create-header">
  <input id="route-title" type="text" placeholder="Route title…" value="Untitled Route">
  <span id="create-hint">Click the map to drop a waypoint. Right-click to mark as stop.</span>
  <div style="flex:1;"></div>
  <select id="route-profile" disabled title="Profile selection ships in M3">
    <option value="bicycle">Bike</option>
  </select>
  <label id="pin-start-label" title="When checked, the first waypoint is marked as the route's start.">
    <input id="pin-start-cb" type="checkbox"> Pin first as start
  </label>
  <button id="btn-optimise" type="button" disabled title="Optimisation ships in M3">Optimise</button>
  <button id="btn-generate" type="button">Generate Route</button>
  <button id="btn-save" type="button">Save</button>
</div>

<div id="create-main">
  <div id="map" style="position:relative;"></div>
  <aside id="editor-panel"></aside>
</div>
{% endblock %}
{% block scripts %}
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="/static/dist/create.min.js"></script>
{% endblock %}
```

- [ ] **Step 2: Create `src/css/create.css`**

```css
#create-header {
  display: flex; gap: 12px; align-items: center;
  padding: 10px 16px; background: #16213e;
  border-bottom: 2px solid #0f3460;
}
#route-title {
  background:#0f1d3a; border:1px solid #0f3460; color:#e6edf5;
  padding:6px 10px; border-radius:4px; font-size:0.95em; min-width:260px;
}
#create-hint { color:#a0a0b0; font-size:0.8em; }
#create-header select, #create-header button {
  background:#0f3460; color:#e6edf5; border:1px solid #2b3650;
  padding:6px 10px; border-radius:4px; cursor:pointer; font-size:0.8em;
}
#create-header button:disabled, #create-header select:disabled { opacity:0.4; cursor:not-allowed; }
#btn-generate { background:#e94560; border-color:#e94560; }
#pin-start-label { color:#a0a0b0; font-size:0.8em; display:flex; gap:4px; align-items:center; cursor:pointer; }

#create-main { display:flex; flex:1; min-height:0; }
#map { flex:1; min-height:400px; background:#16213e; }
#editor-panel { width:340px; background:#0f1d3a; border-left:1px solid #0f3460; overflow:auto; }

/* Editor widget */
.wpe { display:flex; flex-direction:column; height:100%; }
.wpe-head { padding:10px 14px; border-bottom:1px solid #0f3460; display:flex; justify-content:space-between; align-items:center; font-size:0.85em; }
.wpe-collapse { background:transparent; border:none; color:#a0a0b0; cursor:pointer; font-size:1em; }

.wpe-tabs { display:flex; border-bottom:1px solid #0f3460; background:#0a152b; font-size:0.8em; }
.wpe-tab { padding:8px 12px; color:#a0a0b0; cursor:pointer; border-bottom:2px solid transparent; flex:1; text-align:center; }
.wpe-tab.active { color:#e6edf5; border-bottom-color:#e94560; background:#0f1d3a; }
.wpe-count { color:#6a7a9a; font-size:0.9em; margin-left:4px; }

.wpe-totals { display:flex; gap:16px; padding:8px 14px; font-size:0.78em; background:#0a152b; border-bottom:1px solid #0f3460; }
.wpe-totals strong { color:#ff9f43; }

.wpe-list { flex:1; list-style:none; padding:4px 0; margin:0; overflow:auto; }
.wpe-empty { padding:20px 14px; color:#6a7a9a; font-size:0.85em; text-align:center; }

.wpe-item {
  display:flex; align-items:center; gap:8px; padding:10px 12px;
  border-left:3px solid transparent; font-size:0.85em;
}
.wpe-item:hover { background:#16213e; }
.wpe-item-stop { border-left-color:#ff4757; }
.wpe-item-waypoint { border-left-color:#00e5ff; }
.wpe-handle { color:#6a7a9a; cursor:grab; font-size:1.2em; }
.wpe-icon {
  width:26px; height:26px; display:inline-flex; align-items:center; justify-content:center;
  color:#fff; font-size:0.75em; font-weight:700; flex-shrink:0;
}
.wpe-icon-stop {
  background:#ff4757;
  clip-path: polygon(30% 0, 70% 0, 100% 30%, 100% 70%, 70% 100%, 30% 100%, 0 70%, 0 30%);
}
.wpe-icon-waypoint {
  background:#00e5ff; color:#0f1d3a;
  clip-path: polygon(50% 0, 100% 50%, 50% 100%, 0 50%);
}
.wpe-body { flex:1; min-width:0; }
.wpe-name { color:#e6edf5; }
.wpe-sub { color:#6a7a9a; font-size:0.75em; margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.wpe-badge { background:#ff4757; color:#fff; font-size:0.65em; padding:1px 6px; border-radius:8px; text-transform:uppercase; }
.wpe-remove { background:transparent; border:none; color:#6a7a9a; cursor:pointer; font-size:0.9em; padding:2px 4px; }
.wpe-remove:hover { color:#e6edf5; }

/* Leaflet marker styling (divIcons) */
.wpe-marker { display:flex; align-items:center; justify-content:center; color:#fff; font-size:0.75em; font-weight:700; }
.wpe-stop {
  width:30px; height:30px; background:#ff4757;
  clip-path: polygon(30% 0, 70% 0, 100% 30%, 100% 70%, 70% 100%, 30% 100%, 0 70%, 0 30%);
  border:2px solid #fff;
}
.wpe-waypoint {
  width:20px; height:20px; background:#00e5ff; color:#0f1d3a;
  clip-path: polygon(50% 0, 100% 50%, 50% 100%, 0 50%);
  border:2px solid #fff;
}
.wpe-start { box-shadow: 0 0 0 4px rgba(0,230,118,0.4); }
.wpe-end   { box-shadow: 0 0 0 4px rgba(255,95,21,0.4); }

.wpe-collapsed { width: 32px !important; }
.wpe-collapsed .wpe-head strong, .wpe-collapsed .wpe-tabs,
.wpe-collapsed .wpe-totals, .wpe-collapsed .wpe-list, .wpe-collapsed .wpe-empty { display:none; }
```

- [ ] **Step 3: Create `src/css/create-bundle.css`**

```css
@import "./base.css";
@import "./nav.css";
@import "./create.css";
```

- [ ] **Step 4: Commit**

```bash
git add server/templates/create.html src/css/create.css src/css/create-bundle.css
git commit -m "feat(frontend): Create Route page template and styles"
```

---

### Task 13: Create page entry point (app.js + map.js)

**Files:**
- Create: `src/js/create/app.js`
- Create: `src/js/create/map.js`

- [ ] **Step 1: Create the map module**

Create `src/js/create/map.js`:

```javascript
// --- Leaflet map init for the Create page ---

export function initCreateMap(elId) {
  const map = L.map(elId, { zoomControl: true });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19,
  }).addTo(map);
  // Default view — Brisbane-ish. A future milestone can persist last view.
  map.setView([-27.4705, 153.0260], 11);
  return map;
}

/**
 * Fit the map to a set of waypoints (ignoring ones without coords).
 */
export function fitToWaypoints(map, waypoints) {
  const latlngs = waypoints
    .filter(w => w.lat != null && w.lon != null)
    .map(w => [w.lat, w.lon]);
  if (latlngs.length >= 2) {
    map.fitBounds(L.latLngBounds(latlngs), { padding: [40, 40] });
  } else if (latlngs.length === 1) {
    map.setView(latlngs[0], 13);
  }
}
```

- [ ] **Step 2: Create the entry point**

Create `src/js/create/app.js`:

```javascript
// --- Create Route page entry point ---
//
// Flow:
//   1. On load, read ?route_id=<n> from the URL. If absent, create a
//      recipe-only route via POST /api/routes (JSON body) and rewrite the
//      URL to include the new id.
//   2. Render map; any click adds a waypoint (kind=waypoint). Right-click
//      on an existing waypoint promotes it to a stop and back.
//   3. Mount the shared waypoint-editor into #editor-panel. Wire its
//      onReorder/onRemove to the API.
//   4. Generate button calls /api/routes/<id>/generate and, on success,
//      redirects to the existing analysis page /route/<id>.
//   5. Save button is a no-op in M1 — edits persist immediately as they
//      happen. The button shows a toast and is kept for UX parity with
//      the spec; M2 reuses the same flow for the edit panel.

import { initCreateMap, fitToWaypoints } from './map.js';
import { renderMarkers } from '../shared/waypoint-markers.js';
import { mountWaypointEditor } from '../shared/waypoint-editor.js';
import * as api from '../shared/route-api.js';

async function ensureRouteId() {
  const url = new URL(window.location.href);
  const existing = url.searchParams.get('route_id');
  if (existing) return Number(existing);
  const titleInput = document.getElementById('route-title');
  const route = await api.createRouteRecipe({ title: titleInput.value.trim() || 'Untitled Route' });
  url.searchParams.set('route_id', route.id);
  history.replaceState(null, '', url.toString());
  return route.id;
}

async function reloadWaypoints(state, editor) {
  state.waypoints = await api.listWaypoints(state.routeId);
  editor.setWaypoints(state.waypoints);
  state.markers = renderMarkers(
    state.map, state.waypoints, state.markers,
    {
      draggable: true,
      onDragEnd: async (w, { lat, lon }) => {
        await api.patchWaypoint(state.routeId, w.id, { lat, lon });
        await reloadWaypoints(state, editor);
      },
      // Right-click a marker toggles between waypoint and stop (M1 spec).
      // M6 replaces this with a proper context menu offering more actions.
      onContextMenu: async (w) => {
        const nextKind = w.kind === 'stop' ? 'waypoint' : 'stop';
        await api.patchWaypoint(state.routeId, w.id, { kind: nextKind });
        await reloadWaypoints(state, editor);
      },
    },
  );
  // Reflect current pin_role in the checkbox (first waypoint's state wins).
  const pinCb = document.getElementById('pin-start-cb');
  if (pinCb) {
    pinCb.checked = state.waypoints.length > 0 && state.waypoints[0].pin_role === 'start';
    pinCb.disabled = state.waypoints.length === 0;
  }
}

async function main() {
  const state = {
    routeId: null,
    map: null,
    waypoints: [],
    markers: [],
  };

  state.routeId = await ensureRouteId();
  state.map = initCreateMap('map');

  const editor = mountWaypointEditor(
    document.getElementById('editor-panel'),
    {
      onReorder: async (orderedIds) => {
        await api.reorderWaypoints(state.routeId, orderedIds);
        await reloadWaypoints(state, editor);
      },
      onRemove: async (wptId) => {
        await api.deleteWaypoint(state.routeId, wptId);
        await reloadWaypoints(state, editor);
      },
    },
  );

  await reloadWaypoints(state, editor);
  fitToWaypoints(state.map, state.waypoints);

  // Click on map → append waypoint.
  state.map.on('click', async (e) => {
    const n = state.waypoints.length + 1;
    await api.appendWaypoint(state.routeId, {
      name: `Waypoint ${n}`,
      lat: e.latlng.lat,
      lon: e.latlng.lng,
      kind: 'waypoint',
    });
    await reloadWaypoints(state, editor);
  });

  // Right-click on map → no-op at this level (kind toggle is on marker click).
  // M6 upgrades right-click to a proper context menu.

  // Pin first-as-start checkbox.
  document.getElementById('pin-start-cb').addEventListener('change', async (e) => {
    if (state.waypoints.length === 0) return;
    const firstId = state.waypoints[0].id;
    await api.patchWaypoint(state.routeId, firstId,
                            { pin_role: e.target.checked ? 'start' : null });
    await reloadWaypoints(state, editor);
  });

  // Title edits persist on blur.
  document.getElementById('route-title').addEventListener('blur', async (e) => {
    const title = e.target.value.trim();
    if (!title) return;
    await fetch(`/api/routes/${state.routeId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    });
  });

  // Save is informational in M1 — edits already persist on every action.
  document.getElementById('btn-save').addEventListener('click', () => {
    const btn = document.getElementById('btn-save');
    const orig = btn.textContent;
    btn.textContent = 'Saved ✓';
    setTimeout(() => { btn.textContent = orig; }, 1200);
  });

  // Generate → Valhalla, then redirect to the analysis page.
  document.getElementById('btn-generate').addEventListener('click', async () => {
    const btn = document.getElementById('btn-generate');
    if (state.waypoints.length < 2) {
      alert('Add at least two waypoints before generating.');
      return;
    }
    btn.disabled = true;
    btn.textContent = 'Generating…';
    try {
      await api.generateRoute(state.routeId);
      window.location.href = `/route/${state.routeId}`;
    } catch (err) {
      alert('Generate failed: ' + err.message);
      btn.disabled = false;
      btn.textContent = 'Generate Route';
    }
  });
}

main().catch(err => {
  console.error(err);
  alert('Create page failed to load: ' + err.message);
});
```

- [ ] **Step 2: Commit**

```bash
git add src/js/create/app.js src/js/create/map.js
git commit -m "feat(frontend): Create Route page entry point with map + editor wiring"
```

---

### Task 14: Build integration for the create bundle

**Files:**
- Modify: `build.js`

- [ ] **Step 1: Extend the build config**

Edit `build.js`. Add two entries to the `configs` array:

```javascript
    { entryPoints: ['src/js/create/app.js'], outfile: path.join(outdir, 'create.min.js'), format: 'iife' },
    { entryPoints: ['src/css/create-bundle.css'], outfile: path.join(outdir, 'create.min.css') },
```

So the full configs array becomes:

```javascript
  const configs = [
    { entryPoints: ['src/js/analysis/app.js'], outfile: path.join(outdir, 'analysis.min.js'), format: 'iife' },
    { entryPoints: ['src/js/library/library-app.js'], outfile: path.join(outdir, 'library.min.js'), format: 'iife' },
    { entryPoints: ['src/js/create/app.js'], outfile: path.join(outdir, 'create.min.js'), format: 'iife' },
    { entryPoints: ['src/css/analysis-bundle.css'], outfile: path.join(outdir, 'analysis.min.css') },
    { entryPoints: ['src/css/library-bundle.css'], outfile: path.join(outdir, 'library.min.css') },
    { entryPoints: ['src/css/create-bundle.css'], outfile: path.join(outdir, 'create.min.css') },
  ];
```

- [ ] **Step 2: Run the build and confirm output**

```bash
npm run build
ls -la server/static/dist/create.*
```

Expected: `create.min.js` and `create.min.css` present and non-empty.

- [ ] **Step 3: Commit**

```bash
git add build.js
git commit -m "build: bundle create.min.{js,css} for the Create Route page"
```

---

### Task 15: Add /create page route

**Files:**
- Modify: `server/blueprints/pages.py`

- [ ] **Step 1: Read current pages.py**

Verify what's there:

```bash
cat server/blueprints/pages.py
```

You'll see two routes: `/` (library) and `/route/<int:route_id>` (analysis).

- [ ] **Step 2: Add the create route**

Append to `server/blueprints/pages.py`:

```python
@bp.route("/create")
def create_page():
    return render_template("create.html")
```

(Make sure `render_template` is imported at the top; it should already be if the other routes render templates.)

- [ ] **Step 3: Manual smoke test**

```bash
./dev.sh --env-file .env.development &
sleep 3
curl -sI http://localhost:5050/create | head -1
kill %1
```

Expected: `HTTP/1.1 200 OK`.

- [ ] **Step 4: Commit**

```bash
git add server/blueprints/pages.py
git commit -m "feat(pages): GET /create serves the Create Route page"
```

---

### Task 16: Library page — "+ New Route" button

**Files:**
- Modify: `src/js/library/library-app.js`

- [ ] **Step 1: Find the upload/header area**

```bash
grep -n "upload\|+ New" src/js/library/library-app.js | head
```

- [ ] **Step 2: Add the button**

The Create button lives in the same header as Upload. Edit `src/js/library/library-app.js` — in the setup that builds the header controls, add:

```javascript
// --- New Route button: jumps to the Create page ---
const newRouteBtn = document.createElement('button');
newRouteBtn.className = 'new-route-btn';
newRouteBtn.textContent = '+ New Route';
newRouteBtn.addEventListener('click', () => {
  window.location.href = '/create';
});
document.querySelector('#library-header').appendChild(newRouteBtn);
```

(Adjust the selector to match the actual header container — inspect `server/templates/library.html` to confirm its id/class.)

- [ ] **Step 3: Add CSS**

In `src/css/library.css`, add:

```css
.new-route-btn {
  background:#e94560; color:#fff; border:none;
  padding:6px 12px; border-radius:4px; cursor:pointer; font-size:0.85em;
}
.new-route-btn:hover { background:#c93651; }
```

- [ ] **Step 4: Rebuild and smoke-test**

```bash
npm run build
# visually confirm the button appears by visiting the library page
```

- [ ] **Step 5: Commit**

```bash
git add src/js/library/library-app.js src/css/library.css
git commit -m "feat(library): '+ New Route' button navigates to /create"
```

---

### Task 17: Regression test — upload + analyse existing routes still works

**Files:**
- None (this is a validation task — no code change)

- [ ] **Step 1: Run the full non-UI suite**

```bash
source .venv/bin/activate
pytest tests/ --ignore=tests/test_ui_library.py --ignore=tests/test_ui_analysis.py --ignore=tests/test_ui_create.py -q
```

Expected: everything green.

- [ ] **Step 2: Run the existing UI suites (desktop)**

```bash
pytest tests/test_ui_library.py tests/test_ui_analysis.py -v
```

Expected: every test passes (M1 must not break existing paths).

- [ ] **Step 3: If any failure, pause and fix before advancing**

Do not proceed to Task 18 if there are regressions. Investigate — common regressions:
- Blueprint ordering broken (check `server/blueprints/__init__.py`).
- Schema IF NOT EXISTS missed (check `schema.sql`).
- Old tests counted blueprints or routes and the numbers changed.

---

### Task 18: Playwright E2E test for the Create page

**Files:**
- Create: `tests/test_ui_create.py`

- [ ] **Step 1: Write the E2E tests**

Create `tests/test_ui_create.py`:

```python
"""Playwright E2E tests for the Create Route page."""

import json
import os
from unittest.mock import patch

from playwright.sync_api import expect

import tests.test_api_routing as routing_tests  # reuse _fake_valhalla_response


def _click_map_at(page, selector, x_frac, y_frac):
    box = page.locator(selector).bounding_box()
    assert box
    page.mouse.click(box["x"] + x_frac * box["width"], box["y"] + y_frac * box["height"])


def test_create_page_loads(page, server_url):
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    expect(page.locator("#map")).to_be_visible()
    expect(page.locator("#editor-panel")).to_be_visible()
    # URL gains ?route_id=<n> shortly after load (recipe auto-create).
    page.wait_for_function("() => new URL(location.href).searchParams.get('route_id') !== null",
                           timeout=5000)


def test_click_map_adds_waypoint(page, server_url):
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    page.wait_for_function("() => new URL(location.href).searchParams.get('route_id') !== null")
    _click_map_at(page, "#map", 0.3, 0.4)
    # Sidebar should show 1 item.
    expect(page.locator(".wpe-item").first).to_be_visible(timeout=3000)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 1", timeout=3000,
    )


def test_add_three_waypoints_and_remove_one(page, server_url):
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    page.wait_for_function("() => new URL(location.href).searchParams.get('route_id') !== null")
    _click_map_at(page, "#map", 0.25, 0.4)
    _click_map_at(page, "#map", 0.5, 0.4)
    _click_map_at(page, "#map", 0.75, 0.4)
    page.wait_for_function("() => document.querySelectorAll('.wpe-item').length === 3", timeout=5000)
    # Remove middle item.
    page.locator(".wpe-item").nth(1).locator(".wpe-remove").click()
    page.wait_for_function("() => document.querySelectorAll('.wpe-item').length === 2", timeout=3000)


def test_marker_right_click_toggles_kind(page, server_url):
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    page.wait_for_function("() => new URL(location.href).searchParams.get('route_id') !== null")
    _click_map_at(page, "#map", 0.3, 0.4)
    page.wait_for_selector(".wpe-item-waypoint", timeout=3000)
    # Right-click the marker toggles kind waypoint → stop (per M1 spec).
    page.locator(".wpe-marker.wpe-waypoint").first.click(button="right")
    page.wait_for_selector(".wpe-item-stop", timeout=3000)


def test_drag_reorder_waypoints(page, server_url):
    """Drag the second sidebar row above the first; verify the PUT reorder
    API landed and the list order swapped."""
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    page.wait_for_function("() => new URL(location.href).searchParams.get('route_id') !== null")
    # Add three waypoints.
    _click_map_at(page, "#map", 0.25, 0.4)
    _click_map_at(page, "#map", 0.5, 0.4)
    _click_map_at(page, "#map", 0.75, 0.4)
    page.wait_for_function("() => document.querySelectorAll('.wpe-item').length === 3", timeout=5000)
    # Names are "Waypoint 1", "Waypoint 2", "Waypoint 3" in order.
    names_before = page.locator(".wpe-item .wpe-name").all_text_contents()
    assert [n.strip() for n in names_before] == ["Waypoint 1", "Waypoint 2", "Waypoint 3"]
    # Drag item #3's handle up above item #1's handle.
    src = page.locator(".wpe-item").nth(2).locator(".wpe-handle")
    dst = page.locator(".wpe-item").nth(0).locator(".wpe-handle")
    src.drag_to(dst)
    # Wait for API round-trip + rerender.
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item .wpe-name')[0].textContent.trim() === 'Waypoint 3'",
        timeout=3000,
    )


def test_pin_first_as_start(page, server_url):
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    page.wait_for_function("() => new URL(location.href).searchParams.get('route_id') !== null")
    _click_map_at(page, "#map", 0.3, 0.4)
    _click_map_at(page, "#map", 0.6, 0.4)
    page.wait_for_function("() => document.querySelectorAll('.wpe-item').length === 2", timeout=3000)
    # Check the box; the first row should gain a Start badge.
    page.locator("#pin-start-cb").check()
    expect(page.locator(".wpe-item").first.locator(".wpe-badge")).to_have_text("Start", timeout=3000)
    # Uncheck → badge disappears.
    page.locator("#pin-start-cb").uncheck()
    expect(page.locator(".wpe-item").first.locator(".wpe-badge")).to_have_count(0, timeout=3000)
```

- [ ] **Step 2: Run Playwright suite**

```bash
source .venv/bin/activate
python -m pytest tests/test_ui_create.py -v
```

Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_ui_create.py
git commit -m "test: Playwright E2E for Create page (add/remove/kind-toggle)"
```

---

### Task 19: Manual verification checklist and M1 close-out

**Files:**
- Modify: `docs/superpowers/plans/2026-04-17-route-creation-m1.md` (append checklist outcome)

This task is a human sign-off. Run through it end-to-end on the running dev server.

- [ ] **Step 1: Start the dev server**

```bash
./dev.sh --env-file .env.development
```

Wait for "Starting Flask dev server on port 5050".

- [ ] **Step 2: Manual smoke test**

In a browser:

1. Go to `http://localhost:5050/` — library loads; click "+ New Route".
2. Create page opens at `/create`; URL gets a `?route_id=<n>` query string within 2 s.
3. Click 3–5 places on the map. Each adds a cyan diamond waypoint on the map and a row in the sidebar.
4. Click on a map waypoint marker. It turns into a red octagon and the sidebar row shows as a stop.
5. Drag a row in the sidebar to reorder. Map numbers update.
6. Click the ✕ on a sidebar row. The waypoint disappears from both sidebar and map; numbering stays contiguous.
7. Click "Generate Route". After 1–10 seconds you're redirected to `/route/<n>`, the analysis page, with a detailed track drawn on the map, gradient colouring on, stats populated, and the profile chart rendered.

- [ ] **Step 3: If any step fails, file it as an issue and return to the relevant task to fix before marking M1 complete.**

- [ ] **Step 4: Run the full Playwright suite one more time**

```bash
pytest tests/test_ui_library.py tests/test_ui_analysis.py tests/test_ui_create.py -v
```

Expected: every test green.

- [ ] **Step 5: Append manual sign-off to the plan**

Add a line to the very bottom of `docs/superpowers/plans/2026-04-17-route-creation-m1.md`:

```markdown
---

**M1 verified:** YYYY-MM-DD by <name>. All tasks complete, full regression + new Playwright suite green, manual checklist step 2 passed on `http://localhost:5050/`.
```

- [ ] **Step 6: Commit the verification marker**

```bash
git add docs/superpowers/plans/2026-04-17-route-creation-m1.md
git commit -m "chore: M1 verification sign-off"
```

- [ ] **Step 7: Merge to main**

```bash
git checkout main
git pull --ff-only  # we have a remote now
git merge --no-ff feature/route-creation -m "feat: route creation M1 — recipe schema + manual creation"
git push origin main
```

- [ ] **Step 8: Announce completion**

Tell the user: **"M1 complete and merged to `main`. Ready to write the M2 plan (inline Edit panel on the Analysis page) — shall I proceed?"**

---

**M1 verified:** 2026-11-14 by Claude Code, for review by Phil Gersekowski. Audited after the fact against the spec's M1 acceptance list. `test_api_waypoints.py`, `test_api_routing.py`, `test_models_waypoints.py` and `test_ui_create.py` pass (part of a 95-test run with the M2 suites). Create, reorder, promote-to-stop, Generate and the analysis redirect are exercised by those suites and by the M3 smoke script against the live Valhalla. The manual checklist was not walked by hand. Deviation from the spec: the profile picker is no longer locked to `bicycle`, because M3 enabled it. Full-suite status is as recorded in the M3 sign-off (5 pre-existing environmental failures, 2 flakes).
