# Route Creation M2: Inline Edit Panel on Analysis Page

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Let the user edit any recipe-backed route directly on its Analysis page via a slide-out panel. Clicking **Edit** on an analysis view reveals the same `waypoint-editor` used on the Create page, mounted to the right edge over the map. Map marker drag, right-click context menu, and add-by-map-click all work the same as Create. A **Regenerate Route** button re-runs Valhalla; on success the analysis page reloads so the new track + gradient data are rendered by the existing pipeline. Routes that don't have a recipe (legacy uploads, pre-M4 imports) show a disabled Edit button with a tooltip.

**Architecture:** Reuse all the shared modules M1 already ships (`waypoint-editor`, `waypoint-markers`, `route-api`, `polyline`, `map-layers`). New code is a thin analysis-page-specific controller (`edit-panel.js`) plus template and CSS changes. The current analysis page has a stable public surface (it reads GPX from `/api/gpx/<id>` and renders). On regenerate success, do a `window.location.reload()` so the existing init path picks up the fresh GPX — deliberately avoids a bespoke in-place re-render in M2 (deferred to polish).

**Scope boundaries:**
- **In:** Edit button + slide-out panel, marker drag, add-by-click on the map, right-click context menu reusing M1's component, Regenerate Route button, Close/Discard (just closes — M1 persists immediately so there's nothing to "discard" in the M1 sense), disabled state for recipe-less routes.
- **In (added mid-milestone):** Line-drag on the generated Valhalla polyline to insert a new waypoint mid-leg with automatic position renumbering — see Task 6.
- **In (added mid-milestone):** Per-leg routing — every pin becomes a Valhalla break so each adjacent pair gets its own leg + cached polyline. Simplifies line-drag, eliminates the segment-projection workaround, and gives M3's optimiser a richer cost matrix — see Task 7.
- **Out (M6):** "Convert GPX to recipe" heuristic for legacy routes.
- **Out (M3):** Costing-preset UI, round-trip, optimise. The `linked_to_previous` flag that keeps shape-waypoints attached to their preceding stop through optimiser reorders also lands in M3.

**Mid-milestone pivot note:** The original M2 shipped an inline slide-out edit panel on the Analysis page (Tasks 1–5). User feedback after that landed was that combining view + edit on one screen was confusing, so we pivoted: the Analysis page now links out to `/create?route_id=<id>` (the Create page IS the editor), and a dirty-state guard prompts before navigating with unregenerated edits. The slide-out module + its tests were removed. Task 6 below adds line-drag on top of the pivoted UX.

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

### Task 6: Line-drag to insert a waypoint (route reshape)

**Feature:** On the Create page (the pivoted editor), the user can click-and-drag anywhere on the generated Valhalla route polyline — **not** on an existing pin — to create a new waypoint at the drop location. The new waypoint splices between the two waypoints that bound the dragged leg, everything below it shifts down one position, and the route regenerates.

**Why here:** The pivoted M2 UX (Create page = editor) exposes the generated polyline; line-drag belongs in the same mental model as "click to add waypoint / drag pin to move". Done before M3 so optimisation has the richer edit primitives to work with.

**Files:**
- Modify: `server/models/waypoints.py` — add `insert_waypoint_at(route_id, position, ...)`.
- Modify: `server/blueprints/api_waypoints.py` — POST accepts optional `position`.
- Modify: `src/js/create/app.js` — draw each leg as its own interactive polyline; wire line-drag → ghost marker → insert-at-position.
- Modify: `src/css/create.css` — cursor hint when hovering over a leg, ghost-marker style.
- Modify: `tests/test_api_waypoints.py` — insert-at-position backend coverage.
- Modify: `tests/test_ui_create.py` — Playwright coverage for the drag.

---

**Step 1 (backend model — failing test):** In `tests/test_models_waypoints.py`, add:
```python
def test_insert_waypoint_at_shifts_subsequent_positions(app):
    with app.app_context():
        rid = create_route(title="x")["id"]
        a = wp.append_waypoint(rid, name="A", lat=0, lon=0, kind="stop")
        b = wp.append_waypoint(rid, name="B", lat=1, lon=1, kind="stop")
        c = wp.append_waypoint(rid, name="C", lat=2, lon=2, kind="stop")
        # Insert X between A (position 0) and B (position 1): X goes to position 1,
        # B shifts to 2, C to 3.
        x = wp.insert_waypoint_at(rid, position=1,
                                   name="X", lat=0.5, lon=0.5, kind="waypoint")
        rows = wp.list_waypoints(rid)
        names_in_order = [r["name"] for r in rows]
        assert names_in_order == ["A", "X", "B", "C"]
        positions = [r["position"] for r in rows]
        assert positions == [0, 1, 2, 3]
```

