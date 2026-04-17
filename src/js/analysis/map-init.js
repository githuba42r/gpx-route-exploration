// --- Leaflet map initialization, tile layers, layer persistence, base route ---

import { storageKey } from './storage.js';
import { attachTileLayers } from '../shared/map-layers.js';

/**
 * Create and configure the Leaflet map with tile layers and base route line.
 * Returns { map, baseRoute }.
 */
export function initMap(points) {
  const savedView = JSON.parse(localStorage.getItem(storageKey('map-view')) || 'null');
  const map = L.map('map', { zoomControl: true });

  attachTileLayers(map, { defaultBase: 'OSM Standard', defaultOverlays: [] });

  // Base route line (thin, always visible, neutral colour)
  const baseRoute = L.polyline(
    points.map(p => [p.lat, p.lon]),
    { color: '#ff5f15', weight: 2, opacity: 0.7 }
  ).addTo(map);

  // Restore saved view or fit to track bounds
  if (savedView) {
    map.setView([savedView.lat, savedView.lng], savedView.zoom);
  } else {
    const bounds = L.latLngBounds(points.map(p => [p.lat, p.lon]));
    map.fitBounds(bounds, { padding: [30, 30] });
  }

  map.on('moveend', () => {
    const c = map.getCenter();
    localStorage.setItem(storageKey('map-view'), JSON.stringify({
      lat: c.lat, lng: c.lng, zoom: map.getZoom()
    }));
  });

  return { map, baseRoute };
}
