// --- Route gradient info modal with nearby peak search ---

import { useAbsoluteMode, gradToAngle } from './gradient.js';
import { haversine } from './track-processor.js';
import { findNearbyPeakGradient, clearModalMarkers, addModalMarker } from './context-menu.js';

/**
 * Show the gradient info modal for a right-clicked location.
 */
export function showGradientModal(map, points, gradSectionsRef, shared) {
  clearModalMarkers(map, shared);

  const latlng = shared.ctxLatLng;
  const ptIdx = shared.ctxNearestIdx;
  const p = points[ptIdx];
  const displayGrad = useAbsoluteMode ? Math.abs(p.gradient) : p.gradient;
  const gradSign = (!useAbsoluteMode && p.gradient > 0) ? '+' : '';
  const angle = gradToAngle(Math.abs(displayGrad)).toFixed(1);

  document.getElementById('gm-pos').textContent =
    latlng.lat.toFixed(5) + ', ' + latlng.lng.toFixed(5);
  document.getElementById('gm-dist').textContent = (p.dist / 1000).toFixed(2) + ' km';
  document.getElementById('gm-ele').textContent = p.eleSmooth.toFixed(1) + ' m';
  document.getElementById('gm-grad').textContent = gradSign + displayGrad.toFixed(1) + '%';
  document.getElementById('gm-angle').textContent = angle + '\u00b0';

  // Show selected location marker (yellow)
  addModalMarker(map, shared, latlng.lat, latlng.lng, '#ffee58', 'Selected');
  // Show nearest track point marker (cyan)
  addModalMarker(map, shared, p.lat, p.lon, '#00bcd4', 'Nearest');

  const sec = gradSectionsRef.current[ptIdx];
  if (sec) {
    const secStart = Math.max(0, sec.startIdx - 1);
    const secDist = points[sec.endIdx].dist - points[secStart].dist;
    const secRise = points[sec.endIdx].eleSmooth - points[secStart].eleSmooth;
    let gradSum = 0, gradCount = 0;
    for (let si = sec.startIdx; si <= sec.endIdx; si++) {
      gradSum += points[si].gradient;
      gradCount++;
    }
    const secAvg = gradCount > 0 ? gradSum / gradCount : 0;
    const absAvg = useAbsoluteMode ? Math.abs(secAvg) : secAvg;
    const avgSign = (!useAbsoluteMode && secAvg > 0) ? '+' : '';
    const secAngle = gradToAngle(absAvg).toFixed(1);

    document.getElementById('gm-sec-range').textContent = sec.label || '\u2014';
    document.getElementById('gm-sec-len').textContent = secDist >= 1000
      ? (secDist / 1000).toFixed(2) + ' km'
      : secDist.toFixed(0) + ' m';
    document.getElementById('gm-sec-rise').textContent =
      (secRise >= 0 ? '+' : '') + secRise.toFixed(1) + ' m';
    document.getElementById('gm-sec-avg').textContent =
      avgSign + absAvg.toFixed(1) + '% / ' + secAngle + '\u00b0';
  }

  // Nearby peak gradient
  const peak = findNearbyPeakGradient(points, latlng);
  const radiusLabel = document.getElementById('gm-nearby-radius');
  if (radiusLabel) radiusLabel.textContent = peak.radius + 'm radius';

  if (peak.idx !== null) {
    const pk = points[peak.idx];
    const pkGrad = useAbsoluteMode ? Math.abs(pk.gradient) : pk.gradient;
    const pkSign = (!useAbsoluteMode && pk.gradient > 0) ? '+' : '';
    const pkAngle = gradToAngle(Math.abs(pkGrad)).toFixed(1);
    document.getElementById('gm-nearby-max').textContent =
      pkSign + pkGrad.toFixed(1) + '% / ' + pkAngle + '\u00b0';
    document.getElementById('gm-nearby-dist').textContent =
      (pk.dist / 1000).toFixed(2) + ' km (' + peak.dist.toFixed(0) + 'm from here)';
    document.getElementById('gm-nearby-ele').textContent = pk.eleSmooth.toFixed(1) + ' m';

    // Peak gradient marker with pulsing pin
    const peakIcon = L.divIcon({
      className: '',
      html: '<div style="position:relative;width:36px;height:36px;">' +
        '<div style="position:absolute;inset:0;border-radius:50%;background:rgba(233,69,96,0.3);animation:peak-pulse 1.5s ease-in-out infinite;"></div>' +
        '<svg viewBox="0 0 36 36" width="36" height="36" style="position:absolute;inset:0;">' +
        '<circle cx="18" cy="18" r="12" fill="#e94560" stroke="#fff" stroke-width="3"/>' +
        '<text x="18" y="22" text-anchor="middle" fill="#fff" font-size="12" font-weight="bold">!</text>' +
        '</svg></div>',
      iconSize: [36, 36],
      iconAnchor: [18, 18]
    });
    const peakMarker = L.marker([pk.lat, pk.lon], { icon: peakIcon, zIndexOffset: 1000 }).addTo(map);
    peakMarker.bindTooltip('Peak ' + pkGrad.toFixed(1) + '%', {
      permanent: true, direction: 'top', offset: [0, -20],
      className: 'modal-marker-tip peak-tip'
    });
    shared.modalMarkers.push(peakMarker);

    // Search radius circle
    const circle = L.circle([latlng.lat, latlng.lng], {
      radius: peak.radius,
      color: '#ffee58', fillColor: '#ffee58', fillOpacity: 0.05,
      weight: 1, dashArray: '6,4'
    }).addTo(map);
    shared.modalMarkers.push(circle);
  } else {
    document.getElementById('gm-nearby-max').textContent = '\u2014';
    document.getElementById('gm-nearby-dist').textContent = '\u2014';
    document.getElementById('gm-nearby-ele').textContent = '\u2014';
  }

  const modalOverlay = document.getElementById('grad-modal-overlay');
  modalOverlay.classList.add('visible');

  // Wire close handlers (idempotent — remove old listeners first)
  const modalClose = document.getElementById('gm-close');
  const closeFn = () => closeGradientModal(map, shared);
  modalClose.onclick = closeFn;
  modalOverlay.onclick = (e) => {
    if (e.target === modalOverlay) closeFn();
  };
}

export function closeGradientModal(map, shared) {
  document.getElementById('grad-modal-overlay').classList.remove('visible');
  clearModalMarkers(map, shared);
}
