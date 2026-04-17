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

// Global rate limit: minimum ms between successful /generate calls regardless
// of trigger (auto debounce or manual click).
const GLOBAL_RATE_LIMIT_MS = 5000;

const STORAGE_AUTO = 'gpx-create-auto-generate';
const STORAGE_DEBOUNCE = 'gpx-create-debounce-ms';

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
    color: '#00e5ff', weight: 3, opacity: 0.85, dashArray: '6 8', interactive: false,
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
    color: '#ff5f15', weight: 4, opacity: 0.9, interactive: false,
  }).addTo(state.map);
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
        await api.patchWaypoint(state.routeId, w.id, { lat, lon });
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
  if (state.autoGenerate) {
    scheduleGenerate(state);
    ensureRenderLoop(state);
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

function showError(err) {
  const el = document.getElementById('generate-error');
  const upstream = err.upstreamUrl ? `<div class="err-upstream">Upstream: ${escapeHtml(err.upstreamUrl)}${err.upstreamBody ? `\n\n${escapeHtml(err.upstreamBody)}` : ''}</div>` : '';
  const detail = err.detail ? `<div class="err-upstream">${escapeHtml(err.detail)}</div>` : '';
  el.innerHTML = `
    <button class="err-dismiss" type="button" title="Dismiss">&times;</button>
    <strong>Route generation failed.</strong>
    <span class="err-source">(backend endpoint ${escapeHtml(err.endpoint || '/api/routes/?/generate')} returned ${err.status ?? '—'})</span>
    ${upstream || detail}
  `;
  el.querySelector('.err-dismiss').addEventListener('click', clearError);
  el.style.display = 'block';
}

function escapeHtml(s) {
  return String(s || '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function scheduleGenerate(state) {
  if (state.pendingTimer) clearTimeout(state.pendingTimer);
  const delay = Math.max(0, state.debounceMs);
  state.pendingStartedAt = Date.now();
  state.pendingDeadline = state.pendingStartedAt + delay;
  setStatus(`Pending (${(delay / 1000).toFixed(1)}s)`, 'pending');
  state.pendingTimer = setTimeout(() => {
    state.pendingTimer = null;
    state.pendingStartedAt = null;
    state.pendingDeadline = null;
    tryGenerate(state);
  }, delay);
  renderGenerateControl(state);
}

function cancelPending(state) {
  if (state.pendingTimer) {
    clearTimeout(state.pendingTimer);
    state.pendingTimer = null;
    state.pendingStartedAt = null;
    state.pendingDeadline = null;
  }
}

async function tryGenerate(state) {
  if (state.isGenerating) {
    // Someone's mid-flight. Reschedule a small nudge ahead.
    state.pendingStartedAt = Date.now();
    state.pendingDeadline = state.pendingStartedAt + 500;
    state.pendingTimer = setTimeout(() => {
      state.pendingTimer = null;
      state.pendingStartedAt = null;
      state.pendingDeadline = null;
      tryGenerate(state);
    }, 500);
    setStatus('Pending (in-flight)', 'pending');
    renderGenerateControl(state);
    return;
  }
  const elapsed = Date.now() - state.lastGenerateAt;
  if (elapsed < GLOBAL_RATE_LIMIT_MS) {
    const wait = GLOBAL_RATE_LIMIT_MS - elapsed;
    state.pendingStartedAt = Date.now();
    state.pendingDeadline = state.pendingStartedAt + wait;
    setStatus(`Rate-limited (${Math.ceil(wait / 1000)}s)`, 'rate');
    state.pendingTimer = setTimeout(() => {
      state.pendingTimer = null;
      state.pendingStartedAt = null;
      state.pendingDeadline = null;
      tryGenerate(state);
    }, wait);
    renderGenerateControl(state);
    return;
  }
  await doGenerate(state);
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
    state.lastGenerateAt = Date.now();
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

  let variant, iconText, labelText, disabled = false, showCountdown = false;

  if (state.isGenerating) {
    variant = 'busy'; iconText = '⏳'; labelText = 'Generating…'; disabled = true;
  } else if (state.autoGenerate && state.pendingTimer) {
    variant = (state.lastGenerateAt && Date.now() - state.lastGenerateAt < GLOBAL_RATE_LIMIT_MS)
      ? 'rate' : 'debounce';
    iconText = '';
    const remaining = Math.max(0, (state.pendingDeadline || 0) - Date.now());
    labelText = `${(remaining / 1000).toFixed(1)}s`;
    showCountdown = true;
  } else if (state.autoGenerate) {
    variant = 'ready'; iconText = '✓'; labelText = 'Auto-gen ready';
  } else {
    variant = 'manual'; iconText = '⚡'; labelText = 'Generate Now';
  }

  ctrl.dataset.variant = variant;
  icon.textContent = iconText;
  icon.style.display = iconText ? '' : 'none';
  label.textContent = labelText;
  countdownWrap.style.display = showCountdown ? 'inline-block' : 'none';
  primary.disabled = disabled;

  if (showCountdown && state.pendingStartedAt != null && state.pendingDeadline != null) {
    const total = Math.max(1, state.pendingDeadline - state.pendingStartedAt);
    const remaining = Math.max(0, state.pendingDeadline - Date.now());
    const progressPct = 1 - remaining / total; // 0→1 as timer runs out
    const CIRCUM = 88;
    progress.style.strokeDashoffset = String(progressPct * CIRCUM);
  } else {
    progress.style.strokeDashoffset = '0';
  }

  // Title tooltips convey the action that clicking the primary will take.
  primary.title = {
    manual: 'Generate the route now',
    ready: 'Click to disable auto-generate',
    debounce: 'Click to disable auto-generate (or pick Generate Now from the menu)',
    rate: 'Rate-limited — click to disable auto-generate',
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
    if (state.pendingTimer || state.isGenerating) {
      state.renderTimer = setTimeout(tick, 150);
    } else {
      state.renderLoopActive = false;
      state.renderTimer = null;
    }
  };
  tick();
}

function ensureRenderLoop(state) {
  if ((state.pendingTimer || state.isGenerating) && !state.renderLoopActive) {
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

function buildMenu(state) {
  const menu = document.getElementById('gen-menu');
  if (!state.autoGenerate) {
    // Auto OFF: only option is to turn auto ON.
    menu.innerHTML = `
      <div class="menu-section">
        <button class="menu-btn" id="menu-enable-auto" type="button">
          Enable auto-generate
        </button>
        <div class="menu-hint">Auto mode regenerates after waypoint edits, waiting the debounce time before calling Valhalla.</div>
      </div>`;
    menu.querySelector('#menu-enable-auto').addEventListener('click', () => {
      setAutoGenerate(state, true);
      closeMenu();
    });
  } else {
    // Auto ON: debounce slider + immediate Generate Now.
    const secs = Math.round(state.debounceMs / 1000);
    menu.innerHTML = `
      <div class="menu-section">
        <div class="menu-title">Debounce delay</div>
        <div class="menu-row">
          <input type="range" id="menu-debounce-slider" min="1" max="30" step="1" value="${secs}">
          <input type="number" id="menu-debounce-seconds" min="1" max="30" value="${secs}"> sec
        </div>
        <div class="menu-hint">Max 1 generate call per ${GLOBAL_RATE_LIMIT_MS / 1000} s globally.</div>
      </div>
      <div class="menu-section">
        <button class="menu-btn primary" id="menu-generate-now" type="button">
          ⚡ Generate Now (skip debounce)
        </button>
      </div>`;
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
      cancelPending(state);
      tryGenerate(state);
      ensureRenderLoop(state);
      closeMenu();
    });
  }
}

function setAutoGenerate(state, value) {
  state.autoGenerate = value;
  savePrefs(state);
  if (!value) {
    cancelPending(state);
    setStatus('Idle', 'idle');
  } else if (state.waypoints.length >= 2) {
    scheduleGenerate(state);
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
}

function savePrefs(state) {
  localStorage.setItem(STORAGE_AUTO, state.autoGenerate ? '1' : '0');
  localStorage.setItem(STORAGE_DEBOUNCE, String(state.debounceMs));
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
    pendingTimer: null,
    isGenerating: false,
    lastGenerateAt: 0,
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
      cancelPending(state);
      tryGenerate(state);
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
  state.map.on('click', async (e) => {
    const n = state.waypoints.length + 1;
    await api.appendWaypoint(state.routeId, {
      name: `Waypoint ${n}`, lat: e.latlng.lat, lon: e.latlng.lng, kind: 'waypoint',
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
