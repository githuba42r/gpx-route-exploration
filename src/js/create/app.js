// --- Create Route page entry point ---
//
// Responsibilities:
//   - Auto-create a recipe-only route on first load; keep route_id in the URL
//   - Click map → append waypoint; right-click pin → toggle stop/waypoint
//   - Drag sidebar rows to reorder; X to remove; pin-first-as-start checkbox
//   - Dashed live-preview polyline between waypoints
//   - Generate Route: call Valhalla via /api/routes/<id>/generate.
//     • Auto-generate mode (toggle + settings popover) debounces + rate-limits
//     • Manual "Generate Now" button still rate-limited
//   - Draw the generated road-snapped track on this page (decode polylines
//     client-side), replacing the dashed preview section
//   - Structured error panel on failure — shows our endpoint and the upstream
//     Valhalla URL/body separately

import { initCreateMap, fitToWaypoints } from './map.js';
import { renderMarkers } from '../shared/waypoint-markers.js';
import { onLongPress, longPressJustFired } from '../shared/long-press.js';
import { mountWaypointEditor } from '../shared/waypoint-editor.js';
import { decodePolyline } from '../shared/polyline.js';
import * as api from '../shared/route-api.js';
import { openCsvImport } from '../shared/csv-import.js';
import { initAddressSearch } from './address-search.js';
import { initBottomSheet } from './bottom-sheet.js';

// Leading-edge debounce semantics:
//   - A waypoint change fires /generate IMMEDIATELY (if eligible).
//   - After a generate completes, a cooldown of `debounceMs` runs.
//   - Waypoint changes during that cooldown are remembered (pendingChange)
//     and fire exactly once when the cooldown ends.
//   - Debounce slider sets the cooldown duration; no separate global
//     rate limit anymore (debounceMs IS the rate limit).

const STORAGE_AUTO = 'gpx-create-auto-generate';
const STORAGE_DEBOUNCE = 'gpx-create-debounce-ms';
const STORAGE_ROUTE_COLOR   = 'gpx-create-route-color';
const STORAGE_PREVIEW_COLOR = 'gpx-create-preview-color';
const DEFAULT_ROUTE_COLOR   = '#ff5f15';
const DEFAULT_PREVIEW_COLOR = '#00e5ff';

// -------------------- snap-to-road --------------------
//
// Before appending / moving a waypoint, ask Valhalla's /locate endpoint
// what the nearest bicycle-routable road/path is. If it's within 10 m of
// the clicked point, use those snapped coords — dramatically improves
// /generate success rates since the first and last pins must be
// break-type (edge-snappable). 10 m is deliberately conservative: we
// don't want to yank a pin off-road that the user placed deliberately.
//
// Short timeout so we don't hold up the UI when Valhalla is slow or
// unreachable — we silently fall back to the user's raw coords.

const SNAP_MAX_DISTANCE_M = 10;
const SNAP_TIMEOUT_MS = 1500;

async function maybeSnapToRoad(lat, lon) {
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), SNAP_TIMEOUT_MS);
    const resp = await fetch('/proxy/valhalla/locate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        locations: [{ lat, lon }],
        costing: 'bicycle',
        verbose: false,
      }),
      signal: ctrl.signal,
    });
    clearTimeout(timer);
    if (!resp.ok) return { lat, lon, snapped: false };
    const body = await resp.json();
    const edges = (body?.[0]?.edges) || [];
    if (!edges.length) return { lat, lon, snapped: false };
    // Valhalla orders edges by proximity; edges[0] is the closest.
    const best = edges[0];
    const snappedLat = best.correlated_lat;
    const snappedLon = best.correlated_lon;
    if (snappedLat == null || snappedLon == null) return { lat, lon, snapped: false };
    const dist = (best.distance != null)
      ? best.distance
      : haversineMeters(lat, lon, snappedLat, snappedLon);
    if (dist > SNAP_MAX_DISTANCE_M) return { lat, lon, snapped: false, distanceM: dist };
    return { lat: snappedLat, lon: snappedLon, snapped: true, distanceM: dist };
  } catch (_) {
    // Aborted, network error, or bad JSON — silently fall back.
    return { lat, lon, snapped: false };
  }
}

