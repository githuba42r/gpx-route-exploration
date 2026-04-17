// --- Create Route page entry point ---

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

function updatePreviewLine(state) {
  // Dashed cyan line through included waypoints in order — "here's the shape
  // of your route before you pay Valhalla for it". Replaced by the real track
  // on the analysis page once Generate Route lands.
  const pts = state.waypoints
    .filter(w => w.included !== 0 && w.lat != null && w.lon != null)
    .map(w => [w.lat, w.lon]);

  if (state.previewLine) {
    state.map.removeLayer(state.previewLine);
    state.previewLine = null;
  }
  if (pts.length < 2) return;
  state.previewLine = L.polyline(pts, {
    color: '#00e5ff',
    weight: 3,
    opacity: 0.85,
    dashArray: '6 8',
    interactive: false,
  }).addTo(state.map);
  // Keep the dashed preview below the markers so they remain clickable.
  if (state.previewLine.bringToBack) state.previewLine.bringToBack();
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
      onContextMenu: async (w) => {
        const nextKind = w.kind === 'stop' ? 'waypoint' : 'stop';
        await api.patchWaypoint(state.routeId, w.id, { kind: nextKind });
        await reloadWaypoints(state, editor);
      },
    },
  );
  updatePreviewLine(state);
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
    previewLine: null,
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

  document.getElementById('pin-start-cb').addEventListener('change', async (e) => {
    if (state.waypoints.length === 0) return;
    const firstId = state.waypoints[0].id;
    await api.patchWaypoint(state.routeId, firstId,
                            { pin_role: e.target.checked ? 'start' : null });
    await reloadWaypoints(state, editor);
  });

  document.getElementById('route-title').addEventListener('blur', async (e) => {
    const title = e.target.value.trim();
    if (!title) return;
    await fetch(`/api/routes/${state.routeId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    });
  });

  document.getElementById('btn-save').addEventListener('click', () => {
    const btn = document.getElementById('btn-save');
    const orig = btn.textContent;
    btn.textContent = 'Saved ✓';
    setTimeout(() => { btn.textContent = orig; }, 1200);
  });

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
