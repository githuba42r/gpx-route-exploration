// --- Leaflet map initialization, tile layers, layer persistence, base route ---

import { storageKey } from './storage.js';

/**
 * Create and configure the Leaflet map with tile layers and base route line.
 * Returns { map, baseRoute }.
 */
export function initMap(points) {
  // Restore saved map view or use default
  const savedView = JSON.parse(localStorage.getItem(storageKey('map-view')) || 'null');
  const map = L.map('map', { zoomControl: true });

  // --- Tile layers ---
  const osmStandard = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19
  });

  const osmCycle = L.tileLayer('https://{s}.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors &amp; CyclOSM',
    maxZoom: 20
  });

  const openTopo = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors, SRTM | &copy; OpenTopoMap',
    maxZoom: 17
  });

  const esriSatellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    attribution: '&copy; Esri, Maxar, Earthstar Geographics',
    maxZoom: 19
  });

  // --- Overlays ---
  const waymarkedTrails = L.tileLayer('https://tile.waymarkedtrails.org/hiking/{z}/{x}/{y}.png', {
    attribution: '&copy; Waymarked Trails',
    maxZoom: 18,
    opacity: 0.7
  });

  const waymarkedCycling = L.tileLayer('https://tile.waymarkedtrails.org/cycling/{z}/{x}/{y}.png', {
    attribution: '&copy; Waymarked Trails',
    maxZoom: 18,
    opacity: 0.7
  });

  // Layer control
  const baseLayers = {
    'OSM Standard': osmStandard,
    'CyclOSM (Bicycle)': osmCycle,
    'OpenTopoMap (Contours)': openTopo,
    'Satellite': esriSatellite,
  };

  const overlayLayers = {
    'Hiking Trails': waymarkedTrails,
    'Cycling Routes': waymarkedCycling,
  };

  // Restore saved layer preferences
  const savedBase = localStorage.getItem(storageKey('map-base-layer'));
  const savedOverlays = JSON.parse(localStorage.getItem(storageKey('map-overlays')) || '[]');

  const activeBase = (savedBase && baseLayers[savedBase]) ? baseLayers[savedBase] : osmStandard;
  activeBase.addTo(map);

  savedOverlays.forEach(name => {
    if (overlayLayers[name]) overlayLayers[name].addTo(map);
  });

  L.control.layers(baseLayers, overlayLayers, { position: 'topleft', collapsed: true }).addTo(map);

  // Persist layer changes
  map.on('baselayerchange', (e) => {
    localStorage.setItem(storageKey('map-base-layer'), e.name);
  });
  map.on('overlayadd', () => {
    const active = Object.keys(overlayLayers).filter(n => map.hasLayer(overlayLayers[n]));
    localStorage.setItem(storageKey('map-overlays'), JSON.stringify(active));
  });
  map.on('overlayremove', () => {
    const active = Object.keys(overlayLayers).filter(n => map.hasLayer(overlayLayers[n]));
    localStorage.setItem(storageKey('map-overlays'), JSON.stringify(active));
  });

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

  // Persist map view on move/zoom
  map.on('moveend', () => {
    const c = map.getCenter();
    localStorage.setItem(storageKey('map-view'), JSON.stringify({
      lat: c.lat, lng: c.lng, zoom: map.getZoom()
    }));
  });

  return { map, baseRoute };
}