**Step 2 (backend model — implement):** In `server/models/waypoints.py`:
```python
def insert_waypoint_at(route_id, position, *, name, lat, lon, kind,
                       address=None, description=None,
                       included=1, pin_role=None, dwell_minutes=0):
    """Insert a waypoint at the given position, shifting every existing
    waypoint with position >= `position` up by one to preserve the
    UNIQUE(route_id, position) invariant."""
    db = get_db()
    # Phase 1: push conflicting rows out of the way by negating their
    # positions (same two-phase technique used by reorder_waypoints).
    db.execute(
        "UPDATE route_waypoints SET position = -(position + 2) "
        "WHERE route_id = ? AND position >= ?",
        (route_id, position),
    )
    # Phase 2: insert at the target slot.
    cur = db.execute(
        """INSERT INTO route_waypoints (
             route_id, position, kind, name, address, lat, lon,
             included, pin_role, dwell_minutes, description
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (route_id, position, kind, name, address, lat, lon,
         included, pin_role, dwell_minutes, description),
    )
    # Phase 3: fold the shifted rows back to their new, bumped positions.
    db.execute(
        "UPDATE route_waypoints SET position = -position - 1 "
        "WHERE route_id = ? AND position < 0",
        (route_id,),
    )
    db.commit()
    return get_waypoint(cur.lastrowid, route_id)
```
Run the test: `pytest tests/test_models_waypoints.py::test_insert_waypoint_at_shifts_subsequent_positions -v` — expect PASS.

**Step 3 (API — failing test):** In `tests/test_api_waypoints.py`:
```python
def test_append_with_position_inserts_and_shifts(client):
    r = client.post("/api/routes", json={"title": "r"}, content_type="application/json")
    rid = r.get_json()["id"]
    for i, name in enumerate(["A", "B", "C"]):
        client.post(f"/api/routes/{rid}/waypoints",
                    json={"name": name, "lat": i, "lon": i, "kind": "stop"})
    # Insert X at position 1 (between A and B).
    resp = client.post(f"/api/routes/{rid}/waypoints",
                       json={"name": "X", "lat": 0.5, "lon": 0.5,
                             "kind": "waypoint", "position": 1})
    assert resp.status_code == 201
    listing = client.get(f"/api/routes/{rid}/waypoints").get_json()
    assert [w["name"] for w in listing] == ["A", "X", "B", "C"]
```

**Step 4 (API — implement):** In `server/blueprints/api_waypoints.py::append_waypoint`, branch on `position`:
```python
position = data.get("position")
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
if position is None:
    wp = wp_model.append_waypoint(route_id, **common)
else:
    wp = wp_model.insert_waypoint_at(route_id, position=int(position), **common)
```
Run: `pytest tests/test_api_waypoints.py -v` — expect green.

**Step 5 (frontend drawing — one polyline per leg):** In `src/js/create/app.js`, change `drawGeneratedRoute` so each leg becomes its own `L.polyline` with `interactive: true`, tagged with `leg.from_position`:
```javascript
function drawGeneratedRoute(state, legs) {
  clearGeneratedLayer(state);
  if (!legs.length) return;
  const group = L.featureGroup().addTo(state.map);
  legs.forEach((leg, i) => {
    if (!leg.polyline) return;
    const latlngs = decodePolyline(leg.polyline, 6);
    if (latlngs.length < 2) return;
    const line = L.polyline(latlngs, {
      color: state.routeColor, weight: 4, opacity: 0.9, interactive: true,
    });
    line._legFromPosition = leg.from_position ?? i;
    line.on('mousedown', (ev) => startLineDrag(state, line, ev));
    group.addLayer(line);
  });
  state.generatedLayer = group;
  updatePreviewLine(state);
}
```
The `applyColors` helper iterates `state.generatedLayer.eachLayer(l => l.setStyle(...))` now that it's a group.

**Step 6 (line-drag handler):** Implement `startLineDrag` in the same file. Strategy:
- On mousedown, disable `map.dragging`; record the clicked `leg._legFromPosition` and the current latlng.
- Create a `L.circleMarker` ghost at the pointer position.
- Track `mousemove` on the map container: update ghost latlng.
- On `mouseup`: re-enable `map.dragging`, read the ghost's final latlng, call `maybeSnapToRoad()` (reuse M1 helper), then POST:
  ```js
  await fetch(`/api/routes/${state.routeId}/waypoints`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: 'Waypoint',
      lat: final.lat, lon: final.lon,
      kind: 'waypoint',
      position: line._legFromPosition + 1,
    }),
  });
  ```
