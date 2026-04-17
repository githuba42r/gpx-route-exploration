# Route Creation M2: Inline Edit Panel on Analysis Page

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Let the user edit any recipe-backed route directly on its Analysis page via a slide-out panel. Clicking **Edit** on an analysis view reveals the same `waypoint-editor` used on the Create page, mounted to the right edge over the map. Map marker drag, right-click context menu, and add-by-map-click all work the same as Create. A **Regenerate Route** button re-runs Valhalla; on success the analysis page reloads so the new track + gradient data are rendered by the existing pipeline. Routes that don't have a recipe (legacy uploads, pre-M4 imports) show a disabled Edit button with a tooltip.

**Architecture:** Reuse all the shared modules M1 already ships (`waypoint-editor`, `waypoint-markers`, `route-api`, `polyline`, `map-layers`). New code is a thin analysis-page-specific controller (`edit-panel.js`) plus template and CSS changes. The current analysis page has a stable public surface (it reads GPX from `/api/gpx/<id>` and renders). On regenerate success, do a `window.location.reload()` so the existing init path picks up the fresh GPX — deliberately avoids a bespoke in-place re-render in M2 (deferred to polish).

**Scope boundaries:**
- **In:** Edit button + slide-out panel, marker drag, add-by-click on the map, right-click context menu reusing M1's component, Regenerate Route button, Close/Discard (just closes — M1 persists immediately so there's nothing to "discard" in the M1 sense), disabled state for recipe-less routes.
- **Out (M6):** "Convert GPX to recipe" heuristic for legacy routes.
- **Out (M3):** Costing-preset UI, round-trip, optimise.

---

## File structure

**Create:**
- `src/js/analysis/edit-panel.js` — slide-out panel controller. Wraps the shared `waypoint-editor` + marker machinery for use on the Analysis page.
- `src/css/edit-panel.css` — slide-out animation, positioning, backdrop.
- `tests/test_ui_edit_panel.py` — Playwright coverage.

**Modify:**
- `server/blueprints/api_routes.py` — `GET /api/routes/<id>` augments the route dict with `has_recipe: bool`.
- `server/blueprints/pages.py` — pass `has_recipe` to the analysis template.
- `server/templates/analysis.html` — Edit button in nav + edit-panel container DOM + stop-edit modal DOM (reuse the same IDs as Create; one CSS file covers both).
- `src/js/analysis/app.js` — import and mount `edit-panel.js`; pass current route + refresh callback.
- `src/css/analysis-bundle.css` — `@import "./edit-panel.css"`.

---

### Task 1: `has_recipe` on the route API

**Files:**
- Modify: `server/blueprints/api_routes.py`
- Modify: `tests/test_api_routes.py`

A cheap flag — `has_recipe` is `True` iff there are any rows in `route_waypoints` for the route. Surface it on `GET /api/routes/<id>` and on the listing endpoint for completeness.

- [ ] **Step 1:** Write a failing test — `test_api_routes.py::test_get_route_includes_has_recipe`:
```python
def test_get_route_includes_has_recipe(client, app):
    # Recipe-only route (from M1).
    r = client.post("/api/routes", json={"title": "Recipe"}, content_type="application/json")
    rid = r.get_json()["id"]
    got = client.get(f"/api/routes/{rid}").get_json()
    assert got["has_recipe"] is False  # no waypoints yet
    # Add a waypoint → has_recipe flips.
    client.post(f"/api/routes/{rid}/waypoints",
                json={"name": "A", "lat": 0, "lon": 0, "kind": "stop"})
    got = client.get(f"/api/routes/{rid}").get_json()
    assert got["has_recipe"] is True
```

- [ ] **Step 2:** Implement — in `api_routes.py::get_single_route`, add:
```python
from server.models import waypoints as wp_model
# ... inside get_single_route, after get_route ...
route["has_recipe"] = bool(wp_model.list_waypoints(route_id))
```

- [ ] **Step 3:** Run the pytest; the list endpoint can stay untouched for M2 (add later if needed).

- [ ] **Step 4:** Commit: `feat(api): GET /api/routes/<id> exposes has_recipe`

---

### Task 2: `has_recipe` passed to the Analysis page template

