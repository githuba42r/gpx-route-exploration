// --- Leaflet map init for the Create page ---

export function initCreateMap(elId) {
  const map = L.map(elId, { zoomControl: true });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19,
  }).addTo(map);
  map.setView([-27.4705, 153.0260], 11);
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