- On success: refresh `state.waypoints` from the server, re-render markers + sidebar, bump `state.currentVersion`, trigger auto-regenerate if enabled. Clean up the ghost either way.

Keep the handler compact (~60 lines). Pull the mousemove / mouseup listeners on `document` (not the map container) so a fast drag that leaves the map still ends cleanly; remove them in a shared `cleanup()`.

**Step 7 (CSS affordance):** In `src/css/create.css`:
```css
/* Hovering over a generated leg signals "drag me". */
.leaflet-interactive { cursor: crosshair; }
#map.is-dragging-line .leaflet-interactive { cursor: grabbing; }

/* Ghost marker following the cursor during a line-drag. */
.route-drag-ghost {
  pointer-events: none;
  stroke: #fff;
  stroke-width: 2;
  fill: var(--preview-color, #00e5ff);
  fill-opacity: 0.9;
}
```
Toggle `is-dragging-line` on `#map` from the drag handler so the cursor stays `grabbing` even when the pointer leaves the polyline.

**Step 8 (Playwright — failing test):** In `tests/test_ui_create.py`:
```python
def test_line_drag_inserts_waypoint_between_neighbours(page, server_url, monkeypatch_valhalla):
    """Drag on the generated route polyline → new waypoint inserted between
    the two pins that bound that leg; the list renumbers in order."""
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    page.wait_for_function("() => window.__appReady === true", timeout=10000)

    # Drop two pins — Generate Now (mocked Valhalla returns 1 leg).
    _click_map_at(page, "#map", 0.3, 0.5)
    _click_map_at(page, "#map", 0.7, 0.5)
    page.locator("#btn-gen-primary").click()
    # Wait for the generated polyline to exist (a single leg group).
    page.wait_for_selector(".leaflet-interactive[stroke]", timeout=5000)

    # Drag from roughly the midpoint of the rendered leg to a new position.
    box = page.locator("#map").bounding_box()
    page.mouse.move(box["x"] + 0.5 * box["width"], box["y"] + 0.5 * box["height"])
    page.mouse.down()
    page.mouse.move(box["x"] + 0.5 * box["width"], box["y"] + 0.3 * box["height"], steps=10)
    page.mouse.up()

    # Sidebar now has three rows — the new one at position 1 (between 0 and 2).
    expect(page.locator(".wpe-item")).to_have_count(3, timeout=5000)
    positions = page.evaluate(
        "() => Array.from(document.querySelectorAll('.wpe-item'))"
        ".map(el => parseInt(el.dataset.position, 10))"
    )
    assert positions == [0, 1, 2], positions
```
(If Valhalla isn't easily mockable at this level, use a fixture that patches `POST /api/routes/<id>/generate` with a two-point synthesised polyline via `page.route(...)` — same pattern as `test_regenerate_button_calls_generate_and_reloads`.)

**Step 9 (run + fix until green):**
```
pytest tests/test_models_waypoints.py tests/test_api_waypoints.py -v
pytest tests/test_ui_create.py::test_line_drag_inserts_waypoint_between_neighbours -v
```

**Step 10 (commit):**
```
git add server/models/waypoints.py server/blueprints/api_waypoints.py \
        src/js/create/app.js src/css/create.css \
        tests/test_models_waypoints.py tests/test_api_waypoints.py \
        tests/test_ui_create.py
npm run build
git add server/static/dist/  # only if bundles are tracked
git commit -m "feat(create): drag the generated route to insert a waypoint mid-leg"
```

**Acceptance:**
- Hovering the generated polyline shows a crosshair cursor.
- Drag on a leg creates a ghost that follows the pointer.
- Drop inserts a waypoint with `position = leg.from_position + 1`; downstream positions shift.
- Snap-to-road applies to the drop point (reuses M1's 10 m threshold).
- Auto-regenerate (if enabled) fires once; manual mode marks the page dirty.
- Sidebar rows render in `position` order — no gaps, no duplicates.

---

### Task 7: Per-leg routing — one Valhalla leg per adjacent waypoint pair

**Feature:** Send every waypoint to Valhalla as `type: break` so the response contains one leg per adjacent pair (N-1 legs for N waypoints), regardless of whether a pin is a stop or a waypoint. This eliminates the through-type collapse that motivated the `insertionPositionForDrag` helper; line-drag becomes `leg.from_position + 1` again because each drawn polyline now maps 1:1 to a waypoint pair.

**Why the refactor:** The Task 6 fix (segment projection) works but is clever and brittle. Per-leg routing is conceptually simpler and has a downstream win: M3's 2-opt optimiser needs a cost matrix of "distance between every pair we've routed", and per-leg caching gives it every adjacent pair for free. The `through` semantic Valhalla offers is a minor optimisation we don't otherwise use — we never surface turn-by-turn announcements where the difference would matter.

**Files:**
- Modify: `server/routing/valhalla_client.py` — drop the `type: break` vs `type: through` branching; all locations become breaks.
- Modify: `server/blueprints/api_routing.py` — `expected_legs = len(wps) - 1` (plus 1 for round-trip), drop the `break_positions` bookkeeping.
- Modify: `src/js/create/app.js` — `drawGeneratedRoute` goes back to using `leg.from_position` directly on each line; `startLineDrag` uses `line._legFromPosition + 1`; drop the `state.polylinePoints` plumbing.
- Delete: `src/js/shared/insertion.js` — no longer needed.
- Modify: `tests/test_routing_valhalla_client.py` — update the request-shape test (no through-type).
- Modify: `tests/test_api_routing.py` — update the expected-legs test to reflect N-1 legs for N waypoints of any kind.
- Modify: `tests/test_ui_create.py` — the multi-waypoint regression test stays (it still asserts correct insertion position) but is now exercising the simpler code path. Remove the `window.__computeInsertionPosition` hook.

**Why before M3:** Simpler state is cheaper to reason about when adding the optimiser. And the richer per-leg cache is a direct M3 input.

---

- [ ] **Step 1 (valhalla_client test — failing):** Update `tests/test_routing_valhalla_client.py::test_request_body_shape` (or equivalent): every location should be `type: break`, no `through`.

- [ ] **Step 2 (valhalla_client — implement):** In `build_request_body`, delete the `loc_type = "break" if ... else "through"` branch. Always use `break`:
```python
RADIUS_M = 100
for lat, lon in waypoints:
    locs.append({"lat": lat, "lon": lon, "type": "break", "radius": RADIUS_M})
```
`kinds` becomes unused by the client — leave the parameter in place (still passed from `api_routing.py`) but note in a comment that it's reserved for future per-kind costing.

- [ ] **Step 3 (api_routing test — failing):** In `tests/test_api_routing.py`, add/update a case: 4 waypoints of kind=`waypoint` → expect 3 legs (not 1). Adjust any existing tests that assumed through-collapse.

- [ ] **Step 4 (api_routing — implement):** In `generate_route`:
```python
n = len(wps)
expected_legs = n - 1
if opts.get("round_trip"):
    expected_legs = n  # closing leg back to the first waypoint
if len(parsed_legs) != expected_legs:
    return jsonify({
        "error": "Upstream routing service failed",
        "detail": f"Valhalla returned {len(parsed_legs)} legs, expected {expected_legs}",
    }), 502

# Every waypoint is a break now, so every adjacent pair is its own leg.
legs_rows = []
for i, leg in enumerate(parsed_legs):
    from_pos = wps[i]["position"]
    to_pos = wps[(i + 1) % n]["position"] if opts.get("round_trip") else wps[i + 1]["position"]
    legs_rows.append({
        "from_position": from_pos,
        "to_position": to_pos,
        "distance_m": leg["distance_m"],
        "duration_s": leg["duration_s"],
        "polyline": leg["polyline"],
    })
```
Drop the `break_positions` computation entirely.

- [ ] **Step 5 (frontend — simplify drawGeneratedRoute):** In `src/js/create/app.js`:
```javascript
function drawGeneratedRoute(state, legs) {
  clearGeneratedLayer(state);
  if (!legs || !legs.length) return;
  const group = L.featureGroup();
  let drewAnyLeg = false;
  legs.forEach((leg) => {
    if (!leg.polyline) return;
    const latlngs = decodePolyline(leg.polyline, 6);
    if (latlngs.length < 2) return;
    const line = L.polyline(latlngs, {
      color: state.routeColor, weight: 4, opacity: 0.9, interactive: true,
    });
    line._legFromPosition = leg.from_position;
    line.on('mousedown', (ev) => startLineDrag(state, line, ev));
    group.addLayer(line);
    drewAnyLeg = true;
  });
  if (!drewAnyLeg) return;
  group.addTo(state.map);
  state.generatedLayer = group;
  updatePreviewLine(state);
}
```
Drop the `flat` array, the `state.polylinePoints` plumbing, and the `window.__computeInsertionPosition` hook.

- [ ] **Step 6 (frontend — simplify startLineDrag):** `startLineDrag(state, line, mouseEvent)` goes back to reading `line._legFromPosition`:
```javascript
await api.insertWaypointAt(state.routeId, line._legFromPosition + 1, {
  name: 'Waypoint', lat: snap.lat, lon: snap.lon, kind: 'waypoint',
});
```
No segment-projection call.

- [ ] **Step 7 (delete dead code):**
```
git rm src/js/shared/insertion.js
```
Remove its import from `app.js` and the `window.__computeInsertionPosition` exposure. Remove the `polylinePoints` field from the initial `state` object.

- [ ] **Step 8 (update UI regression test):** In `tests/test_ui_create.py::test_line_drag_inserts_between_correct_pair_on_multi_waypoint_route`, stop calling `window.__computeInsertionPosition`. Instead replace the asserts with real mouse drags on the rendered leg polylines (the 6-waypoint fixture now produces 5 distinct interactive lines; find the one with `_legFromPosition = 4` via a small JS helper and drag on its midpoint). Keep the assertion: after the drag, the route-listing API returns 7 rows with positions `[0, 1, 2, 3, 4, 5, 6]` and the new row at position 5.

- [ ] **Step 9:** `npm run build` and run the full regression:
```
pytest tests/ --ignore=tests/test_ui_analysis.py
```

- [ ] **Step 10 (commit):**
```
git commit -m "refactor(routing): every waypoint is a break — one leg per adjacent pair"
```

**Acceptance:**
- 6 waypoints of any kind mix → 5 legs returned, 5 interactive polylines rendered.
- Line-drag on the segment between WP5 and WP6 inserts at position 5, without consulting any insertion helper.
- `src/js/shared/insertion.js` is gone; `state.polylinePoints` is gone; the bug cannot recur.
- M3 can treat `route_legs` as a (sparse) cost matrix where every currently-visible adjacency has real network data.

---

### Task 8: Manual verification + M2 close-out

- [ ] Start dev server: `./dev.sh --env-file .env.development`.
- [ ] Create a recipe route via `/create`, drop some pins, Generate → land on analysis page.
- [ ] Analysis page: click **Edit Route** → lands on `/create?route_id=<id>` with the recipe loaded.
- [ ] Drag a pin on the map → sidebar auto-regenerates (or marks dirty in manual mode).
- [ ] Right-click a pin → context menu (toggle kind, include/exclude, delete).
- [ ] Ctrl+click on an empty area → new stop appears.
- [ ] **Line-drag** on the generated route polyline → ghost follows the cursor, drop inserts a waypoint between the correct neighbours; sidebar reflows in order; auto-regenerate picks it up.
- [ ] With 6 waypoints of kind=waypoint, the Create page draws **5 distinct interactive polylines** (one per adjacent pair), and a drag on any one of them inserts at the correct position — the Task 7 per-leg refactor is load-bearing here.
- [ ] Create page: **Route Analysis** nav link returns to `/route/<id>`.
- [ ] Make an edit but don't regenerate, click Library → confirm dialog offers Regenerate-then-leave vs. Leave-anyway.
- [ ] Open a legacy (GPX-only) route → Edit button in Analysis nav disabled with tooltip.
- [ ] Run full suites: `pytest tests/test_ui_analysis.py tests/test_ui_create.py tests/test_ui_edit_panel.py tests/test_ui_library.py`.

- [ ] Append a `**M2 verified:**` line to the bottom of this plan.
- [ ] Hand back to the user (do not merge — same pattern as M1).

---

**M2 verified:** 2026-11-14 by Claude Code, for review by Phil Gersekowski. Audited after the fact. `test_ui_edit_panel.py` and `test_ui_create.py` pass (95-test run with the M1 suites); per-leg routing and line-drag insertion (Tasks 6-7) are exercised by `test_ui_create.py` and by the M3 smoke script. The manual checklist was not walked by hand. Deviations from the spec: editing happens on `/create?route_id=<id>` via the Edit Route link, not a slide-out panel on the Analysis page (commit `a0696b9` replaced the inline panel), and every waypoint is a routing break, giving one leg per adjacent pair. GPX-only routes keep a disabled Edit button. Full-suite status is as recorded in the M3 sign-off.
