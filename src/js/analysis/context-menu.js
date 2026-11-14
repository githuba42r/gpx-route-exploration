// --- Right-click context menu, waypoint CRUD, shared helpers ---

import { useAbsoluteMode, gradToAngle } from './gradient.js';
import { haversine } from './track-processor.js';
import { storageKey } from './storage.js';
import { showGradientModal, closeGradientModal } from './gradient-modal.js';
import { initTerrainGradient } from './terrain-gradient.js';
import { onLongPress } from '../shared/long-press.js';

/**
 * Shared context-menu state passed to modal sub-modules.
 */
function createSharedState() {
  return {
    ctxLatLng: null,
    ctxNearestIdx: null,
    ctxTargetWaypoint: null,
    modalMarkers: [],
  };
}

// --- Shared helpers (exported for gradient-modal and terrain-gradient) ---

export function findNearestPoint(points, latlng) {
  let bestIdx = 0, bestDist = Infinity;
  for (let i = 0; i < points.length; i++) {
    const d = (points[i].lat - latlng.lat) ** 2 + (points[i].lon - latlng.lng) ** 2;
    if (d < bestDist) { bestDist = d; bestIdx = i; }
  }
  return bestIdx;
}

export function findNearbyPeakGradient(points, latlng) {
  const nearestIdx = findNearestPoint(points, latlng);
  const nearestDist = haversine(latlng.lat, latlng.lng, points[nearestIdx].lat, points[nearestIdx].lon);
  const searchRadius = Math.max(50, nearestDist + 50);
  const degThresh = (searchRadius / 111000) * 1.5;

  let peakIdx = -1, peakAbsGrad = 0;
  for (let i = 1; i < points.length; i++) {
    const dlat = Math.abs(points[i].lat - latlng.lat);
    const dlon = Math.abs(points[i].lon - latlng.lng);
    if (dlat > degThresh || dlon > degThresh) continue;
    const dist = haversine(latlng.lat, latlng.lng, points[i].lat, points[i].lon);
    if (dist <= searchRadius) {
      const absG = Math.abs(points[i].gradient);
      if (absG > peakAbsGrad) {
        peakAbsGrad = absG;
        peakIdx = i;
      }
    }
  }

  return {
    idx: peakIdx >= 0 ? peakIdx : null,
    radius: Math.round(searchRadius),
    dist: peakIdx >= 0 ? haversine(latlng.lat, latlng.lng, points[peakIdx].lat, points[peakIdx].lon) : 0
  };
}

export function clearModalMarkers(map, shared) {
  shared.modalMarkers.forEach(m => map.removeLayer(m));
  shared.modalMarkers = [];
}

export function addModalMarker(map, shared, lat, lon, color, label) {
  const m = L.circleMarker([lat, lon], {
    radius: 8, color: '#fff', fillColor: color, fillOpacity: 1, weight: 2
  }).addTo(map);
  if (label) m.bindTooltip(label, { permanent: true, direction: 'right', className: 'modal-marker-tip' });
  shared.modalMarkers.push(m);
  return m;
}

/**
 * Initialize the right-click context menu and waypoint system.
 */
