// --- Leaflet map init for the Create page ---

import { attachTileLayers } from '../shared/map-layers.js';
import { storageKey } from '../analysis/storage.js';

const DEFAULT_CENTER = [-27.4705, 153.0260];
const DEFAULT_ZOOM = 11;

export function initCreateMap(elId) {
  const map = L.map(elId, { zoomControl: true });

  // Create page defaults: bike-friendly base + cycling-routes overlay on.
  // User's picks override the defaults and persist via localStorage.
  attachTileLayers(map, {
    defaultBase: 'CyclOSM (Bicycle)',
    defaultOverlays: ['Cycling Routes'],
  });

  // Restore saved view or fall back to the configured default.
  const savedView = JSON.parse(localStorage.getItem(storageKey('map-view')) || 'null');
  if (savedView) {
    map.setView([savedView.lat, savedView.lng], savedView.zoom);
  } else {
    map.setView(DEFAULT_CENTER, DEFAULT_ZOOM);
  }

  map.on('moveend', () => {
    const c = map.getCenter();
    localStorage.setItem(storageKey('map-view'), JSON.stringify({
      lat: c.lat, lng: c.lng, zoom: map.getZoom()
    }));
  });

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
