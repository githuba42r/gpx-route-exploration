# Route Creation M3: Routing Options, Elevation-Aware Costing, Optimisation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the bare profile picker that M1 stubbed into the project's actual elevation- and surface-aware routing UX. Users pick a routing preset (Road / Gravel-MTB / Easy / Hike / Drive / Custom), tweak costing sliders, pin start/end, include/exclude individual waypoints, toggle round-trip, optimise the stop order (NN + 2-opt), and see gradient warnings on legs that cross a user-configured steepness threshold. The recipe acquires one new column (`route_waypoints.linked_to_previous`) so shape-waypoints ride with their preceding stop through optimiser reorders.

**Architecture:** Three shippable phases. **M3a** adds preset/costing/pin/include UI on the Create page and finally threads `costing_options` through `/api/routes/<id>/generate` (currently hard-coded to `{}`). **M3b** introduces `server/routing/optimiser.py` (pure-Python NN + 2-opt over *groups*, where a group is a stop plus its trailing linked waypoints), a new column via the runtime-migration pattern from M1, and wires "Optimise" + right-click unlink/re-link. **M3c** adds a Python post-processor (`server/route_postprocess.py`) that decodes Valhalla's per-leg elevation samples and writes `{from_m, to_m, peak_grad_pct}` warnings into the existing `route_legs.warnings` column.

**Tech Stack:** Flask 3 + SQLite (existing), Valhalla (existing), Leaflet 1.9.4 (existing), SortableJS (existing M1 dep), esbuild, pytest + Playwright. No new runtime deps.

---

## Decisions locked up front

These are judgement calls the spec left open or where the existing schema constrains us. Surface them here so nothing gets re-litigated mid-execution. If the reviewer wants different answers, flag before Task 1 — re-planning after code lands is expensive.

### D1 — The `hybrid` preset stays as a legacy alias for `road`

`server/models/schema.sql` ships `route_options.costing_preset DEFAULT 'hybrid'` and allows `('road','gravel-mtb','easy','hike','drive','custom','hybrid')` in its CHECK. SQLite can't `ALTER TABLE ... MODIFY CONSTRAINT` without a full table rebuild. **We keep `hybrid` in the CHECK and treat it as a read-side alias for `road`.** `GET /api/routing-presets` excludes `hybrid` from the user-visible list; the default for newly-created recipes is flipped to `road` via `update_options` on recipe creation.

### D2 — `linked_to_previous` column default is `1` across both kinds

The spec reads "DEFAULT 1 for kind=waypoint, DEFAULT 0 for kind=stop", which SQLite can't express in a single ADD COLUMN. We use a plain `NOT NULL DEFAULT 1`. The optimiser's grouping logic treats each `kind='stop'` row as a group-starter regardless of the flag, so an errant `1` on a stop is a no-op. `kind='waypoint'` rows — the only case where the flag is load-bearing — get the correct default. The right-click menu hides the unlink/re-link entries on stops, so the UI can't set it incorrectly.

### D3 — Gradient post-processor is a Python port, not JS reuse

`src/js/analysis/track-processor.js::processTrackData` smooths elevations with a window and computes windowed gradient over a minimum-distance window. We port the relevant chunk to Python in `server/route_postprocess.py` because:
- Post-processing runs server-side after `replace_legs`, so the persisted `route_legs.warnings` is populated before the response ships.
- Valhalla's response already has per-leg `shape` (polyline6) and a per-leg `elevation` array when `elevation_interval: 10` is set — decoding + sampling in Python avoids a client round-trip.

The port is ~60 LoC; not worth wiring a Node subprocess.

### D4 — Verify the Valhalla elevation field before coding

Valhalla returns per-leg elevation as `leg.elevation` (a flat list of metres, sampled every `elevation_interval` metres along the polyline). Task M3c-1 opens `tests/fixtures/valhalla_response_sample.json` (shipped by M1) and confirms the exact field name — **do not write the post-processor tests against an assumed schema**. If the fixture pre-dates `elevation_interval`, generate a fresh sample via the running dev Valhalla in that first task.

### D5 — Optimiser-cache invalidation uses `last_optimised_at`

There's no dedicated cache column. The optimiser endpoint stamps `route_options.last_optimised_at = int(time.time())` on success. Toggling `linked_to_previous` on any waypoint clears `last_optimised_at` (sets to NULL) so the next Optimise click re-runs rather than serving stale groups.

---

## What already exists — do NOT migrate or re-create in M3

These exist as of M1/M2 closing commits. Verify, don't touch:

- `route_options.costing_options TEXT` (nullable JSON). M3a writes JSON; no migration needed.
- `route_options.max_gradient_warn REAL`. M3a exposes it in the UI; no migration.
- `route_options.last_optimised_at INTEGER`. M3b writes; no migration.
- `route_legs.max_grade_pct REAL` and `route_legs.warnings TEXT`. M3c writes both; no migration.
- `server/routing/valhalla_client.py::build_request_body` already accepts `costing_options` + `round_trip` and already sends `elevation_interval: 10`. M3a-Task 4 verifies with a test; no code change.
- `server/blueprints/api_routing.py::generate_route` line 48 currently hard-codes `costing_options={}` with a `# M3 wires the full costing options` comment. That's the exact line M3a-Task 5 replaces.

---

# Phase M3a — Options UI + generate wiring

**Ships a green path where the user picks a preset, optionally tweaks sliders, toggles round-trip, pins start/end, and excludes waypoints from the sidebar or a right-click menu — then Generate ships the full costing payload to Valhalla.** No optimiser, no gradient warnings yet. After M3a commits, a manual smoke test: pick Gravel-MTB on a route containing an unpaved cut-through, Generate, confirm the track uses the cut-through (whereas Road would hug the sealed road).

## File structure — M3a

**Create:**
- `server/routing/presets.py` — preset → `costing_options` dict + `resolve()` helper.
- `server/blueprints/api_presets.py` — `GET /api/routing-presets` endpoint.
- `tests/test_routing_presets.py` — unit tests.
- `tests/test_api_presets.py` — endpoint test.
- `tests/test_api_options.py` — PATCH /api/routes/<id>/options tests.

**Modify:**
- `server/blueprints/__init__.py` — register `api_presets`.
- `server/blueprints/api_routes.py` — extend `_create_recipe_only` to default `costing_preset='road'` (D1).
- `server/models/waypoints.py` — add `update_options` allowed field is already correct; verify.
- `server/blueprints/api_routing.py` — read options + pass to `vc.call_route`.
- `server/blueprints/api_waypoints.py` — `pin_role` already handled in PATCH; confirm with a test.
- `server/templates/create.html` — add preset dropdown, custom costing panel toggle, round-trip checkbox, max-gradient-warn input. Replace the `disabled` attribute on `#route-profile`.
- `src/js/create/app.js` — wire the above to PATCH `/api/routes/<id>/options`; add "excluded" dim to sidebar rows; add "Include in route" / "Exclude from route" entries to right-click context menu (already exists — verify); add a per-row include toggle icon.
- `src/js/shared/route-api.js` — add `getRoutingPresets()`, `patchRouteOptions(routeId, patch)`.
- `src/js/shared/waypoint-editor.js` — render excluded rows dimmed + an eye/eye-slash click toggle on each row; add start/end pin-role badge + a small checkbox in the row body for hover-affordance pin.
- `src/css/create.css` — styles for preset dropdown + custom panel + excluded rows.
- `tests/test_ui_options.py` — new Playwright suite covering the options UX.

---

### Task M3a-1: Branch verification & M3 kickoff

**Files:** none (read-only).

- [ ] **Step 1:** Verify the branch is `feature/route-creation`:

```bash
git rev-parse --abbrev-ref HEAD
```

Expected: `feature/route-creation`. If not, `git checkout feature/route-creation` before proceeding.

- [ ] **Step 2:** Confirm working tree is clean and M2 has landed:

```bash
git status --short
git log --oneline -5
```

Expected: no working-tree changes; recent history shows M2 commits (per-leg refactor, line-drag, etc.).

- [ ] **Step 3:** Confirm every "what already exists" bullet from the plan header holds:

```bash
grep -n "costing_options" server/models/schema.sql
grep -n "max_gradient_warn" server/models/schema.sql
grep -n "warnings" server/models/schema.sql
grep -n "elevation_interval" server/routing/valhalla_client.py
grep -n "M3 wires the full costing options" server/blueprints/api_routing.py
```

Expected: every grep matches. If any miss, STOP — the schema has drifted and the plan needs amending.

No commit — kickoff is read-only.

---

### Task M3a-2: Routing presets module

**Files:**
- Create: `server/routing/presets.py`
- Create: `tests/test_routing_presets.py`

The preset → `costing_options` mapping belongs on the server so clients never hard-code costing knobs. Each preset is a dict that will be merged into the `costing_options.<profile>` block of a Valhalla `/route` request.

- [ ] **Step 1: Write failing unit tests.** Create `tests/test_routing_presets.py`:

```python
"""Unit tests for routing presets (M3a)."""

import pytest

from server.routing import presets


def test_preset_list_contains_expected_keys():
    listed = presets.list_presets()
    names = [p["name"] for p in listed]
    assert names == ["road", "gravel-mtb", "easy", "hike", "drive", "custom"]


def test_preset_list_hides_hybrid_alias():
    # 'hybrid' is a legacy DB value (see D1); it must NOT appear in the
    # user-facing preset list.
    names = [p["name"] for p in presets.list_presets()]
    assert "hybrid" not in names


def test_resolve_known_preset_returns_costing_options_and_profile():
    res = presets.resolve("gravel-mtb")
    assert res["profile"] == "bicycle"
    assert res["costing_options"]["bicycle_type"] == "Mountain"
    # gravel-mtb accepts unpaved surfaces.
    assert res["costing_options"]["use_roads"] < 0.6


def test_resolve_hybrid_alias_maps_to_road():
    # D1: legacy DB rows with costing_preset='hybrid' still resolve.
    alias = presets.resolve("hybrid")
    road = presets.resolve("road")
    assert alias == road


def test_resolve_custom_returns_empty_options():
    # 'custom' is the opt-out: the client supplies its own costing_options
    # and the preset contributes nothing.
    res = presets.resolve("custom")
    assert res["costing_options"] == {}


def test_resolve_unknown_preset_raises():
    with pytest.raises(ValueError):
        presets.resolve("not-a-preset")


def test_hike_uses_pedestrian_profile():
    res = presets.resolve("hike")
    assert res["profile"] == "pedestrian"


def test_drive_uses_auto_profile():
    res = presets.resolve("drive")
    assert res["profile"] == "auto"
```

- [ ] **Step 2: Run — confirm failure.**

```bash
source .venv/bin/activate
pytest tests/test_routing_presets.py -v
```