**Files:**
- Modify: `server/blueprints/pages.py` — the `/route/<int:route_id>` handler fetches the route and passes `has_recipe` in the template context.
- Modify: `server/templates/analysis.html` — new Edit button in the nav block; `disabled` attribute bound to `{% if not has_recipe %}disabled{% endif %}` with a tooltip explaining why.

- [ ] **Step 1:** Update `pages.py::analysis_page` (or equivalent) to call `wp_model.list_waypoints(route_id)` and compute `has_recipe` → pass via `render_template(..., has_recipe=...)`.

- [ ] **Step 2:** In `analysis.html`, add to the `{% block nav_items %}` section:
```html
<button id="btn-open-edit" type="button"
        {% if not has_recipe %}disabled title="This route has no recipe — coming in M6"{% else %}title="Edit stops and waypoints"{% endif %}>
  Edit Route
</button>
```

- [ ] **Step 3:** Manual smoke: open a recipe-backed route (created via M1 Create page) → button enabled. Open a GPX-only route (legacy upload) → button disabled.

- [ ] **Step 4:** Commit.

---

### Task 3: Slide-out panel DOM + CSS

**Files:**
- Modify: `server/templates/analysis.html` — add the panel container + close button + Regenerate button.
- Create: `src/css/edit-panel.css`.
- Modify: `src/css/analysis-bundle.css` — `@import "./edit-panel.css";`.

Template addition (after `{% block content %}` main area, before `{% endblock %}`):
```html
<div id="edit-panel-overlay" style="display:none;">
  <aside id="edit-panel">
    <div id="edit-panel-head">
      <strong>Edit route</strong>
      <button id="btn-close-edit" type="button" title="Close">✕</button>
    </div>
    <div id="edit-panel-editor"></div>
    <div id="edit-panel-foot">
      <span id="edit-panel-status" class="ep-status-idle">No changes</span>
      <button id="btn-regen-edit" type="button">Regenerate Route</button>
    </div>
  </aside>
</div>

<!-- Reuse the pin context menu + stop-edit modal DOM from the Create page -->
<div id="pin-ctx-menu" role="menu" style="display:none;"></div>
<div id="stop-edit-overlay" style="display:none;">
  <!-- same markup as in create.html; factor out if repeat gets painful in M3 -->
</div>
```

CSS — slide from the right edge, full map height, with a scrim so clicks outside dismiss:

```css
#edit-panel-overlay {
  position: absolute; inset: 0;
  pointer-events: none; z-index: 900;
}
#edit-panel {
  position: absolute; top: 0; right: 0; bottom: 0;
  width: 340px; background: #0f1d3a; border-left: 1px solid #0f3460;
  pointer-events: auto;
  display: flex; flex-direction: column;
  transform: translateX(100%); transition: transform 200ms ease-out;
}
#edit-panel-overlay.open #edit-panel { transform: translateX(0); }

#edit-panel-head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 14px; border-bottom: 1px solid #0f3460;
}
#edit-panel-head strong { color: #e6edf5; font-size: 1em; }
#btn-close-edit { background: transparent; border: none; color: #a0a0b0; font-size: 1.2em; cursor: pointer; }

#edit-panel-editor { flex: 1; overflow: auto; }

#edit-panel-foot {
  padding: 10px 12px; border-top: 1px solid #0f3460;
  display: flex; gap: 8px; align-items: center;
}
#btn-regen-edit {
  flex: 1; background: #e94560; color: #fff; border: 1px solid #e94560;
  padding: 8px 14px; border-radius: 4px; cursor: pointer; font-size: 0.9em;
}
#btn-regen-edit:disabled { opacity: 0.5; cursor: not-allowed; }

#edit-panel-status { font-size: 0.75em; font-family: ui-monospace, monospace; }
.ep-status-idle     { color: #6a7a9a; }
.ep-status-dirty    { color: #ff9f43; }
.ep-status-busy     { color: #00e5ff; }
.ep-status-ok       { color: #00c851; }
.ep-status-err      { color: #ff4757; }
```

- [ ] **Step 1:** Add the DOM + CSS.
- [ ] **Step 2:** `npm run build`; verify `analysis.min.css` contains the edit-panel styles.
- [ ] **Step 3:** Commit.

---

### Task 4: `edit-panel.js` controller

**Files:**
- Create: `src/js/analysis/edit-panel.js`
- Modify: `src/js/analysis/app.js` — import and init if `data-has-recipe` is true.

