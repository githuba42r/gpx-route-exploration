// --- DEM-based terrain gradient sampling, terrain modal, mini-map ---

import { ABSOLUTE_RANGES, gradToAngle } from './gradient.js';
import { clearModalMarkers, addModalMarker } from './context-menu.js';

const VALHALLA_HEIGHT_URL = '/proxy/valhalla/height';
const SAMPLE_DIST = 25; // metres
const BEARINGS = [
  { deg: 0,   label: 'N' },
  { deg: 45,  label: 'NE' },
  { deg: 90,  label: 'E' },
  { deg: 135, label: 'SE' },
  { deg: 180, label: 'S' },
  { deg: 225, label: 'SW' },
  { deg: 270, label: 'W' },
  { deg: 315, label: 'NW' },
];

function offsetLatLon(lat, lon, bearingDeg, distM) {
  const dlat = (distM / 111320) * Math.cos(bearingDeg * Math.PI / 180);
  const dlon = (distM / (111320 * Math.cos(lat * Math.PI / 180))) * Math.sin(bearingDeg * Math.PI / 180);
  return { lat: lat + dlat, lon: lon + dlon };
}

async function sampleTerrainElevations(lat, lon) {
  const shape = [{ lat, lon }];
  for (const b of BEARINGS) {
    const pt = offsetLatLon(lat, lon, b.deg, SAMPLE_DIST);
    shape.push({ lat: parseFloat(pt.lat.toFixed(7)), lon: parseFloat(pt.lon.toFixed(7)) });
  }

  const resp = await fetch(VALHALLA_HEIGHT_URL, {
    method: 'POST',
    body: JSON.stringify({ shape })
  });
  const data = await resp.json();

  if (!data.height || data.height.some(h => h === null)) {
    throw new Error('DEM data not available for this location');
  }

  const centerEle = data.height[0];
  const directions = BEARINGS.map((b, i) => {
    const ele = data.height[i + 1];
    const grad = ((ele - centerEle) / SAMPLE_DIST) * 100;
    return { ...b, ele, gradient: grad, absGradient: Math.abs(grad) };
  });

  return { centerEle, directions };
}

function gradientColorForValue(absGrad) {
  for (const r of ABSOLUTE_RANGES) {
    if (absGrad >= r.min && absGrad < r.max) return r.color;
  }
  return '#888';
}

function compassTextColor(absGrad) {
  if (absGrad < 2)  return '#a5d6a7';
  if (absGrad < 5)  return '#fff176';
  if (absGrad < 8)  return '#ffcc80';
  if (absGrad < 12) return '#ef9a9a';
  if (absGrad < 16) return '#ff8a80';
  return '#ea80fc';
}

let terrainMiniMap = null;

function buildTerrainMiniMap(latlng, terrain, steepest) {
  const container = document.getElementById('tm-minimap');

  if (terrainMiniMap) {
    terrainMiniMap.remove();
    terrainMiniMap = null;
  }

  setTimeout(() => {
    terrainMiniMap = L.map(container, {
      zoomControl: false,
      attributionControl: false,
      dragging: false,
      scrollWheelZoom: false,
      doubleClickZoom: false,
      boxZoom: false,
      keyboard: false,
      touchZoom: false
    }).setView([latlng.lat, latlng.lng], 18);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 20
    }).addTo(terrainMiniMap);

    const { directions } = terrain;
    const LABEL_DIST = SAMPLE_DIST * 1.6;

    directions.forEach(d => {
      const pt = offsetLatLon(latlng.lat, latlng.lng, d.deg, SAMPLE_DIST);
      const labelPt = offsetLatLon(latlng.lat, latlng.lng, d.deg, LABEL_DIST);
      const color = gradientColorForValue(d.absGradient);
      const isSteep = d === steepest;

      L.polyline(
        [[latlng.lat, latlng.lng], [pt.lat, pt.lon]],
        { color, weight: isSteep ? 6 : 3, opacity: 0.9 }
      ).addTo(terrainMiniMap);

      L.circleMarker([pt.lat, pt.lon], {
        radius: isSteep ? 7 : 4,
        color: '#fff', fillColor: color, fillOpacity: 1, weight: 2
      }).addTo(terrainMiniMap);

      const sign = d.gradient >= 0 ? '+' : '';
      const labelColor = isSteep ? '#e94560' : '#e0e0e0';
      const labelWeight = isSteep ? '700' : '400';
      const labelHtml = `<div style="color:${labelColor};font-weight:${labelWeight};font-size:11px;text-shadow:0 0 4px #000,0 0 2px #000;white-space:nowrap;text-align:center;">${d.label} ${sign}${d.gradient.toFixed(0)}%</div>`;
      L.marker([labelPt.lat, labelPt.lon], {
        icon: L.divIcon({ className: '', html: labelHtml, iconSize: [60, 16], iconAnchor: [30, 8] }),
        interactive: false
      }).addTo(terrainMiniMap);
    });

    L.circleMarker([latlng.lat, latlng.lng], {
      radius: 6, color: '#fff', fillColor: '#ffee58', fillOpacity: 1, weight: 2
    }).addTo(terrainMiniMap);

    terrainMiniMap.invalidateSize();
  }, 50);
}

