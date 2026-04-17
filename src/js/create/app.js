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
import { mountWaypointEditor } from '../shared/waypoint-editor.js';
import { decodePolyline } from '../shared/polyline.js';
import * as api from '../shared/route-api.js';

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
  const pts = state.waypoints
    .filter(w => w.included !== 0 && w.lat != null && w.lon != null)
    .map(w => [w.lat, w.lon]);

  if (state.previewLine) { state.map.removeLayer(state.previewLine); state.previewLine = null; }
  if (pts.length < 2) return;
  state.previewLine = L.polyline(pts, {
    color: state.previewColor, weight: 3, opacity: 0.85, dashArray: '6 8', interactive: false,
  }).addTo(state.map);
  if (state.previewLine.bringToBack) state.previewLine.bringToBack();
}

function clearGeneratedLayer(state) {
  if (state.generatedLayer) { state.map.removeLayer(state.generatedLayer); state.generatedLayer = null; }
}

function drawGeneratedRoute(state, legs) {
  clearGeneratedLayer(state);
  const allLatLngs = [];
  for (const leg of legs) {
    if (!leg.polyline) continue;
    const decoded = decodePolyline(leg.polyline, 6);
    if (allLatLngs.length && decoded.length && allLatLngs[allLatLngs.length - 1][0] === decoded[0][0] &&
        allLatLngs[allLatLngs.length - 1][1] === decoded[0][1]) {
      decoded.shift();
    }
    for (const p of decoded) allLatLngs.push(p);
  }
  if (allLatLngs.length < 2) return;
  state.generatedLayer = L.polyline(allLatLngs, {
    color: state.routeColor, weight: 4, opacity: 0.9, interactive: false,
  }).addTo(state.map);
}

function applyColors(state) {
  if (state.previewLine) state.previewLine.setStyle({ color: state.previewColor });
  if (state.generatedLayer) state.generatedLayer.setStyle({ color: state.routeColor });
}

// -------------------- initial page-load draw --------------------
//
// On page reload there may already be a set of waypoints AND a previously-
// generated set of route_legs in the DB. Drawing the cached legs immediately
// gives the user the road-snapped route on arrival — no waypoint-edit
// required, no Valhalla call. If the cache is empty AND auto-generate is
// on, leading-edge fires a fresh call right away.

async function initialRouteDraw(state) {
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
  if (state.autoGenerate) {
    maybeFireGenerate(state);
    ensureRenderLoop(state);
  }
}

// -------------------- waypoint reload + change version bump --------------------

async function reloadWaypoints(state, editor, { bump = true } = {}) {
  state.waypoints = await api.listWaypoints(state.routeId);
  if (bump) state.currentVersion += 1;
  editor.setWaypoints(state.waypoints);
  state.markers = renderMarkers(
    state.map, state.waypoints, state.markers,
    {
      draggable: true,
      onDragEnd: async (w, { lat, lon }) => {
        const snap = await maybeSnapToRoad(lat, lon);
        await api.patchWaypoint(state.routeId, w.id, { lat: snap.lat, lon: snap.lon });
        await onWaypointsChanged(state, editor);
      },
      onContextMenu: async (w) => {
        const nextKind = w.kind === 'stop' ? 'waypoint' : 'stop';
        await api.patchWaypoint(state.routeId, w.id, { kind: nextKind });
        await onWaypointsChanged(state, editor);
      },
    },
  );
  updatePreviewLine(state);
  // If waypoints changed since last successful generate, the generated track
  // is stale — drop it so the user isn't looking at a line that no longer
  // matches their stops.
  if (state.generatedVersion !== state.currentVersion) {
    clearGeneratedLayer(state);
  }
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
    if (state.pendingChange && state.autoGenerate && state.waypoints.length >= 2) {
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

// -------------------- main --------------------

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
  state.routeId = await ensureRouteId();
  state.map = initCreateMap('map');

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
    },
  );

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
  state.map.on('click', async (e) => {
    const n = ++state.clickCounter;
    const snap = await maybeSnapToRoad(e.latlng.lat, e.latlng.lng);
    await api.appendWaypoint(state.routeId, {
      name: `Waypoint ${n}`, lat: snap.lat, lon: snap.lon, kind: 'waypoint',
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
}

main().catch(err => {
  console.error(err);
  const el = document.getElementById('generate-error');
  if (el) {
    el.innerHTML = `<strong>Create page failed to load.</strong> <span class="err-source">${escapeHtml(err.message)}</span>`;
    el.style.display = 'block';
  }
});