function haversineMeters(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const toRad = d => d * Math.PI / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2
          + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// -------------------- route bootstrap --------------------

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

// -------------------- drawing --------------------

function updatePreviewLine(state) {
  // Always remove the existing preview before deciding whether to draw a new
  // one — keeps state clean even if the decision flips to "hide".
  if (state.previewLine) { state.map.removeLayer(state.previewLine); state.previewLine = null; }
  // If a fresh road-snapped route is already drawn the dashed preview is
  // redundant noise. Only show the preview when there's no generated route
  // to display.
  if (state.generatedLayer) return;
  const pts = state.waypoints
    .filter(w => w.included !== 0 && w.lat != null && w.lon != null)
    .map(w => [w.lat, w.lon]);
  if (pts.length < 2) return;
  state.previewLine = L.polyline(pts, {
    color: state.previewColor, weight: 3, opacity: 0.85, dashArray: '6 8', interactive: false,
  }).addTo(state.map);
  if (state.previewLine.bringToBack) state.previewLine.bringToBack();
}

function clearGeneratedLayer(state) {
  if (state.generatedLayer) { state.map.removeLayer(state.generatedLayer); state.generatedLayer = null; }
  if (state.warningOverlays) {
    for (const ov of state.warningOverlays) state.map.removeLayer(ov);
    state.warningOverlays = null;
  }
}

// -------------------- gradient-warning overlay (M3c) --------------------
//
// For every leg whose response carries a `warnings` array, overlay a
// thicker red polyline on top of the original at each warning span.
// Offsets are metre-distances along the leg's decoded latlngs —
// compute cumulative distance once per leg so the slice is cheap.

function drawWarningOverlay(state, leg, latlngs) {
  if (!leg || !leg.warnings || !leg.warnings.length) return;
  if (!state.warningOverlays) state.warningOverlays = [];
  const cum = [0];
  for (let i = 1; i < latlngs.length; i++) {
    cum.push(cum[i - 1] + haversineMeters(
      latlngs[i - 1][0], latlngs[i - 1][1],
      latlngs[i][0], latlngs[i][1],
    ));
  }
  for (const w of leg.warnings) {
    const slice = [];
    for (let i = 0; i < latlngs.length; i++) {
      if (cum[i] >= w.from_m && cum[i] <= w.to_m) slice.push(latlngs[i]);
    }
    if (slice.length < 2) continue;
    const overlay = L.polyline(slice, {
      color: '#ff3f2f', weight: 8, opacity: 0.7, interactive: false,
    }).addTo(state.map);
    state.warningOverlays.push(overlay);
  }
}

// -------------------- line-drag: insert waypoint mid-leg --------------------
//
// The user grabs the generated Valhalla polyline — NOT an existing pin —
// and drags to reshape the route. Per-leg routing gives every
// adjacent waypoint pair its own interactive polyline, so the line
// the user grabbed directly identifies where the new pin should go:
// immediately after leg.from_position.

function startLineDrag(state, line, mouseEvent) {
  // Don't interfere with right-click or Ctrl-click (context menu /
  // "drop a stop" in the map handler).
  const orig = mouseEvent.originalEvent;
  if (orig && (orig.button !== 0 || orig.ctrlKey || orig.shiftKey)) return;
  if (state.lineDrag) return;  // already dragging

  // Stop Leaflet's default behaviours — panning + polyline click.
  L.DomEvent.stopPropagation(mouseEvent);
  L.DomEvent.preventDefault(mouseEvent);
  state.map.dragging.disable();
  document.getElementById('map').classList.add('is-dragging-line');

  const ghost = L.circleMarker(mouseEvent.latlng, {
    radius: 7, className: 'route-drag-ghost',
    color: '#fff', weight: 2, fillColor: state.previewColor, fillOpacity: 0.9,
  }).addTo(state.map);

  const dragState = {
    ghost,
    fromPosition: line._legFromPosition,
    currentLatLng: mouseEvent.latlng,
  };
  state.lineDrag = dragState;

  function onMove(ev) {
    const pt = state.map.mouseEventToLatLng(ev);
    dragState.currentLatLng = pt;
    ghost.setLatLng(pt);
  }

  async function onUp() {
    cleanup();
    const { lat, lng } = dragState.currentLatLng;
    try {
      const snap = await maybeSnapToRoad(lat, lng);
      await api.insertWaypointAt(state.routeId, dragState.fromPosition + 1, {
        name: 'Waypoint',
        lat: snap.lat, lon: snap.lon,
        kind: 'waypoint',
        linked_to_previous: 1,
      });
      await onWaypointsChanged(state, state.editor);
    } catch (err) {
      console.error('line-drag insert failed', err);
      setStatus('Insert failed: ' + err.message, 'error');
    }
  }

  function cleanup() {
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
    state.map.dragging.enable();
    document.getElementById('map').classList.remove('is-dragging-line');
    if (ghost) state.map.removeLayer(ghost);
    state.lineDrag = null;
  }

  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
}

function drawGeneratedRoute(state, legs) {
  clearGeneratedLayer(state);
  if (!legs || !legs.length) return;

  // Stash on state so annotateWaypointsWithLegWarnings can reach them
  // without threading through every call site.
  state.legs = legs;

  // Per-leg routing: one interactive polyline per adjacent waypoint
  // pair, tagged with its from_position. Line-drag reads that tag
  // directly — no segment projection needed.
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
    // M3c: lay red overlay over any sub-segment whose smoothed gradient
    // crossed max_gradient_warn at /generate time.
    drawWarningOverlay(state, leg, latlngs);
  });
  if (!drewAnyLeg) return;
  group.addTo(state.map);
  state.generatedLayer = group;
  // Generated route just landed — hide the dashed preview underneath.
  updatePreviewLine(state);
}

function applyColors(state) {
  if (state.previewLine) state.previewLine.setStyle({ color: state.previewColor });
  if (state.generatedLayer) {
    // generatedLayer is a featureGroup of per-leg polylines now.
    state.generatedLayer.eachLayer(l => l.setStyle({ color: state.routeColor }));
  }
}

// -------------------- pin context menu --------------------
//
// Right-click on a map marker opens this. Items are built on the fly from
// the waypoint's current state (kind, included). Delete uses a two-step
// inline confirmation so the menu stays out of modal territory.

let ctxDeleteArmed = null;  // waypoint id that has been armed for deletion

function closePinContextMenu() {
  const menu = document.getElementById('pin-ctx-menu');
  menu.style.display = 'none';
  menu.innerHTML = '';
  ctxDeleteArmed = null;
}