The panel's job:
1. On open, call `GET /api/routes/<id>/waypoints`, mount the shared `waypoint-editor`, render markers over the analysis page's existing map.
2. Wire map clicks (Ctrl+click = stop, click = waypoint), map marker drag (with snap-to-road), right-click context menu — all reuse M1's patterns.
3. Track dirty state (any edit flips `dirty = true`). `Regenerate` sends `/generate` then `window.location.reload()`. Close button dismisses (no rollback — edits persist immediately, same as Create).

Full file:

```javascript
// --- Analysis-page Edit panel (M2) ---
//
// Mounts the shared waypoint-editor inside a slide-out aside, wired to the
// analysis page's existing Leaflet map. Edits persist immediately (same model
// as the Create page); Regenerate re-runs Valhalla then reloads the page so
// the existing analysis init path picks up the new GPX + gradient data.

import { mountWaypointEditor } from '../shared/waypoint-editor.js';
import { renderMarkers } from '../shared/waypoint-markers.js';
import * as api from '../shared/route-api.js';

const SNAP_MAX_M = 10;
const SNAP_TIMEOUT_MS = 1500;

async function maybeSnap(lat, lon) {
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), SNAP_TIMEOUT_MS);
    const r = await fetch('/proxy/valhalla/locate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ locations: [{ lat, lon }], costing: 'bicycle', verbose: false }),
      signal: ctrl.signal,
    });
    clearTimeout(t);
    if (!r.ok) return { lat, lon };
    const edges = ((await r.json())[0] || {}).edges || [];
    if (!edges.length) return { lat, lon };
    const e = edges[0];
    if (e.correlated_lat == null || e.correlated_lon == null) return { lat, lon };
    const dist = haversine(lat, lon, e.correlated_lat, e.correlated_lon);
    return dist <= SNAP_MAX_M ? { lat: e.correlated_lat, lon: e.correlated_lon } : { lat, lon };
  } catch { return { lat, lon }; }
}

function haversine(a, b, c, d) {
  const R = 6371000, toR = x => x * Math.PI / 180;
  const dLat = toR(c - a), dLon = toR(d - b);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toR(a)) * Math.cos(toR(c)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
}

function setStatus(text, cls = 'idle') {
  const el = document.getElementById('edit-panel-status');
  if (!el) return;
  el.textContent = text;
  el.className = `ep-status-${cls}`;
}

// Pin context menu — copied from create/app.js. When we extract a shared
// module in a follow-up commit both pages import it; for M2 the duplication
// is intentional and localised.
let ctxDeleteArmed = null;
function closePinContextMenu() {
  const menu = document.getElementById('pin-ctx-menu');
  if (!menu) return;
  menu.style.display = 'none';
  menu.innerHTML = '';
  ctxDeleteArmed = null;
}
function openPinContextMenu(state, w, leafletEvt) {
  const menu = document.getElementById('pin-ctx-menu');
  const isStop = w.kind === 'stop';
  const included = w.included !== 0;
  menu.innerHTML = `
    <div class="ctx-header">${escapeHtml(w.name || (isStop ? 'Stop' : 'Waypoint'))}</div>
    <button data-act="toggle-kind" type="button">${isStop ? 'Mark as Waypoint' : 'Mark as Stop'}</button>
    <button data-act="toggle-include" type="button">${included ? 'Exclude from route' : 'Include in route'}</button>
    ${isStop ? '<button data-act="edit-stop" type="button">Edit stop details…</button>' : ''}
    <div class="ctx-sep"></div>
    <button data-act="delete" type="button" class="danger">Delete</button>
  `;
  const ev = leafletEvt?.originalEvent;
  if (ev) { menu.style.left = ev.clientX + 'px'; menu.style.top = ev.clientY + 'px'; }
  menu.style.display = 'block';

  menu.querySelectorAll('button[data-act]').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const act = btn.dataset.act;
      if (act === 'delete') {
        if (ctxDeleteArmed !== w.id) {
          ctxDeleteArmed = w.id;
          btn.textContent = 'Click again to confirm delete';
          btn.classList.add('confirm-danger');
          return;
        }
        closePinContextMenu();
        await api.deleteWaypoint(state.routeId, w.id);
        await state.refresh();
        return;
      }
      closePinContextMenu();
      if (act === 'toggle-kind') {
        await api.patchWaypoint(state.routeId, w.id, { kind: isStop ? 'waypoint' : 'stop' });
        await state.refresh();
      } else if (act === 'toggle-include') {
        await api.patchWaypoint(state.routeId, w.id, { included: included ? 0 : 1 });
        await state.refresh();
      } else if (act === 'edit-stop') {
        openStopEditModal(state, w);
      }
    });
  });
}

function openStopEditModal(state, w) {
  const overlay = document.getElementById('stop-edit-overlay');
  const nameInput = document.getElementById('stop-edit-name');
  const descInput = document.getElementById('stop-edit-description');
  const arrivalInput = document.getElementById('stop-edit-arrival');
  nameInput.value = w.name || '';
  descInput.value = w.description || '';
  arrivalInput.value = isoToLocalInput(w.arrival_time);
  overlay.style.display = 'flex';
  nameInput.focus();

  const save = async () => {
    const arrival = arrivalInput.value
      ? new Date(arrivalInput.value).toISOString()
      : null;
    await api.patchWaypoint(state.routeId, w.id, {
      name: nameInput.value.trim() || 'Stop',
      description: descInput.value.trim() || null,
      arrival_time: arrival,
    });
    overlay.style.display = 'none';
    cleanup();
    await state.refresh();
  };
  const cancel = () => { overlay.style.display = 'none'; cleanup(); };
  const keyHandler = (e) => {
    if (e.key === 'Escape') cancel();
    else if (e.key === 'Enter' && !e.shiftKey && e.target.tagName !== 'TEXTAREA') save();
  };
  function cleanup() {
    document.getElementById('stop-edit-save').removeEventListener('click', save);
    document.getElementById('stop-edit-cancel').removeEventListener('click', cancel);
    overlay.removeEventListener('keydown', keyHandler);
  }
  document.getElementById('stop-edit-save').addEventListener('click', save);
  document.getElementById('stop-edit-cancel').addEventListener('click', cancel);
  overlay.addEventListener('keydown', keyHandler);
}

function isoToLocalInput(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function escapeHtml(s) {
  return String(s || '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

/**
 * Initialise the Analysis-page edit panel.
 *
 * @param {Object} opts
 * @param {L.Map} opts.map — the analysis page's Leaflet map
 * @param {number} opts.routeId
 * @returns { open, close } API
 */
export function initEditPanel({ map, routeId }) {
  const state = {
    routeId,
    map,
    waypoints: [],
    markers: [],
    clickCounter: 0,
    dirty: false,
    isRegenerating: false,
    editor: null,
    refresh: async () => {
      state.waypoints = await api.listWaypoints(routeId);
      state.editor.setWaypoints(state.waypoints);
      state.markers = renderMarkers(map, state.waypoints, state.markers, {
        draggable: true,
        onDragEnd: async (w, { lat, lon }) => {
          const s = await maybeSnap(lat, lon);
          await api.patchWaypoint(routeId, w.id, { lat: s.lat, lon: s.lon });
          state.dirty = true;
          setStatus('Edits pending — click Regenerate', 'dirty');
          await state.refresh();
        },
        onContextMenu: (w, evt) => openPinContextMenu(state, w, evt),
      });
      if (state.waypoints.length > 0 && state.clickCounter < state.waypoints.length) {
        state.clickCounter = state.waypoints.length;
      }
    },
  };

  const overlay = document.getElementById('edit-panel-overlay');
  const editorEl = document.getElementById('edit-panel-editor');
  const closeBtn = document.getElementById('btn-close-edit');
  const regenBtn = document.getElementById('btn-regen-edit');

  // Mount the editor widget into the panel (shared with Create).
  state.editor = mountWaypointEditor(editorEl, {
    onReorder: async (ids) => {
      await api.reorderWaypoints(routeId, ids);
      state.dirty = true;
      setStatus('Edits pending — click Regenerate', 'dirty');
      await state.refresh();
    },
    onRemove: async (wptId) => {
      await api.deleteWaypoint(routeId, wptId);
      state.dirty = true;
      setStatus('Edits pending — click Regenerate', 'dirty');
      await state.refresh();
    },
  });

  // Map click → append waypoint (Ctrl+click = stop).
  const onMapClick = async (e) => {
    if (overlay.style.display !== 'flex') return;   // panel closed: inert
    const asStop = !!(e.originalEvent && (e.originalEvent.ctrlKey || e.originalEvent.metaKey));
    const n = ++state.clickCounter;
    const s = await maybeSnap(e.latlng.lat, e.latlng.lng);
    await api.appendWaypoint(routeId, {
      name: asStop ? `Stop ${n}` : `Waypoint ${n}`,
      lat: s.lat, lon: s.lon, kind: asStop ? 'stop' : 'waypoint',
    });
    state.dirty = true;
    setStatus('Edits pending — click Regenerate', 'dirty');
    await state.refresh();
  };

  // Context-menu dismiss.
  document.addEventListener('click', (e) => {
    const m = document.getElementById('pin-ctx-menu');
    if (m && m.style.display !== 'none' && !m.contains(e.target)) closePinContextMenu();
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closePinContextMenu(); });

  async function open() {
    overlay.style.display = 'flex';
    overlay.classList.add('open');
    await state.refresh();
    map.on('click', onMapClick);
    setStatus('No changes', 'idle');
  }
  function close() {
    overlay.classList.remove('open');
    overlay.style.display = 'none';
    map.off('click', onMapClick);
    state.markers.forEach(m => map.removeLayer(m));
    state.markers = [];
    closePinContextMenu();
  }

  closeBtn.addEventListener('click', close);

  regenBtn.addEventListener('click', async () => {
    if (state.isRegenerating) return;
    if (state.waypoints.length < 2) {
      setStatus('Need ≥ 2 waypoints', 'err');
      return;
    }
    state.isRegenerating = true;
    regenBtn.disabled = true;
    setStatus('Regenerating…', 'busy');
    try {
      await api.generateRoute(routeId);
      setStatus('Regenerated — reloading', 'ok');
      // Simplest reliable refresh: re-run the existing analysis init path.
      window.location.reload();
    } catch (err) {
      setStatus('Regenerate failed', 'err');
      console.error(err);
      alert('Regenerate failed: ' + err.message);
    } finally {
      state.isRegenerating = false;
      regenBtn.disabled = false;
    }
  });

  return { open, close };
}
```