function showTerrainModal(map, latlng, terrain, shared) {
  clearModalMarkers(shared);

  const { centerEle, directions } = terrain;
  const steepest = directions.reduce((a, b) => a.absGradient > b.absGradient ? a : b);
  const steepAngle = gradToAngle(steepest.absGradient).toFixed(1);

  document.getElementById('tm-pos').textContent =
    latlng.lat.toFixed(5) + ', ' + latlng.lng.toFixed(5);
  document.getElementById('tm-ele').textContent = centerEle + ' m';
  document.getElementById('tm-max-grad').textContent =
    steepest.absGradient.toFixed(1) + '% / ' + steepAngle + '\u00b0';
  document.getElementById('tm-direction').textContent =
    steepest.label + ' (' + steepest.deg + '\u00b0) ' +
    (steepest.gradient > 0 ? '\u2197 uphill' : '\u2198 downhill');

  // Compass table
  const compassEl = document.getElementById('tm-compass');
  let html = '';
  directions.forEach(d => {
    const mapColor = gradientColorForValue(d.absGradient);
    const textColor = compassTextColor(d.absGradient);
    const bar = '\u2588'.repeat(Math.min(20, Math.round(d.absGradient / 2)));
    const isSteepest = d === steepest;
    const style = isSteepest ? 'font-weight:700;' : '';
    html += `<div style="${style}">` +
      `<span style="display:inline-block;width:24px;">${d.label}</span>` +
      `<span style="display:inline-block;width:50px;">${d.ele}m</span>` +
      `<span style="display:inline-block;width:70px;color:${textColor}">${d.gradient >= 0 ? '+' : ''}${d.gradient.toFixed(1)}%</span>` +
      `<span style="color:${mapColor}">${bar}</span>` +
      (isSteepest ? ' \u25c0' : '') +
      `</div>`;
  });
  compassEl.innerHTML = html;

  // Marker on main map
  addModalMarker(map, shared, latlng.lat, latlng.lng, '#ffee58', 'Terrain sample');

  const terrainOverlay = document.getElementById('terrain-modal-overlay');
  terrainOverlay.classList.add('visible');

  buildTerrainMiniMap(latlng, terrain, steepest);
}

function closeTerrainModal(shared) {
  document.getElementById('terrain-modal-overlay').classList.remove('visible');
  clearModalMarkers(shared);
  if (terrainMiniMap) {
    terrainMiniMap.remove();
    terrainMiniMap = null;
  }
}

/**
 * Initialize terrain gradient menu item and modal close handlers.
 */
export function initTerrainGradient(map, points, shared, hideCtxMenu) {
  const ctxTerrainInfo = document.getElementById('ctx-terrain-info');
  const terrainOverlay = document.getElementById('terrain-modal-overlay');
  const terrainClose = document.getElementById('tm-close');

  ctxTerrainInfo.addEventListener('click', async () => {
    if (!shared.ctxLatLng) { hideCtxMenu(); return; }
    hideCtxMenu();

    clearModalMarkers(shared);
    addModalMarker(map, shared, shared.ctxLatLng.lat, shared.ctxLatLng.lng, '#ffee58', 'Sampling...');

    try {
      const terrain = await sampleTerrainElevations(shared.ctxLatLng.lat, shared.ctxLatLng.lng);
      showTerrainModal(map, shared.ctxLatLng, terrain, shared);
    } catch (err) {
      clearModalMarkers(shared);
      alert('Terrain gradient failed: ' + err.message);
    }
  });

  terrainClose.addEventListener('click', () => closeTerrainModal(shared));
  terrainOverlay.addEventListener('click', (e) => {
    if (e.target === terrainOverlay) closeTerrainModal(shared);
  });
}