function openPinContextMenu(state, editor, w, leafletEvt) {
  const menu = document.getElementById('pin-ctx-menu');
  const isStop = w.kind === 'stop';
  const included = w.included !== 0;
  const isStart = w.pin_role === 'start';
  const isEnd = w.pin_role === 'end';
  const linked = w.linked_to_previous === 1;
  const linkEntry = isStop
    ? ''
    : (linked
        ? '<button data-act="unlink" type="button">Unlink from previous</button>'
        : '<button data-act="relink" type="button">Re-link to previous</button>');

  menu.innerHTML = `
    <div class="ctx-header">${escapeHtml(w.name || (isStop ? 'Stop' : 'Waypoint'))}</div>
    <button data-act="set-start" type="button">${isStart ? 'Unset as Start' : 'Set as Start'}</button>
    <button data-act="set-end" type="button">${isEnd ? 'Unset as End' : 'Set as End'}</button>
    <div class="ctx-sep"></div>
    <button data-act="toggle-kind" type="button">${isStop ? 'Mark as Waypoint' : 'Mark as Stop'}</button>
    <button data-act="toggle-include" type="button">${included ? 'Exclude from route' : 'Include in route'}</button>
    ${linkEntry}
    ${isStop ? '<button data-act="edit-stop" type="button">Edit stop details…</button>' : ''}
    <div class="ctx-sep"></div>
    <button data-act="delete" type="button" class="danger">Delete</button>
  `;

  // Position at the cursor. Leaflet events wrap the DOM event in
  // `.originalEvent`; a native contextmenu event IS the DOM event
  // itself — support both.
  const ev = leafletEvt?.originalEvent ?? leafletEvt;
  if (ev && ev.clientX != null) {
    menu.style.left = ev.clientX + 'px';
    menu.style.top = ev.clientY + 'px';
  }
  menu.style.display = 'block';
  // Keep the menu inside the viewport (small screens / bottom-sheet rows).
  const mr = menu.getBoundingClientRect();
  const maxL = Math.max(0, window.innerWidth - mr.width - 4);
  const maxT = Math.max(0, window.innerHeight - mr.height - 4);
  if (mr.left > maxL) menu.style.left = maxL + 'px';
  if (mr.top > maxT) menu.style.top = maxT + 'px';

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
        await onWaypointsChanged(state, editor);
        return;
      }

      closePinContextMenu();
      if (act === 'toggle-kind') {
        const nextKind = isStop ? 'waypoint' : 'stop';
        await api.patchWaypoint(state.routeId, w.id, { kind: nextKind });
        await onWaypointsChanged(state, editor);
      } else if (act === 'toggle-include') {
        await api.patchWaypoint(state.routeId, w.id, { included: included ? 0 : 1 });
        await onWaypointsChanged(state, editor);
      } else if (act === 'set-start') {
        // Mutual exclusion — if another row already has role=start,
        // clear it first so the server never sees two rows with the
        // same pin_role.
        const nextRole = isStart ? null : 'start';
        if (nextRole) {
          const current = state.waypoints.find(x => x.pin_role === 'start' && x.id !== w.id);
          if (current) await api.patchWaypoint(state.routeId, current.id, { pin_role: null });
        }
        await api.patchWaypoint(state.routeId, w.id, { pin_role: nextRole });
        await onWaypointsChanged(state, editor);
      } else if (act === 'set-end') {
        const nextRole = isEnd ? null : 'end';
        if (nextRole) {
          const current = state.waypoints.find(x => x.pin_role === 'end' && x.id !== w.id);
          if (current) await api.patchWaypoint(state.routeId, current.id, { pin_role: null });
        }
        await api.patchWaypoint(state.routeId, w.id, { pin_role: nextRole });
        await onWaypointsChanged(state, editor);
      } else if (act === 'unlink') {
        await api.patchWaypoint(state.routeId, w.id, { linked_to_previous: 0 });
        await onWaypointsChanged(state, editor);
      } else if (act === 'relink') {
        await api.patchWaypoint(state.routeId, w.id, { linked_to_previous: 1 });
        await onWaypointsChanged(state, editor);
      } else if (act === 'edit-stop') {
        openStopEditModal(state, editor, w);
      }
    });
  });
}

// Click anywhere outside the menu dismisses it.
document.addEventListener('click', (e) => {
  const menu = document.getElementById('pin-ctx-menu');
  if (menu && menu.style.display !== 'none' && !menu.contains(e.target)) {
    closePinContextMenu();
  }
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closePinContextMenu();
});

// -------------------- stop edit modal --------------------

function openStopEditModal(state, editor, w) {
  const overlay = document.getElementById('stop-edit-overlay');
  const nameInput = document.getElementById('stop-edit-name');
  const descInput = document.getElementById('stop-edit-description');
  const arrivalInput = document.getElementById('stop-edit-arrival');
  const saveBtn = document.getElementById('stop-edit-save');
  const cancelBtn = document.getElementById('stop-edit-cancel');

  nameInput.value = w.name || '';
  descInput.value = w.description || '';
  arrivalInput.value = isoToLocalInput(w.arrival_time);
  overlay.style.display = 'flex';
  nameInput.focus();
  nameInput.select();

  // Replace listeners (cleanest way when re-opened for a different stop).
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
    await onWaypointsChanged(state, editor);
  };
  const cancel = () => { overlay.style.display = 'none'; cleanup(); };
  const keyHandler = (e) => {
    if (e.key === 'Escape') cancel();
    else if (e.key === 'Enter' && !e.shiftKey && e.target.tagName !== 'TEXTAREA') save();
  };
  function cleanup() {
    saveBtn.removeEventListener('click', save);
    cancelBtn.removeEventListener('click', cancel);
    overlay.removeEventListener('keydown', keyHandler);
  }
  saveBtn.addEventListener('click', save);
  cancelBtn.addEventListener('click', cancel);
  overlay.addEventListener('keydown', keyHandler);
}

