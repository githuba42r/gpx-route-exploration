// --- Analysis-page inline Edit panel (M2) ---
//
// Mounts the shared waypoint-editor inside a slide-out aside, wired to the
// analysis page's existing Leaflet map. Edits persist immediately (same
// model as the Create page — auto-save). Regenerate re-runs Valhalla then
// reloads the analysis page so the existing init path picks up the new
// GPX + gradient data.

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
    const d = haversine(lat, lon, e.correlated_lat, e.correlated_lon);
    return d <= SNAP_MAX_M ? { lat: e.correlated_lat, lon: e.correlated_lon } : { lat, lon };
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

// Pin context menu — same behaviour as create/app.js. Factoring out can wait
// until a third caller appears.
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
        state.markDirty();
        return;
      }
      closePinContextMenu();
      if (act === 'toggle-kind') {
        await api.patchWaypoint(state.routeId, w.id, { kind: isStop ? 'waypoint' : 'stop' });
        await state.refresh(); state.markDirty();
      } else if (act === 'toggle-include') {
        await api.patchWaypoint(state.routeId, w.id, { included: included ? 0 : 1 });
        await state.refresh(); state.markDirty();
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
    state.markDirty();
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
 * @param {L.Map}  opts.map       — the Analysis page's existing Leaflet map
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
    isRegenerating: false,
    editor: null,
    markDirty: () => setStatus('Edits pending — click Regenerate', 'dirty'),
    refresh: async () => {
      state.waypoints = await api.listWaypoints(routeId);
      state.editor.setWaypoints(state.waypoints);
      state.markers = renderMarkers(map, state.waypoints, state.markers, {
        draggable: true,
        onDragEnd: async (w, { lat, lon }) => {
          const s = await maybeSnap(lat, lon);
          await api.patchWaypoint(routeId, w.id, { lat: s.lat, lon: s.lon });
          state.markDirty();
          await state.refresh();
        },
        onContextMenu: (w, evt) => openPinContextMenu(state, w, evt),
      });
      state.clickCounter = Math.max(state.clickCounter, state.waypoints.length);
    },
  };

  const overlay = document.getElementById('edit-panel-overlay');
  const editorEl = document.getElementById('edit-panel-editor');
  const closeBtn = document.getElementById('btn-close-edit');
  const regenBtn = document.getElementById('btn-regen-edit');

  state.editor = mountWaypointEditor(editorEl, {
    onReorder: async (ids) => {
      await api.reorderWaypoints(routeId, ids);
      state.markDirty();
      await state.refresh();
    },
    onRemove: async (wptId) => {
      await api.deleteWaypoint(routeId, wptId);
      state.markDirty();
      await state.refresh();
    },
  });

  const onMapClick = async (e) => {
    if (!overlay.classList.contains('open')) return;
    const asStop = !!(e.originalEvent && (e.originalEvent.ctrlKey || e.originalEvent.metaKey));
    const n = ++state.clickCounter;
    const s = await maybeSnap(e.latlng.lat, e.latlng.lng);
    await api.appendWaypoint(routeId, {
      name: asStop ? `Stop ${n}` : `Waypoint ${n}`,
      lat: s.lat, lon: s.lon, kind: asStop ? 'stop' : 'waypoint',
    });
    state.markDirty();
    await state.refresh();
  };

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
      // Full reload so the existing analysis init reads the new GPX + recomputes
      // gradients. In-place re-render is a polish target.
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