export function initContextMenu(map, points, gradSectionsRef) {
  const shared = createSharedState();

  const ctxMenu = document.getElementById('ctx-menu');
  const ctxAddWaypoint = document.getElementById('ctx-add-waypoint');
  const ctxRemoveWaypoint = document.getElementById('ctx-remove-waypoint');
  const ctxGradInfo = document.getElementById('ctx-grad-info');

  // --- Context menu display ---
  function showCtxMenu(e) {
    ctxMenu.style.left = e.clientX + 'px';
    ctxMenu.style.top = e.clientY + 'px';
    ctxMenu.style.display = 'block';

    const rect = ctxMenu.getBoundingClientRect();
    if (rect.right > window.innerWidth) ctxMenu.style.left = (e.clientX - rect.width) + 'px';
    if (rect.bottom > window.innerHeight) ctxMenu.style.top = (e.clientY - rect.height) + 'px';
  }

  function hideCtxMenu() {
    ctxMenu.style.display = 'none';
    shared.ctxTargetWaypoint = null;
    ctxRemoveWaypoint.style.display = 'none';
  }

  // --- Waypoint management ---
  const waypointMarkers = [];

  function loadWaypoints() {
    try {
      return JSON.parse(localStorage.getItem(storageKey('waypoints')) || '[]');
    } catch { return []; }
  }

  function saveWaypoints() {
    const data = waypointMarkers.map(m => ({
      lat: m.getLatLng().lat,
      lng: m.getLatLng().lng,
      label: m._wpLabel || ''
    }));
    localStorage.setItem(storageKey('waypoints'), JSON.stringify(data));
  }

  function createWaypointIcon() {
    return L.divIcon({
      className: 'waypoint-icon',
      html: '<svg viewBox="0 0 24 36" width="24" height="36">' +
        '<path d="M12,0 C5.4,0 0,5.4 0,12 C0,21 12,36 12,36 S24,21 24,12 C24,5.4 18.6,0 12,0z" fill="#00bcd4" stroke="#fff" stroke-width="2"/>' +
        '<circle cx="12" cy="12" r="5" fill="#fff"/>' +
        '</svg>',
      iconSize: [24, 36],
      iconAnchor: [12, 36],
      popupAnchor: [0, -36]
    });
  }

  function buildPopupContent(marker) {
    const ll = marker.getLatLng();
    const idx = findNearestPoint(points, ll);
    const p = points[idx];
    const displayGrad = useAbsoluteMode ? Math.abs(p.gradient) : p.gradient;
    const angle = gradToAngle(Math.abs(displayGrad)).toFixed(1);
    const label = marker._wpLabel ? `<b>${marker._wpLabel}</b><br>` : '';

    let nearbyHtml = '';
    const peak = findNearbyPeakGradient(points, ll);
    if (peak.idx !== null) {
      const pk = points[peak.idx];
      const pkGrad = useAbsoluteMode ? Math.abs(pk.gradient) : pk.gradient;
      const pkAngle = gradToAngle(Math.abs(pkGrad)).toFixed(1);
      nearbyHtml = `<br><i style="color:#888">Peak within ${peak.radius}m (${peak.dist.toFixed(0)}m away):</i><br>` +
        `Gradient: ${pkGrad.toFixed(1)}% / ${pkAngle}\u00b0`;
    }

    return `${label}` +
      `${ll.lat.toFixed(5)}, ${ll.lng.toFixed(5)}<br>` +
      `Track: ${(p.dist / 1000).toFixed(2)} km<br>` +
      `Elevation: ${p.eleSmooth.toFixed(1)}m<br>` +
      `Gradient: ${displayGrad.toFixed(1)}% / ${angle}\u00b0` +
      nearbyHtml;
  }

  function addWaypointToMap(lat, lng, label) {
    const marker = L.marker([lat, lng], {
      icon: createWaypointIcon(),
      draggable: true
    }).addTo(map);

    marker._wpLabel = label || '';
    marker.bindPopup(buildPopupContent(marker));

    const openMarkerMenu = (e) => {
      shared.ctxTargetWaypoint = marker;
      shared.ctxLatLng = e.latlng;
      shared.ctxNearestIdx = findNearestPoint(points, e.latlng);
      ctxRemoveWaypoint.style.display = '';
      showCtxMenu(e.originalEvent);
    };
    marker.on('contextmenu', (e) => {
      L.DomEvent.stopPropagation(e);
      openMarkerMenu(e);
    });
    const unsubLongPress = onLongPress(marker, openMarkerMenu);
    marker.once('remove', unsubLongPress);

    marker.on('dragend', () => {
      marker.setPopupContent(buildPopupContent(marker));
      saveWaypoints();
    });

    waypointMarkers.push(marker);
    return marker;
  }

  function removeWaypoint(marker) {
    const idx = waypointMarkers.indexOf(marker);
    if (idx !== -1) {
      map.removeLayer(marker);
      waypointMarkers.splice(idx, 1);
      saveWaypoints();
    }
  }

  // --- Map right-click ---
  const openMapMenu = (e) => {
    shared.ctxLatLng = e.latlng;
    shared.ctxNearestIdx = findNearestPoint(points, e.latlng);
    shared.ctxTargetWaypoint = null;
    ctxRemoveWaypoint.style.display = 'none';
    showCtxMenu(e.originalEvent);
  };
  map.on('contextmenu', (e) => {
    L.DomEvent.preventDefault(e.originalEvent);
    openMapMenu(e);
  });
  // Touch: long-press opens the same menu (see shared/long-press.js).
  onLongPress(map, openMapMenu);

  document.addEventListener('click', hideCtxMenu);
  document.addEventListener('contextmenu', (e) => {
    if (!e.target.closest('#map')) hideCtxMenu();
  });

  // --- Context menu actions ---
  ctxAddWaypoint.addEventListener('click', () => {
    if (!shared.ctxLatLng) return;
    const label = prompt('Waypoint label (optional):') || '';
    addWaypointToMap(shared.ctxLatLng.lat, shared.ctxLatLng.lng, label);
    saveWaypoints();
    hideCtxMenu();
  });

  ctxRemoveWaypoint.addEventListener('click', () => {
    if (shared.ctxTargetWaypoint) {
      removeWaypoint(shared.ctxTargetWaypoint);
    }
    hideCtxMenu();
  });

  ctxGradInfo.addEventListener('click', () => {
    if (shared.ctxNearestIdx === null) { hideCtxMenu(); return; }
    showGradientModal(map, points, gradSectionsRef, shared);
    hideCtxMenu();
  });

  // --- Init terrain gradient sub-module ---
  initTerrainGradient(map, points, shared, hideCtxMenu);

  // --- Restore saved waypoints ---
  loadWaypoints().forEach(wp => {
    addWaypointToMap(wp.lat, wp.lng, wp.label);
  });
}