function isoToLocalInput(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  // datetime-local expects YYYY-MM-DDTHH:mm in local time.
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// -------------------- initial page-load draw --------------------
//
// On page reload there may already be a set of waypoints AND a previously-
// generated set of route_legs in the DB. Drawing the cached legs immediately
// gives the user the road-snapped route on arrival — no waypoint-edit
// required, no Valhalla call. If the cache is empty AND auto-generate is
// on, leading-edge fires a fresh call right away.

async function initialRouteDraw(state) {
  // Arriving straight from "Convert to recipe": do not auto-generate on this
  // first load (it would overwrite the uploaded track). Strip the flag so a
  // later reload behaves normally.
  const url = new URL(window.location.href);
  const justConverted = url.searchParams.get('converted') === '1';
  if (url.searchParams.has('converted')) {
    url.searchParams.delete('converted');
    history.replaceState(null, '', url.pathname + url.search + url.hash);
  }
  if (state.waypoints.length < 2) return;
  try {
    const resp = await fetch(`/api/routes/${state.routeId}/legs`);
    if (resp.ok) {
      const legs = await resp.json();
      if (legs.length > 0) {
        drawGeneratedRoute(state, legs);
        state.generatedVersion = state.currentVersion;  // mark fresh
        setStatus(`Ready · cached (${legs.length} leg${legs.length > 1 ? 's' : ''})`, 'ok');
        return;
      }
    }
  } catch (_) { /* fall through */ }
  if (state.autoGenerate && !justConverted) {
    maybeFireGenerate(state);
    ensureRenderLoop(state);
  }
}

// -------------------- waypoint reload + change version bump --------------------

function annotateWaypointsWithLegWarnings(waypoints, legs) {
  // Decorate each waypoint with `_leg_warning_peak` iff the leg arriving
  // at this waypoint carries any gradient warnings. The editor reads
  // this synthetic field and renders a ⚠️ badge — see waypoint-editor.js.
  const byTo = new Map();
  for (const leg of (legs || [])) {
    if (leg.warnings && leg.warnings.length > 0) {
      const peak = Math.max(...leg.warnings.map(w => w.peak_grad_pct));
      byTo.set(leg.to_position, peak);
    }
  }
  return waypoints.map(w => ({
    ...w,
    _leg_warning_peak: byTo.has(w.position) ? byTo.get(w.position) : null,
  }));
}

async function reloadWaypoints(state, editor, { bump = true } = {}) {
  state.waypoints = await api.listWaypoints(state.routeId);
  if (bump) state.currentVersion += 1;
  editor.setWaypoints(annotateWaypointsWithLegWarnings(state.waypoints, state.legs));
  state.markers = renderMarkers(
    state.map, state.waypoints, state.markers,
    {
      draggable: true,
      onDragEnd: async (w, { lat, lon }) => {
        const snap = await maybeSnapToRoad(lat, lon);
        await api.patchWaypoint(state.routeId, w.id, { lat: snap.lat, lon: snap.lon });
        await onWaypointsChanged(state, editor);
      },
      onContextMenu: (w, evt) => {
        openPinContextMenu(state, editor, w, evt);
      },
    },
  );
  // If waypoints changed since last successful generate, the generated track
  // is stale — drop it so the user isn't looking at a line that no longer
  // matches their stops. Must happen BEFORE updatePreviewLine so the preview
  // can reappear once the generated layer is gone.
  if (state.generatedVersion !== state.currentVersion) {
    clearGeneratedLayer(state);
  }
  updatePreviewLine(state);
}

async function onWaypointsChanged(state, editor) {
  await reloadWaypoints(state, editor);
  if (state.autoGenerate && state.waypoints.length >= 2) {
    maybeFireGenerate(state);   // fires immediately if eligible; queues otherwise
    ensureRenderLoop(state);
  } else if (state.waypoints.length < 2) {
    // Dropped below threshold — cancel any cooldown so the button returns to
    // idle state; also clear the pending flag so nothing fires later.
    cancelCooldownTimer(state);
    state.cooldownStartedAt = null;
    state.cooldownDeadline = null;
    state.pendingChange = false;
  }
  renderGenerateControl(state);
}

// -------------------- generate state machine --------------------

function setStatus(text, cls = 'idle') {
  const el = document.getElementById('generate-status');
  el.textContent = text;
  el.className = `gen-status-${cls}`;
}

function clearError() { document.getElementById('generate-error').style.display = 'none'; }

// Translate known Valhalla errors into actionable guidance. Leave unknown
// errors alone — the upstream body is still shown so we don't hide info.
function guidanceForValhallaBody(body) {
  if (!body) return null;
  if (body.includes('"error_code":499') || body.includes('Could not find candidate edge')) {
    return 'Valhalla couldn\'t snap one of your pins to its road network. This usually means the pin is off-road (e.g. in a park without tagged trails, in water, or too far from any cycleable road). Try dragging the affected pin closer to a road and regenerating.';
  }
  if (body.includes('"error_code":171') || body.includes('No suitable edges near location')) {
    return 'Valhalla couldn\'t find any cycleable road near one of your pins. Move the pin closer to a road.';
  }
  if (body.includes('"error_code":170') || body.includes('No path could be found')) {
    return 'Valhalla found edges near each pin but couldn\'t build a connected path — the route may be blocked by a disconnected network segment or water crossing. Try adding an intermediate waypoint to steer through a passable area.';
  }
  return null;
}

function showError(err) {
  const el = document.getElementById('generate-error');
  const guidance = guidanceForValhallaBody(err.upstreamBody);
  const guidanceHtml = guidance ? `<div class="err-guidance">${escapeHtml(guidance)}</div>` : '';
  const upstream = err.upstreamUrl ? `<div class="err-upstream">Upstream: ${escapeHtml(err.upstreamUrl)}${err.upstreamBody ? `\n\n${escapeHtml(err.upstreamBody)}` : ''}</div>` : '';
  const detail = err.detail && !err.upstreamUrl ? `<div class="err-upstream">${escapeHtml(err.detail)}</div>` : '';
  el.innerHTML = `
    <button class="err-dismiss" type="button" title="Dismiss">&times;</button>
    <strong>Route generation failed.</strong>
    <span class="err-source">(backend endpoint ${escapeHtml(err.endpoint || '/api/routes/?/generate')} returned ${err.status ?? '—'})</span>
    ${guidanceHtml}
    ${upstream || detail}
  `;
  el.querySelector('.err-dismiss').addEventListener('click', clearError);
  el.style.display = 'block';
}

function escapeHtml(s) {
  return String(s || '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// maybeFireGenerate is the single entry point from auto mode and manual clicks.
// It decides immediately whether to fire, defer until cooldown ends, or
// enqueue for the next eligible moment.
function maybeFireGenerate(state, { bypassCooldown = false } = {}) {
  if (state.waypoints.length < 2) return;
  if (state.importing) {
    state.pendingChange = true;   // picked up when the CSV import finishes
    return;
  }
  if (state.isGenerating) {
    state.pendingChange = true;   // picked up after the in-flight call lands
    return;
  }
  if (!bypassCooldown && inCooldown(state)) {
    state.pendingChange = true;   // picked up when the cooldown timer fires
    return;
  }
  state.pendingChange = false;
  // Cancel any scheduled cooldown-end callback — doGenerate will start a
  // fresh cooldown on completion.
  cancelCooldownTimer(state);
  doGenerate(state);
}

function inCooldown(state) {
  return state.cooldownDeadline != null && state.cooldownDeadline > Date.now();
}

function cancelCooldownTimer(state) {
  if (state.cooldownTimer) {
    clearTimeout(state.cooldownTimer);
    state.cooldownTimer = null;
  }
}

function startCooldown(state) {
  cancelCooldownTimer(state);
  const now = Date.now();
  state.cooldownStartedAt = now;
  state.cooldownDeadline = now + state.debounceMs;
  state.cooldownTimer = setTimeout(() => {
    state.cooldownTimer = null;
    state.cooldownStartedAt = null;
    state.cooldownDeadline = null;
    // If a waypoint edit happened while we were cooling down, fire now.
    if (state.pendingChange && state.autoGenerate && !state.importing && state.waypoints.length >= 2) {
      state.pendingChange = false;
      doGenerate(state);
    } else {
      renderGenerateControl(state);
    }
  }, state.debounceMs);
  ensureRenderLoop(state);
  renderGenerateControl(state);
}

// tryGenerate is kept as a thin alias used by the "Generate Now" menu action
// (which bypasses the auto cooldown) and by the primary click in manual mode.
function tryGenerate(state) {
  maybeFireGenerate(state, { bypassCooldown: true });
}

async function doGenerate(state) {
  if (state.waypoints.length < 2) {
    setStatus('Need ≥ 2 waypoints', 'err');
    return;
  }
  state.isGenerating = true;
  const version = state.currentVersion;
  setStatus('Generating…', 'busy');
  clearError();
  renderGenerateControl(state);
  try {
    const endpoint = `/api/routes/${state.routeId}/generate`;
    const resp = await fetch(endpoint, { method: 'POST' });
    const text = await resp.text();
    let body;
    try { body = JSON.parse(text); } catch { body = { raw: text }; }

    if (!resp.ok) {
      showError({
        endpoint,
        status: resp.status,
        detail: body.detail || body.error || text,
        upstreamUrl: body.upstream_url,
        upstreamBody: body.upstream_body,
      });
      setStatus(`Error ${resp.status}`, 'err');
      return;
    }
    // Success — draw route, update status.
    state.generatedVersion = version;
    if (version === state.currentVersion) {
      drawGeneratedRoute(state, body.legs || []);
      // Editor re-paint so gradient-warning badges (M3c) land on the
      // receiving rows. drawGeneratedRoute already stashed state.legs.
      if (state.editor) {
        state.editor.setWaypoints(
          annotateWaypointsWithLegWarnings(state.waypoints, state.legs),
        );
      }
    } else {
      // Waypoints were changed while the generate was in flight — drop this
      // stale result and let the debounce timer kick another round.
      clearGeneratedLayer(state);
      if (state.autoGenerate) scheduleGenerate(state);
    }
    const km = body.distance_km?.toFixed ? body.distance_km.toFixed(1) : '?';
    const mins = body.duration_s ? Math.round(body.duration_s / 60) : '?';
    setStatus(`Ready · ${km} km · ${mins} min`, 'ok');
  } catch (err) {
    showError({
      endpoint: `/api/routes/${state.routeId}/generate`,
      status: '—',
      detail: err.message,
    });
    setStatus('Network error', 'err');
  } finally {
    state.isGenerating = false;
    // Start the cooldown regardless of success/failure so we don't hammer
    // Valhalla with the same broken request while the user is still
    // editing. If a waypoint change landed during the call, it'll fire
    // automatically at cooldown end (via the startCooldown timer).
    if (state.autoGenerate) {
      startCooldown(state);
    }
    renderGenerateControl(state);
  }
}

// -------------------- split-button render --------------------
//
// Visual states of #generate-control (data-variant):
//   manual   — auto OFF. Button is "⚡ Generate Now". Default orange/red.
//   ready    — auto ON, nothing pending. Green. Label "Auto-gen ready".
//   debounce — auto ON, pending timer running. Grey with circular countdown.
//   rate     — rate-limited waiting. Amber with countdown.
//   busy     — /generate call in flight. Red, primary disabled.
//
// Countdown circle: SVG circle with stroke-dasharray 88 (≈ 2π·14); we animate
// stroke-dashoffset from 0 (full) to 88 (empty) as the deadline approaches.

function renderGenerateControl(state) {
  const ctrl = document.getElementById('generate-control');
  const primary = document.getElementById('btn-gen-primary');
  const icon = document.getElementById('gen-primary-icon');
  const label = document.getElementById('gen-primary-label');
  const countdownWrap = document.getElementById('gen-primary-countdown');
  const progress = countdownWrap.querySelector('circle.progress');

  // The label stays "Generate Now" in every non-busy state; the variant
  // (and the circular countdown) tells the user what's happening. Colour:
  //   manual   red    (auto OFF)
  //   ready    green  (auto ON, no cooldown running, can fire)
  //   cooldown grey   (auto ON, waiting out the cooldown after a generate)
  //   busy     red    (generate in flight, disabled)
  let variant, iconText, labelText, disabled = false, showCountdown = false;

  if (state.isGenerating) {
    variant = 'busy'; iconText = '⏳'; labelText = 'Generating…'; disabled = true;
  } else if (state.importing) {
    // CSV import in flight: the waypoint list is changing under us.
    variant = state.autoGenerate ? 'ready' : 'manual';
    iconText = '⚡'; labelText = 'Generate Now'; disabled = true;
  } else if (state.autoGenerate && state.cooldownTimer && inCooldown(state)) {
    variant = 'cooldown'; iconText = '';
    labelText = 'Generate Now';
    showCountdown = true;
  } else if (state.autoGenerate) {
    variant = 'ready'; iconText = '⚡'; labelText = 'Generate Now';
  } else {
    variant = 'manual'; iconText = '⚡'; labelText = 'Generate Now';
  }

  ctrl.dataset.variant = variant;
  icon.textContent = iconText;
  icon.style.display = iconText ? '' : 'none';
  label.textContent = labelText;
  countdownWrap.style.display = showCountdown ? 'inline-block' : 'none';
  primary.disabled = disabled;

  if (showCountdown && state.cooldownStartedAt != null && state.cooldownDeadline != null) {
    const total = Math.max(1, state.cooldownDeadline - state.cooldownStartedAt);
    const remaining = Math.max(0, state.cooldownDeadline - Date.now());
    const progressPct = 1 - remaining / total; // 0→1 as timer runs out
    const CIRCUM = 88;
    progress.style.strokeDashoffset = String(progressPct * CIRCUM);
  } else {
    progress.style.strokeDashoffset = '0';
  }

  primary.title = {
    manual: 'Generate the route now',
    ready: 'Auto-generate ON — edits fire immediately. Click to turn auto off.',
    cooldown: 'Auto-generate ON — cooling down before the next call. Click to turn auto off, or use ▾ → Generate Now to skip the wait.',
    busy: 'Generating…',
  }[variant] || '';
}

function startRenderLoop(state) {
  // Refresh button + countdown every 150 ms while a timer is pending.
  // Cheap; the function is no-op when nothing's pending.
  if (state.renderLoopActive) return;
  state.renderLoopActive = true;
  const tick = () => {
    renderGenerateControl(state);
    if (state.cooldownTimer || state.isGenerating) {
      state.renderTimer = setTimeout(tick, 150);
    } else {
      state.renderLoopActive = false;
      state.renderTimer = null;
    }
  };
  tick();
}

function ensureRenderLoop(state) {
  if ((state.cooldownTimer || state.isGenerating) && !state.renderLoopActive) {
    startRenderLoop(state);
  }
}

// -------------------- dropdown menu --------------------

function openMenu(state) {
  const menu = document.getElementById('gen-menu');
  const ctrl = document.getElementById('generate-control');
  buildMenu(state);
  menu.style.display = 'block';
  const rect = ctrl.getBoundingClientRect();
  menu.style.top = `${rect.bottom + 4}px`;
  menu.style.left = `${rect.right - menu.offsetWidth}px`;
  document.getElementById('btn-gen-dropdown').setAttribute('aria-expanded', 'true');
}

function closeMenu() {
  const menu = document.getElementById('gen-menu');
  menu.style.display = 'none';
  document.getElementById('btn-gen-dropdown').setAttribute('aria-expanded', 'false');
}

function colorsSectionHtml(state) {
  return `
    <div class="menu-section">
      <div class="menu-title">Line colours</div>
      <div class="menu-row menu-color-row">
        <label>Route</label>
        <input type="color" id="menu-route-color" value="${state.routeColor}">
        <button class="menu-reset" id="menu-route-color-reset" type="button" title="Reset to default">↺</button>
      </div>
      <div class="menu-row menu-color-row">
        <label>Preview</label>
        <input type="color" id="menu-preview-color" value="${state.previewColor}">
        <button class="menu-reset" id="menu-preview-color-reset" type="button" title="Reset to default">↺</button>
      </div>
    </div>`;
}

function wireColorsSection(state, menu) {
  const routeInput = menu.querySelector('#menu-route-color');
  const previewInput = menu.querySelector('#menu-preview-color');
  routeInput.addEventListener('input', (e) => {
    const c = validColor(e.target.value) || DEFAULT_ROUTE_COLOR;
    state.routeColor = c;
    applyColors(state);
    savePrefs(state);
  });
  previewInput.addEventListener('input', (e) => {
    const c = validColor(e.target.value) || DEFAULT_PREVIEW_COLOR;
    state.previewColor = c;
    applyColors(state);
    savePrefs(state);
  });
  menu.querySelector('#menu-route-color-reset').addEventListener('click', () => {
    state.routeColor = DEFAULT_ROUTE_COLOR;
    routeInput.value = DEFAULT_ROUTE_COLOR;
    applyColors(state);
    savePrefs(state);
  });
  menu.querySelector('#menu-preview-color-reset').addEventListener('click', () => {
    state.previewColor = DEFAULT_PREVIEW_COLOR;
    previewInput.value = DEFAULT_PREVIEW_COLOR;
    applyColors(state);
    savePrefs(state);
  });
}

function buildMenu(state) {
  const menu = document.getElementById('gen-menu');
  if (!state.autoGenerate) {
    // Auto OFF: Enable-auto button + line colours.
    menu.innerHTML = `
      <div class="menu-section">
        <button class="menu-btn" id="menu-enable-auto" type="button">
          Enable auto-generate
        </button>
        <div class="menu-hint">Auto mode regenerates immediately when waypoints change, then waits the debounce time before the next call.</div>
      </div>
      ${colorsSectionHtml(state)}`;
    menu.querySelector('#menu-enable-auto').addEventListener('click', () => {
      setAutoGenerate(state, true);
      closeMenu();
    });
    wireColorsSection(state, menu);
  } else {
    // Auto ON: debounce slider + Generate Now + line colours.
    const secs = Math.round(state.debounceMs / 1000);
    menu.innerHTML = `
      <div class="menu-section">
        <div class="menu-title">Debounce delay</div>
        <div class="menu-row">
          <input type="range" id="menu-debounce-slider" min="1" max="30" step="1" value="${secs}">
          <input type="number" id="menu-debounce-seconds" min="1" max="30" value="${secs}"> sec
        </div>
        <div class="menu-hint">Auto fires immediately on the first eligible change, then waits this long before the next call. Changes during the wait are collapsed into a single call at the end.</div>
      </div>
      <div class="menu-section">
        <button class="menu-btn primary" id="menu-generate-now" type="button">
          ⚡ Generate Now (skip cooldown)
        </button>
      </div>
      ${colorsSectionHtml(state)}`;
    const slider = menu.querySelector('#menu-debounce-slider');
    const num = menu.querySelector('#menu-debounce-seconds');
    function setSecs(v) {
      v = Math.max(1, Math.min(30, parseInt(v, 10) || 5));
      state.debounceMs = v * 1000;
      slider.value = String(v);
      num.value = String(v);
      savePrefs(state);
    }
    slider.addEventListener('input', (e) => setSecs(e.target.value));
    num.addEventListener('change', (e) => setSecs(e.target.value));
    menu.querySelector('#menu-generate-now').addEventListener('click', () => {
      cancelCooldownTimer(state);
      state.cooldownDeadline = null;
      state.cooldownStartedAt = null;
      maybeFireGenerate(state, { bypassCooldown: true });
      ensureRenderLoop(state);
      closeMenu();
    });
    wireColorsSection(state, menu);
  }
}

function setAutoGenerate(state, value) {
  state.autoGenerate = value;
  savePrefs(state);
  if (!value) {
    cancelCooldownTimer(state);
    state.cooldownStartedAt = null;
    state.cooldownDeadline = null;
    state.pendingChange = false;
    setStatus('Idle', 'idle');
  } else if (state.waypoints.length >= 2) {
    // Flipping to ON with an already-routeable recipe fires immediately.
    maybeFireGenerate(state);
    ensureRenderLoop(state);
  }
  renderGenerateControl(state);
}

// -------------------- settings persistence --------------------

function loadPrefs(state) {
  const savedAuto = localStorage.getItem(STORAGE_AUTO);
  const savedDebounce = parseInt(localStorage.getItem(STORAGE_DEBOUNCE) || '', 10);
  state.autoGenerate = savedAuto === '1';
  state.debounceMs = (Number.isFinite(savedDebounce) && savedDebounce >= 1000) ? savedDebounce : 5000;
  state.routeColor = validColor(localStorage.getItem(STORAGE_ROUTE_COLOR))   || DEFAULT_ROUTE_COLOR;
  state.previewColor = validColor(localStorage.getItem(STORAGE_PREVIEW_COLOR)) || DEFAULT_PREVIEW_COLOR;
}

function savePrefs(state) {
  localStorage.setItem(STORAGE_AUTO, state.autoGenerate ? '1' : '0');
  localStorage.setItem(STORAGE_DEBOUNCE, String(state.debounceMs));
  localStorage.setItem(STORAGE_ROUTE_COLOR, state.routeColor);
  localStorage.setItem(STORAGE_PREVIEW_COLOR, state.previewColor);
}

function validColor(v) {
  return (typeof v === 'string' && /^#[0-9a-fA-F]{6}$/.test(v)) ? v : null;
}

// -------------------- options UI (M3a) --------------------

async function initOptionsUI(state) {
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
  presetSelect.value = state.currentPreset || 'road';

  presetSelect.addEventListener('change', async () => {
    await api.patchRouteOptions(state.routeId, {
      costing_preset: presetSelect.value,
    });
    state.currentPreset = presetSelect.value;
    document.getElementById('custom-costing-panel').style.display =
      presetSelect.value === 'custom' ? 'flex' : 'none';
    markNeedsRegen(state);
  });

  document.getElementById('btn-toggle-custom').addEventListener('click', () => {
    const panel = document.getElementById('custom-costing-panel');
    panel.style.display = panel.style.display === 'none' ? 'flex' : 'none';
  });

  const rtCb = document.getElementById('route-round-trip');
  rtCb.addEventListener('change', async () => {
    await api.patchRouteOptions(state.routeId, { round_trip: rtCb.checked });
    markNeedsRegen(state);
  });

  const mgInput = document.getElementById('route-max-grad');
  mgInput.addEventListener('change', async () => {
    const v = mgInput.value === '' ? null : Number(mgInput.value);
    await api.patchRouteOptions(state.routeId, { max_gradient_warn: v });
    // Does NOT invalidate legs — M3c's post-processor re-runs on next
    // generate only.
  });

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

  // --- Optimise button (M3b) ---
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
}

function markNeedsRegen(state) {
  const gc = document.getElementById('generate-control');
  if (gc) gc.dataset.variant = 'ready';
  setStatus('Options changed — regenerate', 'ready');
}

// -------------------- main --------------------

// Mobile: secondary header controls collapse behind an Options toggle.
function initHeaderOptionsToggle() {
  const btn = document.getElementById('btn-header-more');
  const header = document.getElementById('create-header');
  if (!btn || !header) return;
  btn.addEventListener('click', () => {
    const open = !header.classList.contains('more-open');
    header.classList.toggle('more-open', open);
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (state_map()) state_map().invalidateSize();
  });
}
function state_map() { return window.__appState && window.__appState.map; }

async function main() {
  const state = {
    routeId: null,
    map: null,
    waypoints: [],
    markers: [],
    previewLine: null,
    generatedLayer: null,
    currentVersion: 0,
    generatedVersion: -1,
    autoGenerate: false,
    debounceMs: 5000,
    routeColor: DEFAULT_ROUTE_COLOR,
    previewColor: DEFAULT_PREVIEW_COLOR,
    // Cooldown / leading-edge state (trailing-edge fire happens automatically
    // when cooldownTimer expires with pendingChange=true).
    cooldownTimer: null,
    cooldownStartedAt: null,
    cooldownDeadline: null,
    pendingChange: false,
    isGenerating: false,
  };

  loadPrefs(state);

  // Capture the URL state *before* ensureRouteId rewrites it. The
  // Analysis nav button is meant for "I'm editing an existing route" —
  // freshly-created routes (where we assign the id here) shouldn't show
  // it yet, since the user hasn't generated a GPX to analyse.
  const arrivedWithRouteId = new URL(window.location.href)
    .searchParams.has('route_id');

  state.routeId = await ensureRouteId();
  state.map = initCreateMap('map');

  // Playwright + debug hook: expose state so tests can assert on or
  // nudge it without reimplementing the whole edit/generate cycle.
  window.__appState = state;

  const editor = mountWaypointEditor(
    document.getElementById('editor-panel'),
    {
      onReorder: async (orderedIds) => {
        await api.reorderWaypoints(state.routeId, orderedIds);
        await onWaypointsChanged(state, editor);
      },
      onRemove: async (wptId) => {
        await api.deleteWaypoint(state.routeId, wptId);
        await onWaypointsChanged(state, editor);
      },
      // Right-click on a sidebar row → open the same context menu the
      // map-marker right-click uses. Keeps behaviour identical whether
      // the user's hand is on the map or on the list.
      onContextMenu: (w, evt) => {
        openPinContextMenu(state, editor, w, evt);
      },
      // Collapse the whole sidebar, not just the widget inside — otherwise
      // the aside stays at 340 px and the map keeps a dark dead strip on
      // its right edge.
      //
      // After the DOM resize, Leaflet needs a nudge (invalidateSize) to
      // realise its container grew/shrank and load tiles for the newly-
      // uncovered area. Without this the user sees the map's #16213e
      // background showing through — which is exactly the "large dark
      // blue area" a user reported on the narrow viewport.
      onCollapseToggle: (isCollapsed) => {
        document.getElementById('editor-panel').classList.toggle('collapsed', isCollapsed);
        if (state.map) {
          // Match the 200 ms CSS transition so tiles fetch with the final size.
          setTimeout(() => state.map.invalidateSize(), 220);
        }
      },
    },
  );

  // Line-drag on the generated polyline (wired in drawGeneratedRoute)
  // needs to trigger the same downstream pipeline as other waypoint
  // edits. Stashing the editor on state avoids threading it through
  // every call site.
  state.editor = editor;
  initBottomSheet({ panel: document.getElementById('editor-panel'), map: state.map });
  initHeaderOptionsToggle();

  await initOptionsUI(state);

  await reloadWaypoints(state, editor, { bump: false });
  fitToWaypoints(state.map, state.waypoints);
  await initialRouteDraw(state);

  // --- Split-button wiring ---
  renderGenerateControl(state);

  // Primary button: action depends on current variant.
  //   - manual  → Generate Now (cancel any pending, trigger immediate)
  //   - ready / debounce / rate → turn auto OFF
  //   - busy    → disabled (no-op)
  document.getElementById('btn-gen-primary').addEventListener('click', () => {
    if (state.isGenerating) return;
    if (state.autoGenerate) {
      setAutoGenerate(state, false);
    } else {
      // Manual mode: fire immediately, bypass any lingering cooldown.
      cancelCooldownTimer(state);
      state.cooldownDeadline = null;
      state.cooldownStartedAt = null;
      maybeFireGenerate(state, { bypassCooldown: true });
      ensureRenderLoop(state);
    }
  });

  // CSV append: the route always exists by now (ensureRouteId at startup).
  document.getElementById('btn-import-csv').addEventListener('click', () => {
    const finish = async () => {
      if (!state.importing) return;
      state.importing = false;
      renderGenerateControl(state);
      await reloadWaypoints(state, editor);
      fitToWaypoints(state.map, state.waypoints.filter(w => w.included !== 0));
      if (state.autoGenerate && state.waypoints.length >= 2) {
        maybeFireGenerate(state);
        ensureRenderLoop(state);
      }
    };
    openCsvImport({
      routeId: state.routeId,
      defaultTitle: document.getElementById('route-title').value.trim(),
      onStart: () => {
        state.importing = true;
        renderGenerateControl(state);
        // Cancel/backdrop close mid-import never calls onDone; don't leave
        // Generate disabled. finish() is idempotent via state.importing.
        const overlay = document.getElementById('csv-import-overlay');
        if (overlay) {
          const mo = new MutationObserver(() => {
            if (!overlay.isConnected) { mo.disconnect(); finish(); }
          });
          mo.observe(document.body, { childList: true });
        }
      },
      onDone: finish,
    });
  });

  // Add by address: append a stop at the picked geocode result.
  initAddressSearch({
    input: document.getElementById('add-address'),
    list: document.getElementById('address-suggestions'),
    status: document.getElementById('address-status'),
    onSelect: async ({ name, address, lat, lon }) => {
      await api.appendWaypoint(state.routeId, { name, lat, lon, kind: 'stop', address });
      await onWaypointsChanged(state, editor);
      state.map.panTo([lat, lon]);
    },
  });

  // Dropdown arrow toggles the menu.
  document.getElementById('btn-gen-dropdown').addEventListener('click', (e) => {
    e.stopPropagation();
    const menu = document.getElementById('gen-menu');
    if (menu.style.display === 'none' || !menu.style.display) openMenu(state);
    else closeMenu();
  });
  document.addEventListener('click', (e) => {
    const menu = document.getElementById('gen-menu');
    if (menu.style.display === 'block'
        && !menu.contains(e.target)
        && e.target.id !== 'btn-gen-dropdown') {
      closeMenu();
    }
  });

  // --- Map click → append waypoint ---
  // state.clickCounter is a synchronous counter so that two clicks firing
  // before the first reloadWaypoints() returns still get distinct default
  // names. Initialised to the current waypoint count on load.
  state.clickCounter = state.waypoints.length;
  // A long-press on empty map has no menu in Create, but must not fall
  // through to tap-to-add when the finger lifts (iOS fires no contextmenu).
  onLongPress(state.map, () => {});
  state.map.on('click', async (e) => {
    if (longPressJustFired()) return;  // click synthesised after a long-press
    const n = ++state.clickCounter;
    // Ctrl+click (or Cmd+click on macOS) drops a stop, plain click drops a
    // waypoint. Keeps single-click fast for route shaping and makes the
    // destinations-intent explicit without a separate tool.
    const asStop = !!(e.originalEvent && (e.originalEvent.ctrlKey || e.originalEvent.metaKey));
    const kind = asStop ? 'stop' : 'waypoint';
    const snap = await maybeSnapToRoad(e.latlng.lat, e.latlng.lng);
    await api.appendWaypoint(state.routeId, {
      name: asStop ? `Stop ${n}` : `Waypoint ${n}`,
      lat: snap.lat, lon: snap.lon, kind,
    });
    await onWaypointsChanged(state, editor);
  });

  // --- Title blur → persist ---
  document.getElementById('route-title').addEventListener('blur', async (e) => {
    const title = e.target.value.trim();
    if (!title) return;
    await fetch(`/api/routes/${state.routeId}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    });
  });

  // --- Save (no-op; edits already persist per-action) ---
  document.getElementById('btn-save').addEventListener('click', () => {
    const btn = document.getElementById('btn-save');
    const orig = btn.textContent;
    btn.textContent = 'Saved ✓';
    setTimeout(() => { btn.textContent = orig; }, 1200);
  });

  // --- Analysis button: visible only when editing an existing route. ---
  // `arrivedWithRouteId` was captured before ensureRouteId ran, so this
  // distinguishes "user opened /create?route_id=<id>" (show) from "user
  // opened /create and we just assigned an id" (hide, nothing to analyse).
  const analysisBtn = document.getElementById('btn-open-analysis');
  if (arrivedWithRouteId && analysisBtn) {
    analysisBtn.href = `/route/${state.routeId}`;
    analysisBtn.style.display = '';
  }

  // --- Dirty-state prompt on navigation ---
  //
  // Auto-save keeps the recipe in sync with the server, but a "dirty"
  // state still exists between the last generate and subsequent edits:
  // the GPX Valhalla produced is stale until a fresh Regenerate runs.
  // Navigating to Library / Analysis in that window would show the user
  // a route that no longer matches their intent — so we prompt.

  function isDirty() {
    // No recipe-edit since last generate → clean.
    if (state.generatedVersion < 0) return false;
    return state.generatedVersion !== state.currentVersion;
  }

  async function guardNav(href, e) {
    if (!isDirty()) return true;  // let the link navigate normally
    e.preventDefault();
    const save = window.confirm(
      "You have edited this route but haven't regenerated the GPX yet.\n\n" +
      "OK — regenerate now, then leave.\n" +
      "Cancel — leave without regenerating (the destination will show the previously-generated route).",
    );
    if (save) {
      setStatus('Regenerating before leaving…', 'busy');
      try {
        await api.generateRoute(state.routeId);
      } catch (err) {
        const leave = window.confirm('Regenerate failed: ' + err.message + '\n\nLeave anyway?');
        if (!leave) return false;
      }
    }
    window.location.href = href;
    return false;
  }

  document.querySelectorAll('a[href="/"], a#btn-open-analysis').forEach(link => {
    link.addEventListener('click', (e) => guardNav(link.href, e));
  });

  // Catch-all: browser close / reload / external link. Shows the native
  // browser "Leave site?" dialog — no custom UI, but protects from data loss.
  window.addEventListener('beforeunload', (e) => {
    if (isDirty()) {
      e.preventDefault();
      e.returnValue = '';   // Chrome requires a truthy returnValue.
    }
  });

  // Set AFTER every listener has been wired so Playwright can deterministically
  // wait for the page to be fully interactive.
  window.__appReady = true;
}

main().catch(err => {
  console.error(err);
  const el = document.getElementById('generate-error');
  if (el) {
    el.innerHTML = `<strong>Create page failed to load.</strong> <span class="err-source">${escapeHtml(err.message)}</span>`;
    el.style.display = 'block';
  }
});