- [ ] **Step 1:** Create the module.
- [ ] **Step 2:** Wire it in `src/js/analysis/app.js` — at the end of `main()`, after the map is available:
```javascript
import { initEditPanel } from './edit-panel.js';

// ... after map init ...
const hasRecipe = document.body.dataset.hasRecipe === 'true';
if (hasRecipe) {
  const panelApi = initEditPanel({ map, routeId: Number(document.body.dataset.routeId) });
  document.getElementById('btn-open-edit').addEventListener('click', panelApi.open);
}
```

Also ensure `analysis.html` writes `data-has-recipe="{{ 'true' if has_recipe else 'false' }}"` on `<body>`.

- [ ] **Step 3:** `npm run build`. Manual open/close in browser.
- [ ] **Step 4:** Commit.

---

### Task 5: Playwright coverage

**Files:**
- Create: `tests/test_ui_edit_panel.py`

```python
"""Playwright E2E for the M2 inline Edit panel on the Analysis page."""

import os
import requests as http_requests
from playwright.sync_api import expect

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _create_recipe_route(server_url, n_waypoints=2):
    """Create a recipe-backed route + n_waypoints + a fake /legs cache so
    the analysis page has something to render."""
    r = http_requests.post(
        f"{server_url}/api/routes",
        json={"title": "M2 test"},
        headers={"Content-Type": "application/json"},
    )
    rid = r.json()["id"]
    for i in range(n_waypoints):
        http_requests.post(
            f"{server_url}/api/routes/{rid}/waypoints",
            json={"name": f"WP{i}", "lat": -27.40 - i * 0.01, "lon": 152.90 + i * 0.01,
                  "kind": "stop"},
        )
    return rid


def _upload_gpx_only_route(server_url, title="legacy-gpx"):
    """Upload an ordinary GPX file — no recipe created."""
    gpx = (b'<?xml version="1.0"?><gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">'
           b'<trk><trkseg><trkpt lat="-27.4" lon="152.9"><ele>10</ele></trkpt>'
           b'<trkpt lat="-27.41" lon="152.91"><ele>11</ele></trkpt></trkseg></trk></gpx>')
    r = http_requests.post(
        f"{server_url}/api/routes",
        files={"file": ("legacy.gpx", gpx)},
        data={"title": title},
    )
    return r.json()["id"]


def _open_analysis(page, server_url, route_id):
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/route/{route_id}")
    # Existing analysis suite already proves the page loads; we wait for the
    # Edit button itself.
    expect(page.locator("#btn-open-edit")).to_be_visible(timeout=10000)


def test_edit_button_disabled_for_gpx_only_route(page, server_url):
    rid = _upload_gpx_only_route(server_url)
    _open_analysis(page, server_url, rid)
    expect(page.locator("#btn-open-edit")).to_be_disabled()


def test_edit_button_enabled_for_recipe_route(page, server_url):
    rid = _create_recipe_route(server_url)
    _open_analysis(page, server_url, rid)
    expect(page.locator("#btn-open-edit")).to_be_enabled()


def test_click_edit_opens_panel(page, server_url):
    rid = _create_recipe_route(server_url)
    _open_analysis(page, server_url, rid)
    page.locator("#btn-open-edit").click()
    expect(page.locator("#edit-panel-overlay")).to_have_class("open", timeout=2000)
    expect(page.locator(".wpe-item")).to_have_count(2)


def test_close_button_dismisses_panel(page, server_url):
    rid = _create_recipe_route(server_url)
    _open_analysis(page, server_url, rid)
    page.locator("#btn-open-edit").click()
    page.locator("#btn-close-edit").click()
    expect(page.locator("#edit-panel-overlay")).not_to_have_class("open")


def test_add_waypoint_via_map_click_inside_panel(page, server_url):
    rid = _create_recipe_route(server_url, n_waypoints=2)
    _open_analysis(page, server_url, rid)
    page.locator("#btn-open-edit").click()
    expect(page.locator(".wpe-item")).to_have_count(2)
    box = page.locator("#map").bounding_box()
    page.mouse.click(box["x"] + 0.3 * box["width"], box["y"] + 0.5 * box["height"])
    expect(page.locator(".wpe-item")).to_have_count(3, timeout=3000)
    # Status chip reflects the pending edit.
    expect(page.locator("#edit-panel-status")).to_contain_text("Edits pending")


def test_regenerate_button_calls_generate_and_reloads(page, server_url):
    rid = _create_recipe_route(server_url, n_waypoints=2)
    _open_analysis(page, server_url, rid)
    page.locator("#btn-open-edit").click()

    # Mock /generate so we don't depend on a live Valhalla.
    valid_polyline = '~rjgs@_ygsbH~oR_pR'
    page.route(f"**/api/routes/{rid}/generate", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=(f'{{"legs_count":1,"distance_km":0.5,"duration_s":120,'
              f'"gpx_url":"/api/gpx/{rid}",'
              f'"legs":[{{"from_position":0,"to_position":1,"distance_m":500,'
              f'"duration_s":120,"polyline":"{valid_polyline}"}}]}}'),
    ))

    # Click Regenerate; the page will reload on success.
    with page.expect_navigation(timeout=10000):
        page.locator("#btn-regen-edit").click()
    # After reload, we're back on the analysis page and the Edit button is
    # still there (reloaded fine).
    expect(page.locator("#btn-open-edit")).to_be_visible(timeout=10000)
```

- [ ] Write the test file exactly as above.
- [ ] `pytest tests/test_ui_edit_panel.py -v` → expect all 6 to pass.
- [ ] Commit.

---

### Task 6: Manual verification + M2 close-out

- [ ] Start dev server: `./dev.sh --env-file .env.development`.
- [ ] Create a recipe route via `/create`, drop some pins, Generate → land on analysis page.
- [ ] Click **Edit Route** in the nav — panel slides in.
- [ ] Drag a marker, observe status "Edits pending".
- [ ] Right-click a marker → context menu works (toggle kind, include/exclude, delete).
- [ ] Ctrl+click on map inside edit mode → drops a stop.
- [ ] Click "Regenerate Route" — Valhalla runs, page reloads, new track + gradient visible.
- [ ] Open a legacy (GPX-only) route — Edit button disabled with tooltip.
- [ ] Run full suites: `pytest tests/test_ui_analysis.py tests/test_ui_create.py tests/test_ui_edit_panel.py`.

- [ ] Append a `**M2 verified:**` line to the bottom of this plan.
- [ ] Hand back to the user (do not merge — same pattern as M1).
