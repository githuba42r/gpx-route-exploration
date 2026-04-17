// --- Shared Leaflet tile layers + overlay setup with localStorage persistence ---
//
// Used by both the Analysis page (existing routes, per-route prefs) and the
// Create page (new routes, global prefs). Storage keys are built via
// analysis/storage.js#storageKey which is per-route when <body data-route-id>
// is set, otherwise falls back to a global key — so a user's preferred layers
// on the Create page carry across sessions, and each viewed route can still
// have its own preference.

import { storageKey } from '../analysis/storage.js';

/**
 * Attach a full tile-layer + overlay setup to an already-created map.
 *
 * @param {L.Map} map
 * @param {Object} opts
 * @param {string}   opts.defaultBase      Base layer name to use when nothing is persisted.
 *                                         Must match a key in `baseLayers` below.
 * @param {string[]} opts.defaultOverlays  Overlay names to enable when nothing is persisted.
 *                                         Must be keys of `overlayLayers` below.
 * @returns {{ baseLayers, overlayLayers }} References to the layer maps (useful for tests).
 */
export function attachTileLayers(map, { defaultBase = 'OSM Standard', defaultOverlays = [] } = {}) {
  // --- Base layers ---
  const osmStandard = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19,
  });
  const osmCycle = L.tileLayer('https://{s}.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors &amp; CyclOSM',
    maxZoom: 20,
  });
  const openTopo = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors, SRTM | &copy; OpenTopoMap',
    maxZoom: 17,
  });
  const esriSatellite = L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    { attribution: '&copy; Esri, Maxar, Earthstar Geographics', maxZoom: 19 },
  );

  const baseLayers = {
    'OSM Standard':           osmStandard,
    'CyclOSM (Bicycle)':      osmCycle,
    'OpenTopoMap (Contours)': openTopo,
    'Satellite':              esriSatellite,
  };

  // --- Overlays ---
  const waymarkedHiking = L.tileLayer('https://tile.waymarkedtrails.org/hiking/{z}/{x}/{y}.png', {
    attribution: '&copy; Waymarked Trails',
    maxZoom: 18,
    opacity: 0.7,
  });
  const waymarkedCycling = L.tileLayer('https://tile.waymarkedtrails.org/cycling/{z}/{x}/{y}.png', {
    attribution: '&copy; Waymarked Trails',
    maxZoom: 18,
    opacity: 0.7,
  });

  const overlayLayers = {
    'Hiking Trails':   waymarkedHiking,
    'Cycling Routes':  waymarkedCycling,
  };

  // --- Restore saved preferences ---
  const savedBase = localStorage.getItem(storageKey('map-base-layer'));
  const savedOverlays = JSON.parse(localStorage.getItem(storageKey('map-overlays')) || 'null');

  const baseName = (savedBase && baseLayers[savedBase]) ? savedBase : defaultBase;
  baseLayers[baseName].addTo(map);

  const overlaysToEnable = savedOverlays !== null ? savedOverlays : defaultOverlays;
  overlaysToEnable.forEach(name => {
    if (overlayLayers[name]) overlayLayers[name].addTo(map);
  });

  // --- Layer control ---
  L.control.layers(baseLayers, overlayLayers, { position: 'topleft', collapsed: true }).addTo(map);

  // --- Persist on change ---
  map.on('baselayerchange', (e) => {
    localStorage.setItem(storageKey('map-base-layer'), e.name);
  });
  function persistOverlays() {
    const active = Object.keys(overlayLayers).filter(n => map.hasLayer(overlayLayers[n]));
    localStorage.setItem(storageKey('map-overlays'), JSON.stringify(active));
  }
  map.on('overlayadd', persistOverlays);
  map.on('overlayremove', persistOverlays);

  return { baseLayers, overlayLayers };
}