Expected: 7 failures (ImportError — module doesn't exist yet).

- [ ] **Step 3: Implement `server/routing/presets.py`.**

```python
"""Routing presets: preset name → (profile, costing_options).

Each entry maps to a Valhalla /route request shape:
    costing = <profile>          ('bicycle' | 'pedestrian' | 'auto')
    costing_options.<profile> = <costing_options dict>

The UI lists these in order and sends the selected preset name to the
server; the server resolves it here and merges the dict into the
Valhalla request body. 'custom' is the opt-out — the client ships its
own costing_options and the preset contributes nothing.

'hybrid' is a legacy alias for 'road' — see plan Decision D1.
"""

# Tunable knobs — see Valhalla /route reference. Values chosen to reflect
# the spec's intended user personas. Adjust here, not in the UI.
_PRESETS = {
    "road": {
        "profile": "bicycle",
        "costing_options": {
            "bicycle_type": "Road",
            "use_roads": 0.9,
            "use_hills": 0.4,
            "avoid_bad_surfaces": 0.9,
        },
        "description": "Sealed roads, moderate hills tolerated.",
    },
    "gravel-mtb": {
        "profile": "bicycle",
        "costing_options": {
            "bicycle_type": "Mountain",
            "use_roads": 0.3,
            "use_hills": 0.6,
            "avoid_bad_surfaces": 0.2,
        },
        "description": "Unpaved tracks welcome, hills OK.",
    },
    "easy": {
        "profile": "bicycle",
        "costing_options": {
            "bicycle_type": "Hybrid",
            "use_roads": 0.6,
            "use_hills": 0.1,
            "avoid_bad_surfaces": 0.7,
        },
        "description": "Flat, sealed preferred.",
    },
    "hike": {
        "profile": "pedestrian",
        "costing_options": {
            "use_tracks": 0.9,
            "use_hills": 0.6,
        },
        "description": "On-foot, tracks and paths preferred.",
    },
    "drive": {
        "profile": "auto",
        "costing_options": {},
        "description": "Motor vehicle, shortest time.",
    },
    "custom": {
        "profile": "bicycle",
        "costing_options": {},
        "description": "Bring your own costing options.",
    },
}

# D1: 'hybrid' is a read-side alias for 'road'. Kept because the CHECK
# constraint in route_options accepts it and existing rows may carry it.
_ALIAS = {"hybrid": "road"}


def list_presets():
    """Return the user-facing preset list (hybrid alias excluded)."""
    return [
        {"name": name, "profile": p["profile"], "description": p["description"]}
        for name, p in _PRESETS.items()
    ]


def resolve(name):
    """Resolve a preset name (or legacy alias) to its profile + costing options."""
    resolved = _ALIAS.get(name, name)
    if resolved not in _PRESETS:
        raise ValueError(f"unknown preset: {name}")
    entry = _PRESETS[resolved]
    return {
        "profile": entry["profile"],
        "costing_options": dict(entry["costing_options"]),
    }
```

- [ ] **Step 4: Run — confirm pass.**

```bash
pytest tests/test_routing_presets.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit.**

```bash
git add server/routing/presets.py tests/test_routing_presets.py
git commit -m "feat(routing): add preset → costing-options mapping (M3a)"
```

---

### Task M3a-3: `GET /api/routing-presets` endpoint

**Files:**
- Create: `server/blueprints/api_presets.py`
- Create: `tests/test_api_presets.py`
- Modify: `server/blueprints/__init__.py`

- [ ] **Step 1: Write failing endpoint test.** Create `tests/test_api_presets.py`:

```python
"""Endpoint tests for /api/routing-presets (M3a)."""


def test_get_presets_returns_expected_shape(client):
    resp = client.get("/api/routing-presets")
    assert resp.status_code == 200
    body = resp.get_json()
    assert isinstance(body, list)
    names = [p["name"] for p in body]
    assert names == ["road", "gravel-mtb", "easy", "hike", "drive", "custom"]
    # Each entry has a profile and description.
    for p in body:
        assert "profile" in p
        assert "description" in p


def test_get_presets_hides_hybrid(client):
    body = client.get("/api/routing-presets").get_json()
    assert "hybrid" not in [p["name"] for p in body]
```

- [ ] **Step 2: Run — confirm failure.**

```bash
pytest tests/test_api_presets.py -v
```

Expected: 2 failures (404 — blueprint not registered).

- [ ] **Step 3: Implement `server/blueprints/api_presets.py`.**

```python
"""Expose the routing presets catalogue to the client."""

from flask import Blueprint, jsonify

from server.routing import presets

bp = Blueprint("api_presets", __name__, url_prefix="/api")


@bp.route("/routing-presets", methods=["GET"])
def get_presets():
    return jsonify(presets.list_presets()), 200
```

- [ ] **Step 4: Register.** Modify `server/blueprints/__init__.py`:

```python
def register_blueprints(app):
    from server.blueprints.api_routes import bp as routes_bp
    from server.blueprints.api_gpx import bp as gpx_bp
    from server.blueprints.api_categories import bp as categories_bp
    from server.blueprints.api_tags import bp as tags_bp
    from server.blueprints.api_waypoints import bp as waypoints_bp
    from server.blueprints.api_routing import bp as routing_bp
    from server.blueprints.api_presets import bp as presets_bp
    from server.blueprints.proxy import bp as proxy_bp
    app.register_blueprint(routes_bp)
    app.register_blueprint(gpx_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(tags_bp)
    app.register_blueprint(waypoints_bp)
    app.register_blueprint(routing_bp)
    app.register_blueprint(presets_bp)
    app.register_blueprint(proxy_bp)

    from server.blueprints.pages import bp as pages_bp
    app.register_blueprint(pages_bp)
```

- [ ] **Step 5: Run — confirm pass.**

```bash
pytest tests/test_api_presets.py tests/test_routing_presets.py -v
```

Expected: 9 passed.

- [ ] **Step 6: Commit.**

```bash
git add server/blueprints/api_presets.py server/blueprints/__init__.py tests/test_api_presets.py
git commit -m "feat(api): GET /api/routing-presets endpoint (M3a)"
```

---

### Task M3a-4: PATCH `/api/routes/<id>/options` endpoint

**Files:**
- Modify: `server/blueprints/api_routing.py` (add PATCH handler on the route-options resource)
- Create: `tests/test_api_options.py`

The route-options row is currently only mutated indirectly (by `/generate`). M3a needs a first-class PATCH so the frontend can persist user edits to `profile`, `costing_preset`, `costing_options`, `round_trip`, `max_gradient_warn` without triggering a Valhalla call.

- [ ] **Step 1: Write failing endpoint tests.** Create `tests/test_api_options.py`:

```python
"""Tests for PATCH /api/routes/<id>/options (M3a)."""

import json


def _create_route(client, title="T"):
    r = client.post("/api/routes", json={"title": title},
                    content_type="application/json")
    return r.get_json()["id"]


def test_patch_options_sets_round_trip(client):
    rid = _create_route(client)
    resp = client.patch(f"/api/routes/{rid}/options",
                        json={"round_trip": True})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["round_trip"] == 1


def test_patch_options_sets_preset_and_costing_options(client):
    rid = _create_route(client)
    resp = client.patch(f"/api/routes/{rid}/options", json={
        "costing_preset": "gravel-mtb",
        "costing_options": {"use_hills": 0.8, "bicycle_type": "Mountain"},
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["costing_preset"] == "gravel-mtb"
    # costing_options is stored as JSON text; decode for the assertion.
    assert json.loads(body["costing_options"]) == {
        "use_hills": 0.8, "bicycle_type": "Mountain",
    }


def test_patch_options_rejects_unknown_preset(client):
    rid = _create_route(client)
    resp = client.patch(f"/api/routes/{rid}/options",
                        json={"costing_preset": "not-real"})
    assert resp.status_code == 400
    assert "preset" in resp.get_json()["error"].lower()


def test_patch_options_sets_profile(client):
    rid = _create_route(client)
    resp = client.patch(f"/api/routes/{rid}/options", json={"profile": "pedestrian"})
    assert resp.status_code == 200
    assert resp.get_json()["profile"] == "pedestrian"


def test_patch_options_sets_max_gradient_warn(client):
    rid = _create_route(client)
    resp = client.patch(f"/api/routes/{rid}/options",
                        json={"max_gradient_warn": 10.0})
    assert resp.status_code == 200
    assert resp.get_json()["max_gradient_warn"] == 10.0


def test_patch_options_404_on_unknown_route(client):
    resp = client.patch("/api/routes/99999/options", json={"round_trip": True})
    assert resp.status_code == 404
```

- [ ] **Step 2: Run — confirm failure.**

```bash
pytest tests/test_api_options.py -v
```

Expected: 6 failures (404 — endpoint missing).

- [ ] **Step 3: Implement the endpoint.** Append to `server/blueprints/api_routing.py`:

```python
import json as _json

from server.routing import presets


ALLOWED_PROFILES = {"bicycle", "pedestrian", "auto"}
ALLOWED_PRESETS = {"road", "gravel-mtb", "easy", "hike", "drive", "custom", "hybrid"}


@bp.route("/routes/<int:route_id>/options", methods=["PATCH"])
def patch_route_options(route_id):
    user_id = get_current_user()
    route = get_route(user_id, route_id)
    if route is None:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json(silent=True) or {}

    patch = {}
    if "profile" in data:
        p = data["profile"]
        if p not in ALLOWED_PROFILES:
            return jsonify({"error": f"invalid profile: {p}"}), 400
        patch["profile"] = p
    if "costing_preset" in data:
        cp = data["costing_preset"]
        if cp not in ALLOWED_PRESETS:
            return jsonify({"error": f"invalid costing_preset: {cp}"}), 400
        patch["costing_preset"] = cp
    if "costing_options" in data:
        co = data["costing_options"]
        if co is None:
            patch["costing_options"] = None
        elif isinstance(co, dict):
            patch["costing_options"] = _json.dumps(co)
        else:
            return jsonify({"error": "costing_options must be an object"}), 400
    if "round_trip" in data:
        patch["round_trip"] = 1 if bool(data["round_trip"]) else 0
    if "max_gradient_warn" in data:
        mg = data["max_gradient_warn"]
        patch["max_gradient_warn"] = None if mg is None else float(mg)

    # Changing profile / preset / costing_options invalidates cached legs —
    # the spec requires "needs regeneration" semantics. Drop the leg cache
    # and clear last_generated_at so the Analysis page gates on Regenerate.
    geometry_affecting = {"profile", "costing_preset", "costing_options", "round_trip"}
    if geometry_affecting.intersection(patch.keys()):
        wp_model.replace_legs(route_id, [])
        patch["last_generated_at"] = None

    updated = wp_model.update_options(route_id, **patch)
    return jsonify(updated), 200
```

Also update the import block at the top of `api_routing.py`:

```python
# ... existing imports above ...
from server.routing import presets  # noqa: F401 — used by patch_route_options
```

Note the existing `wp_model.update_options` accepts `costing_options` already (see its allowed-set). `None` is filtered by the model's `if v is not None` guard — we reach through that by passing the JSON string (never None) when the client sent a dict, and we skip the key entirely when the client wants a clear (TODO if needed; for M3a `None` round-trip isn't a required use case).

- [ ] **Step 4: Run — confirm pass.**

```bash
pytest tests/test_api_options.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit.**

```bash
git add server/blueprints/api_routing.py tests/test_api_options.py
git commit -m "feat(api): PATCH /api/routes/<id>/options (M3a)"
```

---

### Task M3a-5: Wire `costing_options` through `generate_route`

**Files:**
- Modify: `server/blueprints/api_routing.py`
- Modify: `tests/test_api_routing.py`

The hard-coded `costing_options={}` at line 48 is the exact line replaced here. We build the request-time options by resolving the stored preset and merging any persisted overrides.

- [ ] **Step 1: Write failing test.** Add to `tests/test_api_routing.py`:

```python
import json
from unittest.mock import patch


def test_generate_uses_resolved_costing_options(client, app, monkeypatch):
    # Create a route + 2 waypoints, set preset to gravel-mtb.
    rid = client.post("/api/routes", json={"title": "Gravel"},
                      content_type="application/json").get_json()["id"]
    client.post(f"/api/routes/{rid}/waypoints",
                json={"kind": "stop", "name": "A", "lat": -27.4, "lon": 152.9})
    client.post(f"/api/routes/{rid}/waypoints",
                json={"kind": "stop", "name": "B", "lat": -27.5, "lon": 152.8})
    client.patch(f"/api/routes/{rid}/options",
                 json={"costing_preset": "gravel-mtb"})

    captured = {}

    def fake_call_route(**kwargs):
        captured.update(kwargs)
        with open("tests/fixtures/valhalla_response_sample.json") as f:
            return json.load(f)

    monkeypatch.setattr("server.blueprints.api_routing.vc.call_route", fake_call_route)
    resp = client.post(f"/api/routes/{rid}/generate")
    assert resp.status_code == 200, resp.get_data(as_text=True)

    # Valhalla got the gravel-mtb costing options, not an empty dict.
    co = captured["costing_options"]
    assert co.get("bicycle_type") == "Mountain"
    assert co.get("use_roads", 1.0) < 0.5


def test_generate_custom_preset_uses_stored_costing_options(client, app, monkeypatch):
    rid = client.post("/api/routes", json={"title": "Custom"},
                      content_type="application/json").get_json()["id"]
    client.post(f"/api/routes/{rid}/waypoints",
                json={"kind": "stop", "name": "A", "lat": -27.4, "lon": 152.9})
    client.post(f"/api/routes/{rid}/waypoints",
                json={"kind": "stop", "name": "B", "lat": -27.5, "lon": 152.8})
    client.patch(f"/api/routes/{rid}/options", json={
        "costing_preset": "custom",
        "costing_options": {"use_hills": 0.95, "bicycle_type": "Mountain"},
    })

    captured = {}

    def fake_call_route(**kwargs):
        captured.update(kwargs)
        with open("tests/fixtures/valhalla_response_sample.json") as f:
            return json.load(f)

    monkeypatch.setattr("server.blueprints.api_routing.vc.call_route", fake_call_route)
    resp = client.post(f"/api/routes/{rid}/generate")
    assert resp.status_code == 200

    assert captured["costing_options"] == {"use_hills": 0.95, "bicycle_type": "Mountain"}


def test_generate_round_trip_flag_reaches_valhalla(client, app, monkeypatch):
    rid = client.post("/api/routes", json={"title": "Loop"},
                      content_type="application/json").get_json()["id"]
    client.post(f"/api/routes/{rid}/waypoints",
                json={"kind": "stop", "name": "A", "lat": -27.4, "lon": 152.9})
    client.post(f"/api/routes/{rid}/waypoints",
                json={"kind": "stop", "name": "B", "lat": -27.5, "lon": 152.8})
    client.patch(f"/api/routes/{rid}/options", json={"round_trip": True})

    captured = {}

    def fake_call_route(**kwargs):
        captured.update(kwargs)
        with open("tests/fixtures/valhalla_response_sample_round_trip.json") as f:
            return json.load(f)

    # The round-trip fixture has 2 legs (for 2 waypoints + closing return).
    # If you don't have it yet: copy valhalla_response_sample.json and
    # duplicate its single leg into a two-leg array.
    monkeypatch.setattr("server.blueprints.api_routing.vc.call_route", fake_call_route)
    resp = client.post(f"/api/routes/{rid}/generate")
    assert resp.status_code == 200
    assert captured["round_trip"] is True
```

Before running — check that `tests/fixtures/valhalla_response_sample_round_trip.json` exists; if not, create it:

```bash
cp tests/fixtures/valhalla_response_sample.json tests/fixtures/valhalla_response_sample_round_trip.json
python - <<'PY'
import json
with open("tests/fixtures/valhalla_response_sample_round_trip.json") as f:
    sample = json.load(f)
legs = sample["trip"]["legs"]
# Duplicate the one leg so Valhalla-round-trip mode returns 2 legs.
sample["trip"]["legs"] = legs + [dict(legs[0])]
with open("tests/fixtures/valhalla_response_sample_round_trip.json", "w") as f:
    json.dump(sample, f)
PY
```

- [ ] **Step 2: Run — confirm failure.**

```bash
pytest tests/test_api_routing.py::test_generate_uses_resolved_costing_options -v
```

Expected: `captured["costing_options"]` is `{}` — the assert fails.

- [ ] **Step 3: Replace the hard-coded block.** In `server/blueprints/api_routing.py::generate_route`, find:

```python
    opts = wp_model.get_or_create_options(route_id)
    profile = opts["profile"]

    try:
        response = vc.call_route(
            waypoints=[(w["lat"], w["lon"]) for w in wps],
            profile=profile,
            costing_options={},  # M3 wires the full costing options
            round_trip=bool(opts.get("round_trip")),
            kinds=[w.get("kind") or "stop" for w in wps],
        )
```

Replace with:

```python
    opts = wp_model.get_or_create_options(route_id)
    # Resolve the preset → (profile, costing_options). If the user has
    # custom overrides persisted under costing_options and the preset is
    # 'custom', we use those verbatim. Otherwise we take the preset's
    # defaults and merge any persisted overrides on top (explicit user
    # edits win over preset defaults).
    preset_name = opts.get("costing_preset") or "road"
    resolved = presets.resolve(preset_name)
    # D1: preset-resolved profile takes precedence (hike → pedestrian,
    # drive → auto) unless the user has explicitly overridden profile
    # (opts['profile'] is never NULL thanks to the schema default).
    profile = opts.get("profile") or resolved["profile"]
    costing_options = dict(resolved["costing_options"])
    persisted = opts.get("costing_options")
    if persisted:
        try:
            override = _json.loads(persisted)
            if isinstance(override, dict):
                costing_options.update(override)
        except (TypeError, ValueError):
            pass  # corrupted JSON — ignore and use preset defaults.

    try:
        response = vc.call_route(
            waypoints=[(w["lat"], w["lon"]) for w in wps],
            profile=profile,
            costing_options=costing_options,
            round_trip=bool(opts.get("round_trip")),
            kinds=[w.get("kind") or "stop" for w in wps],
        )
```

- [ ] **Step 4: Run — confirm pass.**

```bash
pytest tests/test_api_routing.py -v
```

Expected: all green. Watch for a regression — the existing tests pre-date this change and may have asserted on `costing_options={}`. If so, update them to allow the new preset-resolved dict.

- [ ] **Step 5: Commit.**

```bash
git add server/blueprints/api_routing.py tests/test_api_routing.py tests/fixtures/valhalla_response_sample_round_trip.json
git commit -m "feat(routing): generate_route resolves preset → costing_options (M3a)"
```

---

### Task M3a-6: `linked_to_previous` forward-compat in API layer (no DB change yet)

**Files:**
- Modify: `server/blueprints/api_waypoints.py`
- Modify: `server/models/waypoints.py`
- Modify: `tests/test_api_waypoints.py`

We extend the API's accepted-fields set now so M3a's line-drag-inserted waypoints can already ship with `linked_to_previous=1`, but the column doesn't yet exist — the runtime migration arrives in M3b-1. The API accepts and silently-discards the field in M3a; the test proves the silent-discard shape. In M3b-1 the same payloads will start being persisted without any frontend change.

Actually — simpler — gate this on column presence. If the column doesn't exist, the API returns a 400. That makes M3b-1 an explicit unlock without dead code in the request path. The task order stays: M3a-6 is just a frontend-prep stub that writes nothing.

- [ ] **Step 1: Skip implementation — leave API unchanged in M3a.**

  The corresponding change to `api_waypoints.py` happens in M3b-2 (right after the migration runs). This task exists in the plan only to remind the executor: **do not** try to wire `linked_to_previous` in M3a — the column isn't there yet.

No code, no test, no commit. Mark the checkbox and move on.

---

### Task M3a-7: Frontend — routing presets API client + options client

**Files:**
- Modify: `src/js/shared/route-api.js`

- [ ] **Step 1:** Append two new functions to `src/js/shared/route-api.js`:

```javascript
export function getRoutingPresets() {
  return json('GET', '/api/routing-presets');
}

export function patchRouteOptions(routeId, patch) {
  return json('PATCH', `/api/routes/${routeId}/options`, patch);
}
```

- [ ] **Step 2:** No unit test at this layer — it's a thin wrapper. Exercised by M3a-11's Playwright suite.

- [ ] **Step 3:** Commit.

```bash
git add src/js/shared/route-api.js
git commit -m "feat(client): route-api exports presets + options helpers (M3a)"
```

---

### Task M3a-8: Frontend — preset dropdown, custom panel, round-trip, max-grad-warn UI

**Files:**
- Modify: `server/templates/create.html`
- Modify: `src/css/create.css`
- Modify: `src/js/create/app.js`

The toolbar currently has a disabled profile dropdown and a disabled Optimise button. We replace the profile dropdown with a preset dropdown (population from the API), add a collapsible custom-costing panel below it, a round-trip checkbox, and a max-gradient-warn number input.

- [ ] **Step 1: Edit `server/templates/create.html`.** Replace the block `<select id="route-profile" disabled title="Profile selection ships in M3">...</select>` and the surrounding toolbar with:

```html
<!-- Preset dropdown — replaces the M1 disabled profile picker. -->
<label for="route-preset" style="margin-right:4px;">Preset:</label>
<select id="route-preset" title="Routing preset — controls profile, surface preference, hill tolerance">
  <option value="">loading…</option>
</select>
<button id="btn-toggle-custom" type="button" title="Custom costing overrides">⚙</button>

<!-- Round-trip toggle. -->
<label for="route-round-trip" style="margin-left:8px;">
  <input type="checkbox" id="route-round-trip"> Round trip
</label>

<!-- Max-gradient warning threshold (M3c uses this). -->
<label for="route-max-grad" style="margin-left:8px;" title="Flag legs whose smoothed gradient exceeds this percent">
  Warn &gt;
  <input type="number" id="route-max-grad" min="0" max="30" step="0.5" style="width:4em;">
  %
</label>
```

And keep the existing `#btn-optimise` (remains disabled until M3b-8 enables it). Update its tooltip to point at M3b rather than M3 generically:

```html
<button id="btn-optimise" type="button" disabled title="Optimisation wired in M3b — pin stops via the sidebar checkboxes to lock order.">Optimise</button>
```

Add the custom panel DOM immediately after `#create-header` (still inside `{% block content %}`):

```html
<div id="custom-costing-panel" style="display:none;">
  <strong>Custom costing</strong>
  <label>Roads <input type="range" id="cc-use-roads" min="0" max="1" step="0.05"></label>
  <label>Hills <input type="range" id="cc-use-hills" min="0" max="1" step="0.05"></label>
  <label>Avoid bad surfaces <input type="range" id="cc-avoid-surfaces" min="0" max="1" step="0.05"></label>
  <label>Bicycle type
    <select id="cc-bicycle-type">
      <option value="">(preset)</option>
      <option value="Road">Road</option>
      <option value="Hybrid">Hybrid</option>
      <option value="Mountain">Mountain</option>
      <option value="Cross">Cross</option>
    </select>
  </label>
</div>
```

- [ ] **Step 2: Style in `src/css/create.css`.** Append:

```css
#custom-costing-panel {
  background: #222;
  border-top: 1px solid #444;
  padding: 6px 12px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 0.85em;
  color: #ddd;
}
#custom-costing-panel label {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}
#custom-costing-panel input[type="range"] {
  width: 80px;
}
```

- [ ] **Step 3: Wire in `src/js/create/app.js`.** Near the other `setStatus` / UI-init helpers (find the block labelled "init" or the one registering the save/generate handlers), add:

```javascript
// -------------------- options UI (M3a) --------------------

async function initOptionsUI(state) {
  // Populate preset dropdown from /api/routing-presets.
  const presetSelect = document.getElementById('route-preset');
  try {
    const presets = await api.getRoutingPresets();
    presetSelect.innerHTML = presets.map(
      p => `<option value="${p.name}">${p.name}</option>`,
    ).join('');
  } catch (err) {
    console.error('failed to load presets', err);
    presetSelect.innerHTML = '<option value="road">road</option>';
  }

  // Fetch current options once — set UI state.
  // (We don't have a GET /options endpoint; options come back on the
  // initial route fetch OR we rely on the PATCH response. For M3a we
  // default-populate from 'road' and let persistence flow one-way.)
  presetSelect.value = state.currentPreset || 'road';

  // Change handlers — every mutation calls patchRouteOptions.
  presetSelect.addEventListener('change', async () => {
    await api.patchRouteOptions(state.routeId, {
      costing_preset: presetSelect.value,
    });
    state.currentPreset = presetSelect.value;
    // Show the custom panel whenever the user selects 'custom'.
    document.getElementById('custom-costing-panel').style.display =
      presetSelect.value === 'custom' ? 'flex' : 'none';
    markNeedsRegen(state);
  });

  document.getElementById('btn-toggle-custom').addEventListener('click', () => {
    const panel = document.getElementById('custom-costing-panel');
    panel.style.display = panel.style.display === 'none' ? 'flex' : 'none';
  });

  // Round-trip.
  const rtCb = document.getElementById('route-round-trip');
  rtCb.addEventListener('change', async () => {
    await api.patchRouteOptions(state.routeId, { round_trip: rtCb.checked });
    markNeedsRegen(state);
  });

  // Max-grad-warn — debounce writes on 'change' rather than 'input' to
  // avoid one PATCH per keystroke.
  const mgInput = document.getElementById('route-max-grad');
  mgInput.addEventListener('change', async () => {
    const v = mgInput.value === '' ? null : Number(mgInput.value);
    await api.patchRouteOptions(state.routeId, { max_gradient_warn: v });
    // Does NOT invalidate legs — M3c's post-processor re-runs on next
    // generate only. Spec line 279 is explicit about this.
  });

  // Custom panel sliders → flip preset to 'custom' + persist options.
  const sliders = ['cc-use-roads', 'cc-use-hills', 'cc-avoid-surfaces', 'cc-bicycle-type'];
  sliders.forEach(id => {
    const el = document.getElementById(id);
    el.addEventListener('change', async () => {
      const opts = {};
      const ur = document.getElementById('cc-use-roads').value;
      const uh = document.getElementById('cc-use-hills').value;
      const as = document.getElementById('cc-avoid-surfaces').value;
      const bt = document.getElementById('cc-bicycle-type').value;
      if (ur !== '') opts.use_roads = Number(ur);
      if (uh !== '') opts.use_hills = Number(uh);
      if (as !== '') opts.avoid_bad_surfaces = Number(as);
      if (bt) opts.bicycle_type = bt;
      presetSelect.value = 'custom';
      state.currentPreset = 'custom';
      await api.patchRouteOptions(state.routeId, {
        costing_preset: 'custom',
        costing_options: opts,
      });
      markNeedsRegen(state);
    });
  });
}

function markNeedsRegen(state) {
  // Light-touch signal: flip the generate button variant if present.
  const gc = document.getElementById('generate-control');
  if (gc) gc.dataset.variant = 'ready';
  setStatus('Options changed — regenerate', 'ready');
}
```

Call `initOptionsUI(state)` from the `bootstrap` / `init` function near where the editor is mounted. Grep for `mountWaypointEditor` in `app.js` to find the right spot.

- [ ] **Step 4: Rebuild.**

```bash
npm run build
```

- [ ] **Step 5: Manual smoke.** Start dev server (`./dev.sh --env-file .env.development`), open `/create`, dev-tools Network tab. Change the preset → observe `PATCH /api/routes/<id>/options`. Tick round-trip → another PATCH. Type a number in `max grad warn` and blur → another PATCH.

- [ ] **Step 6: Commit.**

```bash
git add server/templates/create.html src/css/create.css src/js/create/app.js
git commit -m "feat(create): preset + custom costing + round-trip + max-grad-warn UI (M3a)"
```

---

### Task M3a-9: Frontend — pin start/end per waypoint

**Files:**
- Modify: `src/js/shared/waypoint-editor.js`
- Modify: `src/js/create/app.js`
- Modify: `src/css/waypoint-editor.css`

Each sidebar row grows a small "pin as Start" / "pin as End" checkbox pair visible on hover. The row already renders a `wpe-badge` for the current `pin_role`. `update_waypoint` already accepts `pin_role` and the NULLABLE set permits clearing it.

- [ ] **Step 1: Render the controls.** In `src/js/shared/waypoint-editor.js::render()`, replace the `li.innerHTML = ...` block with:

```javascript
li.innerHTML = `
  <span class="wpe-handle" title="Drag to reorder">⋮⋮</span>
  <span class="wpe-icon wpe-icon-${w.kind}">${w.kind === 'stop' ? visitN : `<span>${visitN}</span>`}</span>
  <div class="wpe-body">
    <div class="wpe-name">${escape(w.name)}${w.pin_role ? ` <span class="wpe-badge">${w.pin_role === 'start' ? 'Start' : 'End'}</span>` : ''}</div>
    <div class="wpe-sub">${escape(w.address || (w.lat != null ? `${w.lat.toFixed(4)}, ${w.lon.toFixed(4)}` : ''))}</div>
    <div class="wpe-pin-controls">
      <label title="Pin as route start">
        <input type="checkbox" class="wpe-pin-start" ${w.pin_role === 'start' ? 'checked' : ''}> S
      </label>
      <label title="Pin as route end">
        <input type="checkbox" class="wpe-pin-end" ${w.pin_role === 'end' ? 'checked' : ''}> E
      </label>
      <button class="wpe-include-toggle" type="button"
              title="${w.included === 0 ? 'Include in route' : 'Exclude from route'}">
        ${w.included === 0 ? '◌' : '●'}
      </button>
    </div>
  </div>
  <button class="wpe-remove" title="Remove" type="button">✕</button>
`;

li.querySelector('.wpe-remove').addEventListener('click', (e) => {
  e.stopPropagation();
  if (handlers.onRemove) handlers.onRemove(w.id);
});
li.querySelector('.wpe-pin-start').addEventListener('change', (e) => {
  e.stopPropagation();
  if (handlers.onUpdate) {
    handlers.onUpdate(w.id, { pin_role: e.target.checked ? 'start' : null });
  }
});
li.querySelector('.wpe-pin-end').addEventListener('change', (e) => {
  e.stopPropagation();
  if (handlers.onUpdate) {
    handlers.onUpdate(w.id, { pin_role: e.target.checked ? 'end' : null });
  }
});
li.querySelector('.wpe-include-toggle').addEventListener('click', (e) => {
  e.stopPropagation();
  if (handlers.onUpdate) {
    handlers.onUpdate(w.id, { included: w.included === 0 ? 1 : 0 });
  }
});
```

- [ ] **Step 2: Wire `onUpdate` in `src/js/create/app.js`.** Find the `mountWaypointEditor(container, { onReorder: ..., onRemove: ... })` call and add/extend:

```javascript
const editor = mountWaypointEditor(editorEl, {
  onReorder: async (orderedIds) => { /* ... existing ... */ },
  onRemove: async (wptId) => { /* ... existing ... */ },
  onUpdate: async (wptId, patch) => {
    // pin_role mutual-exclusion: if user pinned another as start, clear
    // the old one before the server sees both set. Cheap to do
    // client-side first; the UI is more responsive.
    if (patch.pin_role === 'start' || patch.pin_role === 'end') {
      const role = patch.pin_role;
      const current = state.waypoints.find(w => w.pin_role === role && w.id !== wptId);
      if (current) {
        await api.patchWaypoint(state.routeId, current.id, { pin_role: null });
      }
    }
    await api.patchWaypoint(state.routeId, wptId, patch);
    await onWaypointsChanged(state, editor);
  },
});
```

- [ ] **Step 3: CSS for the new controls.** Append to `src/css/waypoint-editor.css`:

```css
.wpe-pin-controls {
  display: flex;
  gap: 8px;
  margin-top: 2px;
  opacity: 0.5;
  transition: opacity 150ms;
  font-size: 0.8em;
}
.wpe-item:hover .wpe-pin-controls,
.wpe-item .wpe-pin-controls:has(input:checked) {
  opacity: 1;
}
.wpe-pin-controls label {
  cursor: pointer;
}
.wpe-include-toggle {
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 0 4px;
  font-size: 1em;
  color: inherit;
}
.wpe-excluded {
  opacity: 0.45;
  text-decoration: line-through wavy #c77;
}
```

- [ ] **Step 4: Rebuild + smoke.**

```bash
npm run build
```

Smoke: drop 3 waypoints, tick "S" on the first — it gains a "Start" badge, the others stay unpinned. Tick "S" on a different one — the first loses its badge. Tick "E" on the last. Click the ● on the middle one — it dims + line-throughs, and the eye-icon flips to ◌.

- [ ] **Step 5: Commit.**

```bash
git add src/js/shared/waypoint-editor.js src/js/create/app.js src/css/waypoint-editor.css
git commit -m "feat(create): per-waypoint pin start/end + include/exclude toggle (M3a)"
```

---

### Task M3a-10: Frontend — right-click Include/Exclude in context menu

**Files:**
- Modify: `src/js/create/app.js`

The right-click `openPinContextMenu` (lines ~254–307) already has an `Exclude from route` / `Include in route` entry. Verify it works against the include toggle added in M3a-9 — the state should be shared (reading `w.included`).

- [ ] **Step 1: Read the existing handler.**

```bash
grep -n "toggle-include\|w.included" src/js/create/app.js
```

Expected: two hits — the menu build (line ~262) and the handler (line ~300). No change needed to the menu itself.

- [ ] **Step 2: Smoke-test interaction with Task M3a-9's row toggle.** Dim a waypoint via the sidebar ●→◌ toggle; right-click its marker on the map → the menu should say **"Include in route"**. Click it → the sidebar row un-dims.

- [ ] **Step 3:** No commit — this task is a verification checkbox with no code.

---

### Task M3a-11: Playwright UI tests for options

**Files:**
- Create: `tests/test_ui_options.py`

- [ ] **Step 1: Write the test suite.**

```python
"""Playwright tests for M3a options UX."""

from playwright.sync_api import expect


def _click_map_at(page, selector, fx, fy):
    """Click at (fraction-x, fraction-y) of the map element bounds."""
    box = page.locator(selector).bounding_box()
    page.mouse.click(box["x"] + box["width"] * fx, box["y"] + box["height"] * fy)


def test_preset_dropdown_is_populated(page, server_url):
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    page.wait_for_function("() => new URL(location.href).searchParams.get('route_id') !== null")
    expect(page.locator("#route-preset option")).to_have_count(6, timeout=3000)
    assert page.locator("#route-preset option").first.get_attribute("value") == "road"


def test_change_preset_patches_options(page, server_url):
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    page.wait_for_function("() => new URL(location.href).searchParams.get('route_id') !== null")
    # Capture the PATCH payload.
    patches = []
    page.on("request", lambda req: patches.append((req.method, req.url, req.post_data))
            if "/options" in req.url else None)
    page.locator("#route-preset").select_option("gravel-mtb")
    page.wait_for_timeout(500)
    assert any("gravel-mtb" in (d or "") for _, _, d in patches)


def test_round_trip_toggle_patches_options(page, server_url):
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    page.wait_for_function("() => new URL(location.href).searchParams.get('route_id') !== null")
    patches = []
    page.on("request", lambda req: patches.append(req.post_data or "")
            if "/options" in req.url else None)
    page.locator("#route-round-trip").check()
    page.wait_for_timeout(500)
    assert any("round_trip" in p and "true" in p for p in patches)


def test_pin_start_via_sidebar_checkbox(page, server_url):
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    page.wait_for_function("() => new URL(location.href).searchParams.get('route_id') !== null")
    _click_map_at(page, "#map", 0.3, 0.4)
    _click_map_at(page, "#map", 0.6, 0.4)
    page.wait_for_function("() => document.querySelectorAll('.wpe-item').length === 2", timeout=3000)
    # Hover the first row to reveal controls, then tick the 'S' checkbox.
    first = page.locator(".wpe-item").first
    first.hover()
    first.locator(".wpe-pin-start").check()
    expect(first.locator(".wpe-badge")).to_have_text("Start", timeout=3000)


def test_sidebar_exclude_dims_row(page, server_url):
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    page.wait_for_function("() => new URL(location.href).searchParams.get('route_id') !== null")
    _click_map_at(page, "#map", 0.3, 0.4)
    _click_map_at(page, "#map", 0.6, 0.4)
    page.wait_for_function("() => document.querySelectorAll('.wpe-item').length === 2", timeout=3000)
    row = page.locator(".wpe-item").first
    row.hover()
    row.locator(".wpe-include-toggle").click()
    expect(row).to_have_class(compile_re(r".*wpe-excluded.*"), timeout=3000)


def test_custom_panel_opens_on_preset_custom(page, server_url):
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    page.wait_for_function("() => new URL(location.href).searchParams.get('route_id') !== null")
    page.locator("#route-preset").select_option("custom")
    expect(page.locator("#custom-costing-panel")).to_be_visible(timeout=1500)


def compile_re(s):
    import re
    return re.compile(s)
```

- [ ] **Step 2: Run the suite.**

```bash
source .venv/bin/activate
pytest tests/test_ui_options.py -v
```

Expected: 6 passed. If any flake on timing, bump the `timeout` kwarg.

- [ ] **Step 3: Commit.**

```bash
git add tests/test_ui_options.py
git commit -m "test(ui): Playwright suite for M3a options UX"
```

---

### Task M3a-12: M3a close-out — manual smoke

**Files:** none (sign-off).

- [ ] **Step 1:** Start the dev server.

```bash
./dev.sh --env-file .env.development
```

- [ ] **Step 2: Manual smoke test.**

1. `/create` — drop 3 stops and 2 waypoints.
2. Toolbar: change preset to `gravel-mtb` → network shows a PATCH. Hit Generate. Confirm the returned polyline.
3. Change preset back to `road` → Generate again. Confirm the polyline differs (fewer unpaved sections on the road preset).
4. Tick round-trip → Generate. Confirm the returned polyline closes back to the first waypoint (leg_count = N, not N-1).
5. Pin the first stop as Start via the sidebar "S" checkbox → a second click elsewhere's "S" transfers the badge.
6. Right-click a map pin → "Exclude from route" → sidebar row dims, map marker stays but Generate skips it.
7. Click ⚙ next to the preset — custom panel opens. Drag `use_hills` to 0.95 → preset snaps to `custom`, the next Generate gets that value.

- [ ] **Step 3:** If any step fails, return to the relevant sub-task. Otherwise:

```bash
git log --oneline feature/route-creation ^main | grep M3a
```

Confirm all M3a commits are present.

No extra commit — the verification outcome is captured in the M3 close-out at the end of the plan.

---

# Phase M3b — Optimiser + linked-to-previous

**Ships the full 2-opt optimiser respecting pins and linked waypoint groups, plus the column + right-click unlink/re-link UX.** After M3b commits, the user can hit "Optimise" on a set of stops and the order reshuffles to a shorter tour while respecting any start/end pins and any linked-to-previous waypoints that must ride with their stop.

## File structure — M3b

**Create:**
- `server/routing/optimiser.py` — pure-Python grouping + NN + 2-opt.
- `tests/test_optimiser.py` — pure-function tests.
- `tests/test_api_optimise.py` — endpoint test.

**Modify:**
- `server/models/__init__.py` — extend `_apply_runtime_migrations` with `linked_to_previous`.
- `server/models/waypoints.py` — add `linked_to_previous` to `update_waypoint`'s allowed set + `append_waypoint` / `insert_waypoint_at` signatures.
- `server/blueprints/api_waypoints.py` — POST/PATCH accept `linked_to_previous`.
- `server/blueprints/api_routing.py` — add `POST /api/routes/<id>/optimise`.
- `src/js/shared/route-api.js` — add `optimiseRoute(routeId)`.
- `src/js/create/app.js` — right-click "Unlink / Re-link" entries; enable Optimise button; show chain-icon on linked rows.
- `src/js/shared/waypoint-editor.js` — render chain-icon indicator for linked rows.
- `tests/test_ui_options.py` — append optimiser + link tests.
- `tests/test_api_waypoints.py` — extend with `linked_to_previous` cases.
- `tests/test_models_waypoints.py` — extend with link default + update cases.

---

### Task M3b-1: Runtime migration — add `linked_to_previous`

**Files:**
- Modify: `server/models/__init__.py`
- Modify: `tests/test_models_waypoints.py`

- [ ] **Step 1: Write failing test.** Append to `tests/test_models_waypoints.py`:

```python
def test_linked_to_previous_column_exists(app):
    with app.app_context():
        db = get_db()
        cols = {r[1] for r in db.execute("PRAGMA table_info(route_waypoints)").fetchall()}
        assert "linked_to_previous" in cols


def test_linked_to_previous_defaults_to_1(app):
    with app.app_context():
        from server.models import waypoints as wp_model
        from server.models.categories import ensure_default_category
        from server.models.routes import create_route
        user_id = "anonymous"
        cat = ensure_default_category(user_id)
        r = create_route(user_id=user_id, category_id=cat["id"],
                         filename="x.gpx", storage_name="x", title="X")
        w = wp_model.append_waypoint(r["id"], name="A", lat=0, lon=0, kind="waypoint")
        assert w["linked_to_previous"] == 1
```

- [ ] **Step 2: Run — confirm failure.**

```bash
pytest tests/test_models_waypoints.py -k linked -v
```

Expected: 2 failures (KeyError or assert).

- [ ] **Step 3: Extend the runtime migration.** Edit `server/models/__init__.py::_apply_runtime_migrations`:

```python
def _apply_runtime_migrations(db):
    """Additive, idempotent column-level migrations for existing deployments
    where a plain CREATE TABLE IF NOT EXISTS wouldn't pick up new columns."""
    migrations = [
        ("route_waypoints", "arrival_time", "TEXT"),
        # M3b: every waypoint rides with the previous one through the
        # optimiser by default. Stops start new groups irrespective of
        # this flag, so DEFAULT 1 is safe across kinds. See plan D2.
        ("route_waypoints", "linked_to_previous", "INTEGER NOT NULL DEFAULT 1"),
    ]
    for table, column, coltype in migrations:
        cols = {r[1] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
```

- [ ] **Step 4: Run — confirm pass.**

```bash
pytest tests/test_models_waypoints.py -v
```

Expected: all green.

- [ ] **Step 5: Regression — ensure existing tests survive a DB with the new column.**

```bash
pytest tests/ --ignore=tests/test_ui_analysis.py --ignore=tests/test_ui_library.py --ignore=tests/test_ui_create.py --ignore=tests/test_ui_options.py --ignore=tests/test_ui_edit_panel.py -q
```

Expected: all green.

- [ ] **Step 6: Commit.**

```bash
git add server/models/__init__.py tests/test_models_waypoints.py
git commit -m "feat(schema): add route_waypoints.linked_to_previous (M3b)"
```

---

### Task M3b-2: Model + API accept `linked_to_previous`

**Files:**
- Modify: `server/models/waypoints.py`
- Modify: `server/blueprints/api_waypoints.py`
- Modify: `tests/test_api_waypoints.py`

- [ ] **Step 1: Write failing tests.** Append to `tests/test_api_waypoints.py`:

```python
def test_post_waypoint_accepts_linked_to_previous(client, app):
    rid = client.post("/api/routes", json={"title": "L"},
                      content_type="application/json").get_json()["id"]
    resp = client.post(f"/api/routes/{rid}/waypoints", json={
        "name": "W", "lat": 0, "lon": 0, "kind": "waypoint",
        "linked_to_previous": 0,
    })
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["linked_to_previous"] == 0


def test_patch_waypoint_can_toggle_link(client, app):
    rid = client.post("/api/routes", json={"title": "L"},
                      content_type="application/json").get_json()["id"]
    w = client.post(f"/api/routes/{rid}/waypoints", json={
        "name": "W", "lat": 0, "lon": 0, "kind": "waypoint",
    }).get_json()
    # Default was 1; flip to 0.
    resp = client.patch(f"/api/routes/{rid}/waypoints/{w['id']}",
                        json={"linked_to_previous": 0})
    assert resp.status_code == 200
    assert resp.get_json()["linked_to_previous"] == 0
```

- [ ] **Step 2: Run — confirm failure.**

```bash
pytest tests/test_api_waypoints.py -k linked -v
```

- [ ] **Step 3: Implement in model.** Edit `server/models/waypoints.py`:

In `append_waypoint`, add `linked_to_previous=1` to the signature and to the INSERT column list + VALUES tuple:

```python
def append_waypoint(route_id, *, name, lat, lon, kind,
                    address=None, description=None,
                    included=1, pin_role=None, dwell_minutes=0,
                    linked_to_previous=1):
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
            included, pin_role, dwell_minutes, description, linked_to_previous
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (route_id, position, kind, name, address, lat, lon,
         included, pin_role, dwell_minutes, description, linked_to_previous),
    )
    db.commit()
    return get_waypoint(cur.lastrowid, route_id)
```

Do the same for `insert_waypoint_at` — add the kwarg, extend the column list + VALUES.

In `update_waypoint`, extend the allowed set:

```python
allowed = {"name", "address", "kind", "lat", "lon",
           "included", "pin_role", "dwell_minutes", "description",
           "arrival_time", "linked_to_previous"}
```

- [ ] **Step 4: Implement in API.** Edit `server/blueprints/api_waypoints.py::append_waypoint`:

```python
common = dict(
    name=data.get("name") or "Waypoint",
    lat=data.get("lat"),
    lon=data.get("lon"),
    kind=kind,
    address=data.get("address"),
    description=data.get("description"),
    dwell_minutes=int(data.get("dwell_minutes") or 0),
    pin_role=data.get("pin_role"),
)
if "linked_to_previous" in data:
    common["linked_to_previous"] = 1 if data["linked_to_previous"] else 0
```

`patch_waypoint` already passes `**data` to `update_waypoint` via the model — the extended allowed-set above is sufficient. But defensively coerce to int:

```python
# Inside patch_waypoint, before calling update_waypoint:
if "linked_to_previous" in data:
    data["linked_to_previous"] = 1 if data["linked_to_previous"] else 0
```

- [ ] **Step 5: Run — confirm pass.**

```bash
pytest tests/test_api_waypoints.py -v
```

Expected: all green.

- [ ] **Step 6: Commit.**

```bash
git add server/models/waypoints.py server/blueprints/api_waypoints.py tests/test_api_waypoints.py
git commit -m "feat(api): waypoint POST/PATCH accept linked_to_previous (M3b)"
```

---

### Task M3b-3: Pure-Python optimiser — tests first

**Files:**
- Create: `tests/test_optimiser.py`

Write ALL the tests first. They'll fail with ImportError. The implementation in M3b-4 clears them.

- [ ] **Step 1: Create `tests/test_optimiser.py`.**

```python
"""Tests for the pure-Python optimiser (M3b).

The optimiser is stateless and consumes plain dicts — no Flask, no DB.
Inputs are a list of waypoint dicts (the schema shape) and an optional
cost matrix; outputs are a list of waypoint ids in the optimised order.
Grouping: every stop starts a new group, followed by any consecutive
waypoints with linked_to_previous=1 (stops end groups; also stops never
carry a meaningful linked_to_previous — see plan D2). 2-opt swaps
groups wholesale, never reaching inside one.
"""

import math

import pytest

from server.routing import optimiser


def _wp(wid, pos, kind, lat, lon, **extra):
    """Waypoint dict in the shape models/waypoints.py returns."""
    return {
        "id": wid, "position": pos, "kind": kind,
        "name": f"W{wid}", "lat": lat, "lon": lon,
        "included": 1, "pin_role": extra.get("pin_role"),
        "linked_to_previous": extra.get("linked_to_previous",
                                        1 if kind == "waypoint" else 1),
    }


def test_optimise_4_point_symmetric_square():
    # Unit square corners. The unique shortest open-tour starting at W1
    # visits in order 1 → 2 → 3 → 4, total perimeter = 3.
    # If we seed with [1,3,2,4] (crossing diagonals, total ~4.83),
    # the optimiser should unwind to a non-crossing tour.
    wps = [
        _wp(1, 0, "stop", 0, 0),
        _wp(2, 1, "stop", 0, 1),
        _wp(3, 2, "stop", 1, 1),
        _wp(4, 3, "stop", 1, 0),
    ]
    # Seed a crossing order by reordering positions:
    wps_bad = [wps[0], wps[2], wps[1], wps[3]]
    new_order = optimiser.optimise(wps_bad)
    # The result is some rotation/reflection of [1,2,3,4].
    # Cheapest open tour over the square is the perimeter, length 3.
    cost = _tour_cost(new_order, wps_bad)
    assert cost == pytest.approx(3.0, abs=1e-6)


def test_optimise_2opt_reduces_cost():
    # A deliberate crossing. Five points; NN from point 0 will produce
    # a crossing tour that 2-opt uncrosses.
    wps = [
        _wp(1, 0, "stop",  0.0, 0.0),
        _wp(2, 1, "stop",  0.0, 3.0),
        _wp(3, 2, "stop",  4.0, 3.0),
        _wp(4, 3, "stop",  4.0, 0.0),
        _wp(5, 4, "stop",  2.0, 1.5),  # inner point
    ]
    # Bad seed: zigzag order.
    wps_seed = [wps[0], wps[2], wps[4], wps[1], wps[3]]
    initial = _tour_cost([w["id"] for w in wps_seed], wps_seed)
    new_order = optimiser.optimise(wps_seed)
    improved = _tour_cost(new_order, wps_seed)
    assert improved < initial, f"2-opt did not reduce cost: {initial} → {improved}"


def test_optimise_respects_pinned_start():
    # Three far-apart points; pin #3 as start. No matter what, W3 should
    # end up at index 0 of the optimised order.
    wps = [
        _wp(1, 0, "stop", 0, 0),
        _wp(2, 1, "stop", 0, 10),
        _wp(3, 2, "stop", 10, 0, pin_role="start"),
    ]
    new_order = optimiser.optimise(wps)
    assert new_order[0] == 3


def test_optimise_respects_pinned_end():
    wps = [
        _wp(1, 0, "stop", 0, 0),
        _wp(2, 1, "stop", 0, 10, pin_role="end"),
        _wp(3, 2, "stop", 10, 0),
    ]
    new_order = optimiser.optimise(wps)
    assert new_order[-1] == 2


def test_optimise_keeps_linked_waypoint_with_its_stop():
    # Stop A → linked WP W → Stop B → Stop C. The optimiser would move B
    # before A (shorter), but W must ride with A. So the result must have
    # W immediately after A wherever A ends up.
    wps = [
        _wp(1, 0, "stop",     0, 0),                    # A (pinned start)
        _wp(2, 1, "waypoint", 0.1, 0.1, linked_to_previous=1),  # W linked to A
        _wp(3, 2, "stop",    10, 10),                   # B far away
        _wp(4, 3, "stop",     5, 5),                    # C middle
    ]
    wps[0]["pin_role"] = "start"
    new_order = optimiser.optimise(wps)
    # W must sit directly after A.
    a_idx = new_order.index(1)
    assert new_order[a_idx + 1] == 2


def test_unlinked_waypoint_is_free_to_reorder():
    # Same topology but W has linked_to_previous=0 — the optimiser may
    # place W anywhere.
    wps = [
        _wp(1, 0, "stop",     0, 0, pin_role="start"),
        _wp(2, 1, "waypoint", 0.1, 0.1, linked_to_previous=0),
        _wp(3, 2, "stop",    10, 10),
        _wp(4, 3, "stop",     5, 5),
    ]
    new_order = optimiser.optimise(wps)
    # Not asserting where W goes — only that the result is a valid tour.
    assert set(new_order) == {1, 2, 3, 4}
    assert new_order[0] == 1  # pinned start preserved


def test_cost_matrix_uses_cached_leg_when_available():
    # Two waypoints; feed a cost matrix that overrides haversine (the
    # real leg distance via cycleways happens to be 2× crow flight).
    wps = [
        _wp(1, 0, "stop", 0, 0),
        _wp(2, 1, "stop", 0, 1),
    ]
    cost_matrix = {(1, 2): 1000.0, (2, 1): 1000.0}
    # Only two points → nothing to reorder — but the cost matrix plumbing
    # is exercised in the next test; here we just confirm the optimiser
    # accepts it without erroring.
    new_order = optimiser.optimise(wps, cost_matrix=cost_matrix)
    assert set(new_order) == {1, 2}


def test_optimise_prefers_cheaper_leg_when_available():
    # Four points on a line: 1—2—3—4 (equally spaced).
    # But the cost matrix claims 1→3 is astronomically cheap and 1→2 is
    # huge. The optimiser should put 3 second.
    wps = [
        _wp(1, 0, "stop", 0, 0),
        _wp(2, 1, "stop", 0, 1),
        _wp(3, 2, "stop", 0, 2),
        _wp(4, 3, "stop", 0, 3),
    ]
    cost_matrix = {
        (1, 2): 1000.0, (2, 1): 1000.0,
        (1, 3): 1.0,    (3, 1): 1.0,
        (1, 4): 1000.0, (4, 1): 1000.0,
        (2, 3): 1000.0, (3, 2): 1000.0,
        (2, 4): 1000.0, (4, 2): 1000.0,
        (3, 4): 1.0,    (4, 3): 1.0,
    }
    new_order = optimiser.optimise(wps, cost_matrix=cost_matrix)
    # Path cost under this matrix: 1→3 (1) + 3→4 (1) + 4→2 (1000) = 1002.
    # Any path starting with 1→2 has cost ≥1000. So the optimal tour
    # must start 1→3.
    assert new_order[:2] == [1, 3]


def _tour_cost(order_or_ids, wps):
    """Sum of haversine distances along the tour."""
    # Accept either a list of ids or a list of waypoint dicts.
    if order_or_ids and isinstance(order_or_ids[0], dict):
        ids = [w["id"] for w in order_or_ids]
    else:
        ids = list(order_or_ids)
    by_id = {w["id"]: w for w in wps}
    total = 0.0
    for a, b in zip(ids, ids[1:]):
        total += _hav(by_id[a], by_id[b])
    return total


def _hav(a, b):
    R = 6371000
    from math import radians, sin, cos, atan2, sqrt
    lat1, lon1 = radians(a["lat"]), radians(a["lon"])
    lat2, lon2 = radians(b["lat"]), radians(b["lon"])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    x = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(x), sqrt(1 - x))
```

- [ ] **Step 2: Run — confirm every test fails with ImportError.**

```bash
pytest tests/test_optimiser.py -v
```

Expected: 9 collection or import errors. We implement in M3b-4.

- [ ] **Step 3: Commit — tests only (TDD).**

```bash
git add tests/test_optimiser.py
git commit -m "test(optimiser): pure-function tests for NN + 2-opt over groups (M3b)"
```

---

### Task M3b-4: Pure-Python optimiser — implementation

**Files:**
- Create: `server/routing/optimiser.py`

- [ ] **Step 1: Implement.**

```python
"""Pure-Python route optimiser: nearest-neighbour + 2-opt over groups.

Groups
------
Every stop (kind='stop') starts a new group. Any subsequent waypoint
(kind='waypoint') with linked_to_previous=1 joins the current group.
An unlinked waypoint (linked_to_previous=0) starts its own group —
this is the "free-floating shape waypoint" case that the user gets by
right-click → Unlink from previous.

The optimiser reorders groups, never the interiors. Pinned-start /
pinned-end groups are held in place.

Cost
----
A distance between two groups is the cost from the last point of the
source group to the first point of the destination group. If a
`cost_matrix` is provided (keyed by `(from_waypoint_id, to_waypoint_id)`)
it overrides the haversine fallback. Cached `route_legs` is the
source of the matrix in the production endpoint; tests can feed
synthetic matrices.
"""

from math import radians, sin, cos, atan2, sqrt


def _haversine(a_lat, a_lon, b_lat, b_lon):
    R = 6371000
    lat1, lon1 = radians(a_lat), radians(a_lon)
    lat2, lon2 = radians(b_lat), radians(b_lon)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    x = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(x), sqrt(1 - x))


def _cost(a, b, cost_matrix):
    if cost_matrix is not None:
        cached = cost_matrix.get((a["id"], b["id"]))
        if cached is not None:
            return cached
    return _haversine(a["lat"], a["lon"], b["lat"], b["lon"])


def build_groups(waypoints):
    """Chunk a waypoint list into groups per the spec.

    Rules:
      - The first waypoint always starts a group.
      - Every stop starts a new group.
      - A waypoint with linked_to_previous=0 starts a new group.
      - A waypoint with linked_to_previous=1 joins the current group.
    """
    groups = []
    current = []
    for w in waypoints:
        if not current:
            current = [w]
            continue
        if w["kind"] == "stop" or int(w.get("linked_to_previous", 1)) == 0:
            groups.append(current)
            current = [w]
        else:
            current.append(w)
    if current:
        groups.append(current)
    return groups


def _group_cost(group_a, group_b, cost_matrix):
    """Cost is last-of-A → first-of-B (+ intra-group distances are fixed)."""
    return _cost(group_a[-1], group_b[0], cost_matrix)


def _pin_constraints(groups):
    """Return (start_idx, end_idx) — indices of the groups that contain a
    pin_role='start' / 'end' waypoint, or None if absent."""
    start_idx = end_idx = None
    for i, g in enumerate(groups):
        for w in g:
            if w.get("pin_role") == "start":
                start_idx = i
            elif w.get("pin_role") == "end":
                end_idx = i
    return start_idx, end_idx


def _nearest_neighbour(groups, cost_matrix, start_idx):
    """Seed tour: greedy NN, forced to begin at start_idx."""
    unvisited = list(range(len(groups)))
    order = [start_idx]
    unvisited.remove(start_idx)
    while unvisited:
        last = order[-1]
        best = min(unvisited,
                   key=lambda j: _group_cost(groups[last], groups[j], cost_matrix))
        order.append(best)
        unvisited.remove(best)
    return order


def _tour_cost(order, groups, cost_matrix):
    total = 0.0
    for i in range(len(order) - 1):
        total += _group_cost(groups[order[i]], groups[order[i + 1]], cost_matrix)
    return total


def _two_opt(order, groups, cost_matrix, *, fixed_first=True, fixed_last=False):
    """Standard 2-opt local search. Skips the first index if pinned, and
    the last index if pinned, so pin_role invariants hold."""
    n = len(order)
    improved = True
    while improved:
        improved = False
        i_start = 1 if fixed_first else 0
        i_end = n - 2 if fixed_last else n - 1
        for i in range(i_start, i_end):
            for j in range(i + 1, n if not fixed_last else n - 1):
                # Reverse segment order[i:j+1].
                if j - i == 1:
                    continue
                new_order = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                if _tour_cost(new_order, groups, cost_matrix) + 1e-9 < \
                   _tour_cost(order, groups, cost_matrix):
                    order = new_order
                    improved = True
        # loop restarts on any improvement
    return order


def optimise(waypoints, cost_matrix=None):
    """Return the optimised ordering as a flat list of waypoint ids.

    waypoints: list of waypoint dicts ordered by current position.
    cost_matrix: optional dict {(from_id, to_id): metres}.
    """
    if not waypoints:
        return []
    # Filter to included-only for the optimisation; excluded rows keep
    # their current positions in the caller.
    included = [w for w in waypoints if w.get("included", 1)]
    if len(included) <= 1:
        return [w["id"] for w in included]

    groups = build_groups(included)
    start_idx, end_idx = _pin_constraints(groups)
    # Default: group 0 is the start (matches the M1 "first pin IS the start"
    # contract) when no pin_role='start' is set.
    if start_idx is None:
        start_idx = 0

    # Move end_idx to the final position BEFORE running NN/2-opt.
    if end_idx is not None and end_idx != len(groups) - 1:
        # swap end group with current last group
        groups = groups[:]
        groups[-1], groups[end_idx] = groups[end_idx], groups[-1]
        # start_idx may have shifted
        if start_idx == len(groups) - 1:
            start_idx = end_idx
        end_idx = len(groups) - 1

    order = _nearest_neighbour(groups, cost_matrix, start_idx)

    # If end is pinned, force it to the tail BEFORE 2-opt (NN may have
    # placed it elsewhere).
    if end_idx is not None:
        order.remove(end_idx)
        order.append(end_idx)

    order = _two_opt(
        order, groups, cost_matrix,
        fixed_first=True,
        fixed_last=end_idx is not None,
    )

    # Flatten groups in the new order → waypoint ids.
    out = []
    for gi in order:
        for w in groups[gi]:
            out.append(w["id"])
    return out
```

- [ ] **Step 2: Run.**

```bash
pytest tests/test_optimiser.py -v
```

Expected: all 9 passed. If `test_optimise_respects_pinned_end` fails with the end at the wrong index: verify the `end_idx` hoist happens *before* NN, not after.

- [ ] **Step 3: Commit.**

```bash
git add server/routing/optimiser.py
git commit -m "feat(optimiser): NN + 2-opt over groups, respecting pins (M3b)"
```

---

### Task M3b-5: `POST /api/routes/<id>/optimise` endpoint

**Files:**
- Modify: `server/blueprints/api_routing.py`
- Create: `tests/test_api_optimise.py`

- [ ] **Step 1: Write failing endpoint test.** Create `tests/test_api_optimise.py`:

```python
"""Tests for POST /api/routes/<id>/optimise (M3b)."""


def test_optimise_returns_new_order_and_persists(client, app):
    rid = client.post("/api/routes", json={"title": "Opt"},
                      content_type="application/json").get_json()["id"]
    # Crossing tour: 4 corners of a square in a bad order.
    pts = [(0, 0), (1, 1), (0, 1), (1, 0)]
    wids = []
    for i, (lat, lon) in enumerate(pts):
        w = client.post(f"/api/routes/{rid}/waypoints", json={
            "name": f"W{i}", "lat": lat, "lon": lon, "kind": "stop",
        }).get_json()
        wids.append(w["id"])

    resp = client.post(f"/api/routes/{rid}/optimise")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "new_order" in body
    assert set(body["new_order"]) == set(wids)

    # Persisted: listing now reflects the new positions.
    listed = client.get(f"/api/routes/{rid}/waypoints").get_json()
    listed_ids = [w["id"] for w in listed]
    assert listed_ids == body["new_order"]


def test_optimise_404_on_unknown_route(client):
    resp = client.post("/api/routes/99999/optimise")
    assert resp.status_code == 404


def test_optimise_requires_at_least_two_included(client, app):
    rid = client.post("/api/routes", json={"title": "Opt"},
                      content_type="application/json").get_json()["id"]
    client.post(f"/api/routes/{rid}/waypoints", json={
        "name": "W", "lat": 0, "lon": 0, "kind": "stop",
    })
    resp = client.post(f"/api/routes/{rid}/optimise")
    assert resp.status_code == 400
```

- [ ] **Step 2: Run — confirm failure.**

```bash
pytest tests/test_api_optimise.py -v
```

- [ ] **Step 3: Implement.** Append to `server/blueprints/api_routing.py`:

```python
from server.routing import optimiser


@bp.route("/routes/<int:route_id>/optimise", methods=["POST"])
def optimise_route(route_id):
    user_id = get_current_user()
    route = get_route(user_id, route_id)
    if route is None:
        return jsonify({"error": "Not found"}), 404

    wps = wp_model.list_waypoints(route_id)
    included = [w for w in wps if w.get("included", 1)]
    if len(included) < 2:
        return jsonify({"error": "at least 2 included waypoints required"}), 400

    # Build a cost matrix from cached legs — real network distance
    # beats haversine whenever we already have it.
    cost_matrix = {}
    wp_by_pos = {w["position"]: w for w in wps}
    for leg in wp_model.list_legs(route_id):
        a = wp_by_pos.get(leg["from_position"])
        b = wp_by_pos.get(leg["to_position"])
        if a is None or b is None:
            continue
        cost_matrix[(a["id"], b["id"])] = leg["distance_m"]
        cost_matrix[(b["id"], a["id"])] = leg["distance_m"]  # symmetric fallback

    new_order = optimiser.optimise(included, cost_matrix=cost_matrix or None)

    # The optimiser only reorders included rows. Excluded rows keep their
    # original positions by being spliced back in at their old spots.
    # Simplest correct approach: build the full ordered id list from the
    # included-new-order + excluded-at-original-index, then reorder.
    excluded = [w for w in wps if not w.get("included", 1)]
    # Put excluded rows at the tail in their prior order. This trades
    # off "keeping them near their old neighbours" for implementation
    # simplicity; a future iteration can preserve precise indices.
    full_order = new_order + [w["id"] for w in excluded]
    wp_model.reorder_waypoints(route_id, full_order)

    # Stamp last_optimised_at and clear it on linked_to_previous edits
    # (D5). Done here:
    wp_model.update_options(route_id, last_optimised_at=int(time.time()))

    return jsonify({"new_order": new_order}), 200
```

- [ ] **Step 4: Run.**

```bash
pytest tests/test_api_optimise.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit.**

```bash
git add server/blueprints/api_routing.py tests/test_api_optimise.py
git commit -m "feat(api): POST /api/routes/<id>/optimise (M3b)"
```

---

### Task M3b-6: Invalidate `last_optimised_at` on link-flag toggle

**Files:**
- Modify: `server/blueprints/api_waypoints.py`
- Modify: `tests/test_api_waypoints.py`

Per Decision D5: toggling `linked_to_previous` on any waypoint clears `last_optimised_at` so the next Optimise click doesn't serve stale groupings.

- [ ] **Step 1: Write failing test.** Append to `tests/test_api_waypoints.py`:

```python
def test_patching_linked_to_previous_clears_last_optimised_at(client, app):
    from server.models import waypoints as wp_model
    rid = client.post("/api/routes", json={"title": "I"},
                      content_type="application/json").get_json()["id"]
    w = client.post(f"/api/routes/{rid}/waypoints", json={
        "name": "W", "lat": 0, "lon": 0, "kind": "waypoint",
    }).get_json()
    with app.app_context():
        wp_model.update_options(rid, last_optimised_at=1234567890)
    # PATCH the link flag.
    client.patch(f"/api/routes/{rid}/waypoints/{w['id']}",
                 json={"linked_to_previous": 0})
    with app.app_context():
        opts = wp_model.get_or_create_options(rid)
    assert opts["last_optimised_at"] is None
```

- [ ] **Step 2: Run — confirm failure.**

```bash
pytest tests/test_api_waypoints.py -k last_optimised -v
```

- [ ] **Step 3: Implement.** Edit `server/blueprints/api_waypoints.py::patch_waypoint` — after the `update_waypoint` call, check if the link flag was changed:

```python
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
    if "linked_to_previous" in data:
        data["linked_to_previous"] = 1 if data["linked_to_previous"] else 0
    updated = wp_model.update_waypoint(wpt_id, route_id, **data)
    # D5: toggling the link flag invalidates the optimiser cache.
    if "linked_to_previous" in data and \
       int(data["linked_to_previous"]) != int(existing.get("linked_to_previous", 1)):
        # Need to clear — update_options filters None, so we go direct.
        from server.models import get_db
        db = get_db()
        db.execute(
            "UPDATE route_options SET last_optimised_at = NULL WHERE route_id = ?",
            (route_id,),
        )
        db.commit()
    return jsonify(updated), 200
```

Note: `wp_model.update_options` filters `None` values (line 183 in `waypoints.py`), so we clear the column via direct SQL.

- [ ] **Step 4: Run.**

```bash
pytest tests/test_api_waypoints.py -v
```

- [ ] **Step 5: Commit.**

```bash
git add server/blueprints/api_waypoints.py tests/test_api_waypoints.py
git commit -m "feat(api): toggling linked_to_previous clears last_optimised_at (M3b)"
```

---

### Task M3b-7: Frontend — route-api helper + link-indicator + Optimise button

**Files:**
- Modify: `src/js/shared/route-api.js`
- Modify: `src/js/shared/waypoint-editor.js`
- Modify: `src/js/create/app.js`

- [ ] **Step 1: Add helper.** Append to `src/js/shared/route-api.js`:

```javascript
export function optimiseRoute(routeId) {
  return json('POST', `/api/routes/${routeId}/optimise`);
}
```

- [ ] **Step 2: Render chain icon on linked rows.** In `src/js/shared/waypoint-editor.js::render()` — append a chain-icon badge next to the existing `wpe-badge` for waypoints with `linked_to_previous === 1`:

```javascript
// Inside the template string, replacing the existing wpe-name div:
<div class="wpe-name">
  ${escape(w.name)}
  ${w.pin_role ? ` <span class="wpe-badge">${w.pin_role === 'start' ? 'Start' : 'End'}</span>` : ''}
  ${w.kind === 'waypoint' && w.linked_to_previous === 1 ? ' <span class="wpe-link-badge" title="Linked to previous — optimiser keeps these adjacent">🔗</span>' : ''}
</div>
```

- [ ] **Step 3: Add the right-click menu entries.** In `src/js/create/app.js::openPinContextMenu`, update the `menu.innerHTML` build:

```javascript
const isStop = w.kind === 'stop';
const included = w.included !== 0;
const linked = w.linked_to_previous === 1;

const linkEntry = isStop
  ? ''
  : (linked
      ? '<button data-act="unlink" type="button">Unlink from previous</button>'
      : '<button data-act="relink" type="button">Re-link to previous</button>');

menu.innerHTML = `
  <div class="ctx-header">${escapeHtml(w.name || (isStop ? 'Stop' : 'Waypoint'))}</div>
  <button data-act="toggle-kind" type="button">${isStop ? 'Mark as Waypoint' : 'Mark as Stop'}</button>
  <button data-act="toggle-include" type="button">${included ? 'Exclude from route' : 'Include in route'}</button>
  ${linkEntry}
  ${isStop ? '<button data-act="edit-stop" type="button">Edit stop details…</button>' : ''}
  <div class="ctx-sep"></div>
  <button data-act="delete" type="button" class="danger">Delete</button>
`;
```

And extend the click handler:

```javascript
} else if (act === 'unlink') {
  await api.patchWaypoint(state.routeId, w.id, { linked_to_previous: 0 });
  await onWaypointsChanged(state, editor);
} else if (act === 'relink') {
  await api.patchWaypoint(state.routeId, w.id, { linked_to_previous: 1 });
  await onWaypointsChanged(state, editor);
}
```

- [ ] **Step 4: Enable the Optimise button and wire it.** In `app.js`, find the existing `btn-optimise` and replace its disabled handler with:

```javascript
// In initOptionsUI or the equivalent init block:
const optBtn = document.getElementById('btn-optimise');
optBtn.disabled = false;
optBtn.title = 'Reorder stops for shortest route (respects pins + linked waypoints)';
optBtn.addEventListener('click', async () => {
  optBtn.disabled = true;
  setStatus('Optimising…', 'busy');
  try {
    await api.optimiseRoute(state.routeId);
    await onWaypointsChanged(state, state.editor);
    setStatus('Optimised — regenerate', 'ready');
    markNeedsRegen(state);
  } catch (err) {
    setStatus('Optimise failed: ' + err.message, 'error');
  } finally {
    optBtn.disabled = false;
  }
});
```

Also update the `create.html` attribute: remove the `disabled` attribute from `#btn-optimise` (the JS still manages it at runtime):

Find:

```html
<button id="btn-optimise" type="button" disabled title="...">Optimise</button>
```

Change to:

```html
<button id="btn-optimise" type="button" title="Reorder stops for shortest route — respects pins + linked waypoints">Optimise</button>
```

- [ ] **Step 5: Line-drag inserts default to `linked_to_previous=1` already (implicit default), but make it explicit.** Find `startLineDrag`'s `insertWaypointAt` call and add the field:

```javascript
await api.insertWaypointAt(state.routeId, dragState.fromPosition + 1, {
  name: 'Waypoint', lat: snap.lat, lon: snap.lon, kind: 'waypoint',
  linked_to_previous: 1,
});
```

(The API layer defaults to 1 anyway — this is a readability improvement.)

- [ ] **Step 6: Rebuild + smoke.**

```bash
npm run build
```

Smoke: drop 3 stops + 1 waypoint. The waypoint row shows a 🔗. Right-click it → "Unlink from previous" → the 🔗 disappears. Right-click → "Re-link to previous" → back.

Click Optimise on a scrambled 5-point tour → sidebar rows rearrange.

- [ ] **Step 7: Commit.**

```bash
git add src/js/shared/route-api.js src/js/shared/waypoint-editor.js src/js/create/app.js server/templates/create.html
git commit -m "feat(create): link/unlink menu + optimise button wiring (M3b)"
```

---

### Task M3b-8: Playwright — optimiser + link UX

**Files:**
- Modify: `tests/test_ui_options.py`

- [ ] **Step 1: Append tests.**

```python
def test_optimise_button_reorders_waypoints(page, server_url):
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    page.wait_for_function("() => new URL(location.href).searchParams.get('route_id') !== null")
    # Drop 4 points in a crossing order.
    for fx, fy in [(0.3, 0.3), (0.7, 0.7), (0.3, 0.7), (0.7, 0.3)]:
        _click_map_at(page, "#map", fx, fy)
    page.wait_for_function("() => document.querySelectorAll('.wpe-item').length === 4", timeout=3000)

    initial_names = page.locator(".wpe-item .wpe-name").all_text_contents()
    page.locator("#btn-optimise").click()
    # Wait for the reorder to land.
    page.wait_for_function(
        "(initial) => {"
        "  const names = [...document.querySelectorAll('.wpe-item .wpe-name')]"
        "    .map(e => e.textContent.trim());"
        "  return JSON.stringify(names) !== JSON.stringify(initial);"
        "}",
        arg=initial_names,
        timeout=5000,
    )


def test_linked_waypoint_keeps_chain_badge(page, server_url):
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    page.wait_for_function("() => new URL(location.href).searchParams.get('route_id') !== null")
    _click_map_at(page, "#map", 0.3, 0.4)
    _click_map_at(page, "#map", 0.4, 0.4)  # second click = waypoint by default
    page.wait_for_function("() => document.querySelectorAll('.wpe-item').length === 2", timeout=3000)
    # Second row is a waypoint and should show 🔗 by default.
    expect(page.locator(".wpe-item").nth(1).locator(".wpe-link-badge")).to_be_visible(timeout=3000)


def test_unlink_from_menu_removes_chain_badge(page, server_url):
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    page.wait_for_function("() => new URL(location.href).searchParams.get('route_id') !== null")
    _click_map_at(page, "#map", 0.3, 0.4)
    _click_map_at(page, "#map", 0.4, 0.4)
    page.wait_for_function("() => document.querySelectorAll('.wpe-item').length === 2", timeout=3000)
    # Right-click on the second marker. The marker DOM is Leaflet's svg
    # pane; use the Leaflet internal API exposed through the map.
    page.evaluate("""() => {
      const markers = [...document.querySelectorAll('.leaflet-marker-icon')];
      const target = markers[markers.length - 1];
      const rect = target.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const evt = new MouseEvent('contextmenu', {
        bubbles: true, clientX: cx, clientY: cy, button: 2,
      });
      target.dispatchEvent(evt);
    }""")
    page.locator('button[data-act="unlink"]').click()
    expect(page.locator(".wpe-item").nth(1).locator(".wpe-link-badge")).to_have_count(0, timeout=3000)
```

- [ ] **Step 2: Run.**

```bash
pytest tests/test_ui_options.py -v
```

Expected: all passed (previous M3a tests + 3 new).

- [ ] **Step 3: Commit.**

```bash
git add tests/test_ui_options.py
git commit -m "test(ui): Playwright optimiser + link-flag toggles (M3b)"
```

---

### Task M3b-9: M3b close-out — manual smoke

**Files:** none.

- [ ] **Step 1:** Start dev server.

- [ ] **Step 2: Manual smoke.**

1. Create a 5-point route in scrambled order (zigzag clicks). Optimise → order changes. Generate → the new tour is shorter.
2. Add a waypoint (right-click empty map → or just click once to drop a default waypoint) between two stops. Observe 🔗 in sidebar.
3. Right-click the waypoint marker → Unlink → 🔗 disappears.
4. Pin the first stop as Start (sidebar "S"). Optimise → first stop stays at index 0.
5. Re-link the waypoint. Optimise → the waypoint is always immediately after the stop it's linked to, regardless of the tour order.
6. Toggle `linked_to_previous` via right-click on a linked waypoint → observe that `last_optimised_at` is cleared (check via `sqlite3 data/routes.db "SELECT last_optimised_at FROM route_options WHERE route_id=<id>"`).

No commit — outcome captured in the final M3 close-out.

---

# Phase M3c — Gradient-warning post-processor

**Ships server-side elevation-aware warnings for legs whose smoothed gradient crosses the user-configured `max_gradient_warn` threshold.** After M3c, a Generate over a route with a steep section and `max_gradient_warn=10` writes JSON warnings into `route_legs.warnings`; the Create page sidebar shows a ⚠️ on the affected leg's row; the map tints the over-threshold sub-segment in the steepest-band colour.

## File structure — M3c

**Create:**
- `server/route_postprocess.py` — pure Python elevation smoothing + windowed gradient + warnings generator.
- `tests/test_route_postprocess.py` — unit tests with synthetic elevation data.

**Modify:**
- `server/blueprints/api_routing.py::generate_route` — call the post-processor after `replace_legs`.
- `server/models/waypoints.py::replace_legs` — already accepts `max_grade_pct` and `warnings`; verify.
- `src/js/create/app.js` — render ⚠️ badge on sidebar rows keyed to legs; tint over-threshold sub-segments.
- `src/js/shared/waypoint-editor.js` — accept per-row `leg_warning` prop, render ⚠️.
- `src/css/create.css` — warning badge + tint overlay colour.
- `tests/test_ui_options.py` — append the M3c gradient-warning test.

---

### Task M3c-1: Verify Valhalla returns per-leg elevation

**Files:**
- Read-only probe of `tests/fixtures/valhalla_response_sample.json`; possibly regenerate.

Decision D4: confirm the exact field name Valhalla uses for per-leg elevation before writing tests against it.

- [ ] **Step 1: Inspect the fixture.**

```bash
python - <<'PY'
import json
with open("tests/fixtures/valhalla_response_sample.json") as f:
    sample = json.load(f)
leg = sample["trip"]["legs"][0]
keys = sorted(leg.keys())
print("leg top-level keys:", keys)
for k in keys:
    v = leg[k]
    if isinstance(v, (list, tuple)):
        print(f"  {k}: list[{len(v)}]")
    else:
        print(f"  {k}: {type(v).__name__}")
PY
```

- [ ] **Step 2: Check for `elevation`.** Expected key name from Valhalla with `elevation_interval: 10`: `elevation` (flat list of floats, metres).

If the fixture does **not** contain `elevation` (the M1 fixture pre-dates elevation_interval), generate a fresh one against the running local Valhalla:

```bash
curl -s http://localhost:8002/route -H 'Content-Type: application/json' -d '{
  "locations": [{"lat":-27.4,"lon":152.9,"type":"break"},{"lat":-27.5,"lon":152.8,"type":"break"}],
  "costing": "bicycle",
  "elevation_interval": 10
}' > tests/fixtures/valhalla_response_sample.json
```

- [ ] **Step 3: Confirm `elevation` is a flat list of floats.**

```bash
python - <<'PY'
import json
sample = json.load(open("tests/fixtures/valhalla_response_sample.json"))
leg = sample["trip"]["legs"][0]
assert "elevation" in leg, f"no 'elevation' in leg keys: {list(leg.keys())}"
assert all(isinstance(x, (int, float)) for x in leg["elevation"])
print("elevation samples:", len(leg["elevation"]))
print("first 5:", leg["elevation"][:5])
PY
```

- [ ] **Step 4:** If the fixture was regenerated, commit:

```bash
git add tests/fixtures/valhalla_response_sample.json
git commit -m "chore(fixture): regenerate Valhalla sample with elevation (M3c)"
```

Otherwise no commit.

---

### Task M3c-2: Post-processor module — tests first

**Files:**
- Create: `tests/test_route_postprocess.py`

- [ ] **Step 1: Write failing tests.**

```python
"""Tests for server/route_postprocess.py — gradient-warning post-processor (M3c)."""

import pytest

from server.route_postprocess import (
    scan_legs_for_warnings,
    _smooth,
    _windowed_gradient,
    _warnings_for_leg,
)


def test_smooth_flat_is_idempotent():
    flat = [100.0] * 20
    assert _smooth(flat, window=7) == pytest.approx(flat)


def test_smooth_spike_is_dampened():
    series = [100.0] * 10
    series[5] = 200.0  # outlier
    smoothed = _smooth(series, window=7)
    assert smoothed[5] < 200.0
    assert smoothed[5] > 100.0


def test_windowed_gradient_constant_slope():
    # 10 samples spaced 10 m apart rising 1 m per sample = 10% grade.
    distances_m = [i * 10.0 for i in range(10)]
    elevations = [i * 1.0 for i in range(10)]
    grads = _windowed_gradient(distances_m, elevations, gradient_dist=50.0)
    # Mid-series samples should be ~10%.
    assert grads[5] == pytest.approx(10.0, abs=0.01)


def test_warnings_empty_when_below_threshold():
    # 20 samples, 10 m spacing, rising 0.3 m per sample = 3% grade.
    ele = [i * 0.3 for i in range(20)]
    dist = [i * 10.0 for i in range(20)]
    w = _warnings_for_leg(dist, ele, max_gradient_warn=10.0)
    assert w == []


def test_warnings_picks_up_steep_run():
    # First 5 samples flat, then a steep 20%-grade climb over 100 m.
    dist = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150]
    ele  = [50, 50, 50, 50, 50, 52, 54, 56, 58, 60, 62, 64, 66, 68, 70, 72]
    w = _warnings_for_leg(dist, ele, max_gradient_warn=10.0)
    assert len(w) == 1
    # The run spans roughly 50m → 150m.
    assert w[0]["from_m"] >= 40
    assert w[0]["to_m"] <= 160
    assert w[0]["peak_grad_pct"] > 15.0  # smoothing rounds it to ~20%


def test_scan_legs_for_warnings_none_when_threshold_null():
    legs = [{
        "distance_m": 1000.0,
        "polyline": "",  # not read by the post-processor directly
        "elevation": [i * 0.1 for i in range(100)],  # ~1% grade
        "elevation_interval_m": 10.0,
    }]
    result = scan_legs_for_warnings(legs, max_gradient_warn=None)
    assert result == [{"max_grade_pct": None, "warnings": None}]


def test_scan_legs_for_warnings_returns_json_serialisable():
    import json
    legs = [{
        "distance_m": 1500.0,
        "polyline": "",
        "elevation": [10 * math_pow(1.02, i) for i in range(100)],
        "elevation_interval_m": 15.0,
    }]
    result = scan_legs_for_warnings(legs, max_gradient_warn=1.0)
    # Output must survive json.dumps (for writing to route_legs.warnings).
    for row in result:
        if row["warnings"] is not None:
            json.dumps(row["warnings"])


def math_pow(b, e):
    # Module-level import would clash in the `pytest -k` filter in some
    # test runners — inline to keep it tidy.
    import math
    return math.pow(b, e)
```

- [ ] **Step 2: Run — confirm all fail.**

```bash
pytest tests/test_route_postprocess.py -v
```

Expected: collection error (ImportError).

- [ ] **Step 3: Commit tests only.**

```bash
git add tests/test_route_postprocess.py
git commit -m "test(postprocess): failing tests for gradient-warning scanner (M3c)"
```

---

### Task M3c-3: Post-processor implementation

**Files:**
- Create: `server/route_postprocess.py`

- [ ] **Step 1: Implement.**

```python
"""Post-process Valhalla response legs: smooth elevations, compute
windowed gradient, emit warning ranges for sub-segments exceeding the
user-configured threshold.

Ported from src/js/analysis/track-processor.js (see plan Decision D3).
"""

# Smoothing and windowed-gradient params match the frontend defaults.
# Frontend persists these in localStorage per-user; the server uses the
# app-level defaults since the DB doesn't carry per-user analysis prefs.
SMOOTH_WINDOW = 7
GRADIENT_DIST = 100.0   # metres of the minimum window over which gradient is measured.


def _smooth(elevations, window):
    """Centred moving average. Mirrors track-processor.js::smoothElevations."""
    n = len(elevations)
    half = window // 2
    out = []
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n - 1, i + half)
        s = 0.0
        c = 0
        for j in range(lo, hi + 1):
            s += elevations[j]
            c += 1
        out.append(s / c)
    return out


def _windowed_gradient(distances_m, elevations_smoothed, gradient_dist=GRADIENT_DIST):
    """Gradient per-sample over the minimum `gradient_dist` window.

    For each index i, walk back until the window spans at least
    `gradient_dist` metres, then gradient = (ele_i - ele_j) / (dist_i - dist_j) * 100.
    Mirrors track-processor.js::processTrackData's gradient loop.
    """
    n = len(distances_m)
    grads = [0.0] * n
    for i in range(1, n):
        j = i - 1
        while j > 0 and (distances_m[i] - distances_m[j]) < gradient_dist:
            j -= 1
        d = distances_m[i] - distances_m[j]
        if d > 1.0:
            grads[i] = ((elevations_smoothed[i] - elevations_smoothed[j]) / d) * 100.0
        else:
            grads[i] = 0.0
    return grads


def _warnings_for_leg(distances_m, elevations, max_gradient_warn):
    """Return a list of {from_m, to_m, peak_grad_pct} for runs where the
    smoothed absolute gradient >= max_gradient_warn."""
    if max_gradient_warn is None:
        return []
    smoothed = _smooth(elevations, SMOOTH_WINDOW)
    grads = _windowed_gradient(distances_m, smoothed)
    warnings = []
    in_run = False
    run_start_m = None
    run_peak = 0.0
    for i, g in enumerate(grads):
        over = abs(g) >= max_gradient_warn
        if over and not in_run:
            in_run = True
            run_start_m = distances_m[i]
            run_peak = abs(g)
        elif over:
            if abs(g) > run_peak:
                run_peak = abs(g)
        elif in_run:
            warnings.append({
                "from_m": run_start_m,
                "to_m": distances_m[i],
                "peak_grad_pct": round(run_peak, 2),
            })
            in_run = False
    if in_run:
        warnings.append({
            "from_m": run_start_m,
            "to_m": distances_m[-1],
            "peak_grad_pct": round(run_peak, 2),
        })
    return warnings


def _max_grade_for_leg(distances_m, elevations):
    """Peak smoothed gradient across the leg (signed)."""
    if len(distances_m) < 2:
        return 0.0
    smoothed = _smooth(elevations, SMOOTH_WINDOW)
    grads = _windowed_gradient(distances_m, smoothed)
    # Return the largest absolute gradient, preserving sign.
    peak = 0.0
    for g in grads:
        if abs(g) > abs(peak):
            peak = g
    return peak


def scan_legs_for_warnings(legs, max_gradient_warn):
    """Given parsed Valhalla legs (with elevation + elevation_interval),
    return a list of {max_grade_pct, warnings} parallel to `legs`.

    Each input leg must have:
      - elevation: list[float] of metre samples
      - elevation_interval_m: float — spacing between samples
      - distance_m: float — total leg length (used as a sanity check)
    """
    out = []
    for leg in legs:
        ele = leg.get("elevation") or []
        step = leg.get("elevation_interval_m") or 10.0
        if not ele:
            out.append({"max_grade_pct": None, "warnings": None})
            continue
        distances = [i * step for i in range(len(ele))]
        peak = _max_grade_for_leg(distances, ele)
        warnings = _warnings_for_leg(distances, ele, max_gradient_warn)
        out.append({
            "max_grade_pct": round(peak, 2),
            "warnings": warnings if warnings else None,
        })
    return out
```

- [ ] **Step 2: Run.**

```bash
pytest tests/test_route_postprocess.py -v
```

Expected: 7 passed.

- [ ] **Step 3: Commit.**

```bash
git add server/route_postprocess.py
git commit -m "feat(postprocess): elevation smoothing + gradient warnings (M3c)"
```

---

### Task M3c-4: Wire the post-processor into `generate_route`

**Files:**
- Modify: `server/routing/valhalla_client.py::parse_legs` — extend to also return `elevation` + `elevation_interval_m`.
- Modify: `server/blueprints/api_routing.py` — call `scan_legs_for_warnings` after building `legs_rows`.
- Modify: `tests/test_routing_valhalla_client.py`.
- Modify: `tests/test_api_routing.py`.

- [ ] **Step 1: Test that `parse_legs` surfaces elevation.** Append to `tests/test_routing_valhalla_client.py`:

```python
import json


def test_parse_legs_includes_elevation():
    with open("tests/fixtures/valhalla_response_sample.json") as f:
        response = json.load(f)
    from server.routing.valhalla_client import parse_legs
    parsed = parse_legs(response)
    assert parsed
    leg = parsed[0]
    assert "elevation" in leg
    assert isinstance(leg["elevation"], list)
    assert "elevation_interval_m" in leg
```

- [ ] **Step 2: Update `parse_legs`.** Edit `server/routing/valhalla_client.py::parse_legs`:

```python
def parse_legs(response):
    """Convert a Valhalla response into a list of leg dicts ready for
    route_legs insertion. The caller assigns from_position/to_position.

    When the request had `elevation_interval` set, every leg carries:
      - elevation: flat list of metre samples along the shape
      - elevation_interval_m: spacing between samples (metres)
    """
    trip = response.get("trip") or {}
    legs = trip.get("legs") or []
    # elevation_interval lives at the request top level (Valhalla echoes
    # it back on the response) — fall back to a hardcoded 10.0 (matching
    # build_request_body) if absent.
    elevation_interval = response.get("elevation_interval", 10.0)
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
            "elevation": leg.get("elevation") or [],
            "elevation_interval_m": float(elevation_interval),
        })
    return out
```

- [ ] **Step 3: Wire in `generate_route`.** In `server/blueprints/api_routing.py`, after the `legs_rows` construction and `replace_legs` call, add the post-processing pass:

```python
from server.route_postprocess import scan_legs_for_warnings
import json as _json


# ... inside generate_route, AFTER parsing legs and BEFORE replace_legs:

# Post-process: elevation-aware warnings (M3c).
opts_threshold = opts.get("max_gradient_warn")
# Build the [{elevation, elevation_interval_m, distance_m}] list parallel
# to parsed_legs; the scanner reads these.
enriched_for_scan = [{
    "elevation": pl["elevation"],
    "elevation_interval_m": pl["elevation_interval_m"],
    "distance_m": pl["distance_m"],
} for pl in parsed_legs]
warnings = scan_legs_for_warnings(enriched_for_scan, opts_threshold)

for i, (row, w) in enumerate(zip(legs_rows, warnings)):
    row["max_grade_pct"] = w["max_grade_pct"]
    row["warnings"] = _json.dumps(w["warnings"]) if w["warnings"] else None

wp_model.replace_legs(route_id, legs_rows)
```

And extend the JSON response so the frontend can render warnings without a follow-up fetch. In the `return jsonify({...})` block, add to each leg entry in the comprehension:

```python
"legs": [
    {
        "from_position": row["from_position"],
        "to_position": row["to_position"],
        "distance_m": row["distance_m"],
        "duration_s": row["duration_s"],
        "polyline": row["polyline"],
        "max_grade_pct": row.get("max_grade_pct"),
        "warnings": _json.loads(row["warnings"]) if row.get("warnings") else None,
    }
    for row in legs_rows
],
```

- [ ] **Step 4: Test the end-to-end path.** Add to `tests/test_api_routing.py`:

```python
def test_generate_writes_warnings_when_threshold_crossed(client, app, monkeypatch):
    rid = client.post("/api/routes", json={"title": "Steep"},
                      content_type="application/json").get_json()["id"]
    client.post(f"/api/routes/{rid}/waypoints",
                json={"kind": "stop", "name": "A", "lat": 0, "lon": 0})
    client.post(f"/api/routes/{rid}/waypoints",
                json={"kind": "stop", "name": "B", "lat": 0, "lon": 0.01})
    client.patch(f"/api/routes/{rid}/options", json={"max_gradient_warn": 10.0})

    # Forge a Valhalla response with a deliberately steep middle section.
    forged = {
        "trip": {
            "legs": [{
                "summary": {"length": 1.0, "time": 300.0},
                "shape": "abc",
                "elevation": (
                    [100.0] * 10 +
                    [100.0 + i * 2.0 for i in range(50)] +  # 20%/100m
                    [200.0] * 10
                ),
            }],
            "summary": {"length": 1.0, "time": 300.0},
        },
        "elevation_interval": 10.0,
    }

    monkeypatch.setattr(
        "server.blueprints.api_routing.vc.call_route",
        lambda **kw: forged,
    )
    resp = client.post(f"/api/routes/{rid}/generate")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    leg = body["legs"][0]
    assert leg["warnings"] is not None
    assert len(leg["warnings"]) >= 1
    assert leg["warnings"][0]["peak_grad_pct"] >= 10.0


def test_generate_no_warnings_when_threshold_null(client, app, monkeypatch):
    rid = client.post("/api/routes", json={"title": "Flat"},
                      content_type="application/json").get_json()["id"]
    client.post(f"/api/routes/{rid}/waypoints",
                json={"kind": "stop", "name": "A", "lat": 0, "lon": 0})
    client.post(f"/api/routes/{rid}/waypoints",
                json={"kind": "stop", "name": "B", "lat": 0, "lon": 0.01})
    # max_gradient_warn NOT set.
    forged = {
        "trip": {
            "legs": [{
                "summary": {"length": 1.0, "time": 300.0},
                "shape": "abc",
                "elevation": [100.0, 102.0, 104.0, 106.0, 108.0, 110.0] * 5,
            }],
            "summary": {"length": 1.0, "time": 300.0},
        },
        "elevation_interval": 10.0,
    }
    monkeypatch.setattr(
        "server.blueprints.api_routing.vc.call_route",
        lambda **kw: forged,
    )
    resp = client.post(f"/api/routes/{rid}/generate")
    assert resp.status_code == 200
    assert resp.get_json()["legs"][0]["warnings"] is None
```

- [ ] **Step 5: Run.**

```bash
pytest tests/test_api_routing.py tests/test_routing_valhalla_client.py tests/test_route_postprocess.py -v
```

Expected: all green. If `test_parse_legs_includes_elevation` fails because the fixture has no elevation, re-run Task M3c-1 step 2.

- [ ] **Step 6: Commit.**

```bash
git add server/routing/valhalla_client.py server/blueprints/api_routing.py tests/test_api_routing.py tests/test_routing_valhalla_client.py
git commit -m "feat(routing): generate_route writes gradient warnings to legs (M3c)"
```

---

### Task M3c-5: Frontend — render ⚠️ badges + tint over-threshold sub-segments

**Files:**
- Modify: `src/js/create/app.js`
- Modify: `src/js/shared/waypoint-editor.js`
- Modify: `src/css/create.css`

- [ ] **Step 1: Accept per-row warnings in the editor.** In `src/js/shared/waypoint-editor.js::render()`, alongside the `w.pin_role` and link-badge rendering, add a leg-warning slot — populated by the owning page via `setWaypoints` (we pass an enriched list where each row may have a synthetic `_leg_warning_peak` field set by app.js).

```javascript
${w._leg_warning_peak != null ? ` <span class="wpe-warn-badge" title="Peak gradient ${w._leg_warning_peak}% on leg in">⚠️</span>` : ''}
```

Inside the `wpe-name` div, after the existing badges.

- [ ] **Step 2: Wire the warnings into the editor feed.** In `src/js/create/app.js::onWaypointsChanged` (or the sibling function that hydrates the editor post-generate), enrich each waypoint with its incoming-leg warning:

```javascript
function annotateWaypointsWithLegWarnings(waypoints, legs) {
  // legs: list of {from_position, to_position, warnings: [...] | null, max_grade_pct}
  const byTo = new Map();
  for (const leg of (legs || [])) {
    if (leg.warnings && leg.warnings.length > 0) {
      // Peak across all sub-segments.
      const peak = Math.max(...leg.warnings.map(w => w.peak_grad_pct));
      byTo.set(leg.to_position, peak);
    }
  }
  return waypoints.map(w => ({
    ...w,
    _leg_warning_peak: byTo.has(w.position) ? byTo.get(w.position) : null,
  }));
}
```

Hook it in wherever the editor is re-hydrated after `generate`:

```javascript
editor.setWaypoints(annotateWaypointsWithLegWarnings(state.waypoints, state.legs));
```

Store `state.legs` whenever `/generate` responds:

```javascript
// After a successful generate response:
state.legs = response.legs || [];
```

- [ ] **Step 3: Tint map sub-segments.** In `drawGeneratedRoute`, after the main `L.polyline(...)` is added, overlay a second polyline for each warning range. Use the steepest-band colour from the existing gradient legend — look up via `import { rangeForGradient } from '../analysis/gradient.js'` (if exported) or hard-code `#ff3f2f` as the red band.

```javascript
function drawWarningOverlay(state, leg, latlngs) {
  if (!leg.warnings) return;
  // leg.polyline was decoded into latlngs (precision 6). leg.warnings
  // uses metre offsets from the leg start. Compute cumulative distance
  // along latlngs and slice.
  const cum = [0];
  for (let i = 1; i < latlngs.length; i++) {
    cum.push(cum[i - 1] + haversineMeters(
      latlngs[i - 1][0], latlngs[i - 1][1],
      latlngs[i][0], latlngs[i][1],
    ));
  }
  leg.warnings.forEach(w => {
    const slice = [];
    for (let i = 0; i < latlngs.length; i++) {
      if (cum[i] >= w.from_m && cum[i] <= w.to_m) slice.push(latlngs[i]);
    }
    if (slice.length < 2) return;
    const overlay = L.polyline(slice, {
      color: '#ff3f2f', weight: 8, opacity: 0.7, interactive: false,
    });
    overlay.addTo(state.map);
    // Track for cleanup.
    if (!state.warningOverlays) state.warningOverlays = [];
    state.warningOverlays.push(overlay);
  });
}
```

Inside `drawGeneratedRoute` after adding each leg polyline, call `drawWarningOverlay(state, leg, decoded)`. And in `clearGeneratedLayer`, clear any overlays too:

```javascript
function clearGeneratedLayer(state) {
  if (state.generatedLayer) {
    state.map.removeLayer(state.generatedLayer);
    state.generatedLayer = null;
  }
  if (state.warningOverlays) {
    for (const ov of state.warningOverlays) state.map.removeLayer(ov);
    state.warningOverlays = null;
  }
}
```

Verify `clearGeneratedLayer` exists — grep:

```bash
grep -n "clearGeneratedLayer" src/js/create/app.js
```

If it's inline, add the overlay clear at each call site.

- [ ] **Step 4: CSS for the warning badge.** Append to `src/css/create.css`:

```css
.wpe-warn-badge {
  font-size: 0.9em;
  padding: 0 3px;
}
.wpe-warn-badge[title] {
  cursor: help;
}
```

- [ ] **Step 5: Rebuild + smoke.**

```bash
npm run build
```

Smoke: set `max_gradient_warn=5`, Generate a route in hilly terrain. Observe ⚠️ badges on the appropriate rows and red overlay on map.

- [ ] **Step 6: Commit.**

```bash
git add src/js/create/app.js src/js/shared/waypoint-editor.js src/css/create.css
git commit -m "feat(create): gradient warning badges + map overlay (M3c)"
```

---

### Task M3c-6: Playwright — gradient warning E2E

**Files:**
- Modify: `tests/test_ui_options.py`

- [ ] **Step 1: Append test.**

```python
def test_gradient_warning_badge_shows_when_threshold_crossed(page, server_url, tmp_path):
    """End-to-end: with a real Valhalla this is flaky, so skip unless
    VALHALLA_LIVE=1. The unit-level scanner + endpoint tests already
    cover the core logic; this test validates the UI wiring."""
    import os
    if not os.environ.get("VALHALLA_LIVE"):
        import pytest
        pytest.skip("VALHALLA_LIVE=1 required (needs real Valhalla with hilly terrain)")

    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    page.wait_for_function("() => new URL(location.href).searchParams.get('route_id') !== null")
    # Known-steep route (tune lat/lon for your local Valhalla coverage).
    # …drop stops, set max_gradient_warn=5, click Generate, wait for warning badge…
    # This is a template; the engineer executing the plan should wire up
    # a live fixture covering their local terrain.
    page.locator("#route-max-grad").fill("5")
    page.locator("#route-max-grad").blur()
    # … (environment-specific setup to produce a steep route) …
    # Expected outcome: a .wpe-warn-badge appears on at least one row.
    # expect(page.locator(".wpe-warn-badge").first).to_be_visible(timeout=15000)
```

- [ ] **Step 2: Run the skip-unless-live test.**

```bash
pytest tests/test_ui_options.py -v
```

Expected: the new test skips, others pass.

- [ ] **Step 3: Commit.**

```bash
git add tests/test_ui_options.py
git commit -m "test(ui): gradient warning E2E skeleton (skipped unless live) (M3c)"
```

---

### Task M3c-7: M3 close-out — manual verification

**Files:** Append to this plan file.

- [ ] **Step 1: Start dev server.**

```bash
./dev.sh --env-file .env.development
```

- [ ] **Step 2: Full manual smoke across all three phases.**

1. `/create` → drop 5 points; change preset road → gravel-mtb; Generate → route follows unpaved shortcuts.
2. Tick round-trip → Generate → route closes back to start.
3. Set `max grad warn = 5` → Generate → map shows red overlay on a steep section; sidebar row shows ⚠️.
4. Pin the 3rd stop as Start; Optimise → the pinned stop is at index 0.
5. Drop a waypoint between stop #1 and #2 (line-drag) → 🔗 badge appears. Optimise → waypoint stays adjacent to its preceding stop.
6. Right-click the waypoint → Unlink → 🔗 disappears. Optimise again → the (now-free) waypoint may move.
7. Exclude a stop via sidebar ● toggle → row dims; Regenerate → route skips it.
8. Right-click excluded marker → "Include in route" → row un-dims.

- [ ] **Step 3: Run the full pytest + Playwright regression.**

```bash
pytest tests/ -v
```

Expected: all green (some skips for VALHALLA_LIVE if not set).

- [ ] **Step 4: Append a verification marker to this plan file.**

```markdown
---

**M3 verified:** YYYY-MM-DD by <name>. All three phases (M3a, M3b, M3c) landed, full pytest + Playwright suites green, manual smoke passed on `http://localhost:5050/`.
```

- [ ] **Step 5: Commit the marker.**

```bash
git add docs/superpowers/plans/2026-04-17-route-creation-m3.md
git commit -m "chore: M3 verification sign-off"
```

- [ ] **Step 6: Merge to main (if that's the user's decision).**

The user may prefer to PR-review before merging. Stop here and await instruction.

---

## Self-review checklist

Before marking M3 complete, confirm each of the following holds.

### M3a
- [ ] `GET /api/routing-presets` returns 6 entries and excludes `hybrid`.
- [ ] `PATCH /api/routes/<id>/options` accepts `profile`, `costing_preset`, `costing_options` (dict), `round_trip`, `max_gradient_warn`.
- [ ] Changing `costing_preset` / `costing_options` / `profile` / `round_trip` clears cached `route_legs` (analysis page shows "needs regeneration").
- [ ] Changing `max_gradient_warn` does NOT clear legs.
- [ ] `generate_route` no longer hard-codes `costing_options={}`; the Valhalla request body reflects the resolved preset.
- [ ] Preset dropdown in the Create toolbar is populated and persists on change.
- [ ] Custom costing panel opens via the ⚙ button AND auto-opens when preset='custom'.
- [ ] Pin start/end checkboxes per sidebar row flip the `pin_role` with mutual exclusion.
- [ ] Include/exclude works from BOTH the sidebar ● toggle AND the right-click map menu.
- [ ] Excluded waypoints do not appear in the Valhalla request (already handled server-side by `generate_route`).

### M3b
- [ ] `route_waypoints.linked_to_previous` column exists; defaults to 1; existing routes survive the migration.
- [ ] `append_waypoint` / `insert_waypoint_at` / `update_waypoint` all accept `linked_to_previous`.
- [ ] `POST /api/routes/<id>/waypoints` and `PATCH .../<wpt_id>` accept `linked_to_previous` (int 0/1).
- [ ] Right-click context menu shows **Unlink from previous** on a linked waypoint, **Re-link to previous** on an unlinked waypoint, and neither on a stop.
- [ ] `POST /api/routes/<id>/optimise` returns `{ new_order: [wpid, ...] }` and persists via `reorder_waypoints`.
- [ ] Optimiser respects `pin_role='start'` → stays at index 0.
- [ ] Optimiser respects `pin_role='end'` → stays at final index.
- [ ] Linked waypoints stay adjacent to their preceding stop.
- [ ] Unlinked waypoints may be reordered independently.
- [ ] Toggling `linked_to_previous` clears `route_options.last_optimised_at`.
- [ ] Line-drag-inserted waypoints explicitly pass `linked_to_previous: 1`.
- [ ] Sidebar renders 🔗 on linked waypoint rows.
- [ ] `#btn-optimise` is enabled and wired.

### M3c
- [ ] Valhalla fixture contains an `elevation` array and `elevation_interval`.
- [ ] `parse_legs` returns per-leg `elevation` + `elevation_interval_m`.
- [ ] `scan_legs_for_warnings` returns a list parallel to input, each element with `max_grade_pct` + `warnings` (or both None when `max_gradient_warn` is null).
- [ ] `generate_route` writes JSON warnings into `route_legs.warnings` and echoes them on the response.
- [ ] Sidebar renders ⚠️ on rows whose incoming leg has warnings.
- [ ] Map shows red overlay on over-threshold sub-segments.
- [ ] Clearing `max_gradient_warn` + regenerating removes warnings without a fresh Valhalla call for the UI (legs themselves are regenerated with the new threshold).

---

## Execution Handoff

This plan is split into three commit-sized phases; each ends with a manual smoke task. Review checkpoints:

**After M3a commits land** (Tasks M3a-1 through M3a-12 on the branch):
Review the options UX against the M3a acceptance bullets in the spec. A useful diff preview:

```bash
git log --oneline feature/route-creation ^main | grep M3a
pytest tests/test_api_options.py tests/test_api_presets.py tests/test_routing_presets.py tests/test_ui_options.py -v
```

**After M3b commits land** (Tasks M3b-1 through M3b-9):
Review the optimiser + link-flag UX. The load-bearing checks are:

```bash
pytest tests/test_optimiser.py tests/test_api_optimise.py tests/test_api_waypoints.py -v
```

And a manual 5-point optimise with a pinned-start + linked-waypoint to confirm grouping.

**After M3c commits land** (Tasks M3c-1 through M3c-7):
Review the gradient-warning path. Confirm:

```bash
pytest tests/test_route_postprocess.py tests/test_api_routing.py tests/test_routing_valhalla_client.py -v
```

And a manual Generate on a hilly route with `max_gradient_warn=5`.

At that point every bullet in the spec's M3 acceptance list (spec lines 282–289) should be verifiably passing.
