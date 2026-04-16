// --- Map hover panel: route info on segment/base-route mouseover ---

import { useAbsoluteMode, gradToAngle } from './gradient.js';

/**
 * Wire up the map hover info panel to segment and base-route mouse events.
 */
export function initMapHoverPanel(map, points, segmentLayers, baseRoute, gradSectionsRef) {
  const mhPanel = document.getElementById('map-hover-body');
  const mhToggle = document.getElementById('map-hover-toggle');
  let mhVisible = false;
  mhToggle.addEventListener('click', () => {
    mhVisible = !mhVisible;
    mhPanel.style.display = mhVisible ? 'block' : 'none';
    mhToggle.textContent = mhVisible ? 'Hide Info' : 'Route Info';
  });

  const panelEl = document.getElementById('map-hover-panel');
  L.DomEvent.disableClickPropagation(panelEl);
  L.DomEvent.disableScrollPropagation(panelEl);

  function updateMapHover(ptIdx) {
    if (!mhVisible) return;
    const p = points[ptIdx];
    const displayGrad = useAbsoluteMode ? Math.abs(p.gradient) : p.gradient;
    const gradSign = (!useAbsoluteMode && p.gradient > 0) ? '+' : '';

    document.getElementById('mh-dist').textContent = (p.dist / 1000).toFixed(2) + ' km';
    document.getElementById('mh-ele').textContent = p.eleSmooth.toFixed(1) + ' m';
    const ptAngle = gradToAngle(displayGrad).toFixed(1);
    document.getElementById('mh-grad').textContent =
      gradSign + displayGrad.toFixed(1) + '% / ' + ptAngle + '\u00b0';

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

      document.getElementById('mh-sec-len').textContent = secDist >= 1000
        ? (secDist / 1000).toFixed(2) + ' km'
        : secDist.toFixed(0) + ' m';
      document.getElementById('mh-sec-rise').textContent =
        (secRise >= 0 ? '+' : '') + secRise.toFixed(1) + ' m';
      const secAngle = gradToAngle(absAvg).toFixed(1);
      document.getElementById('mh-sec-avg').textContent =
        avgSign + absAvg.toFixed(1) + '% / ' + secAngle + '\u00b0';
    }
  }

  function clearMapHover() {
    if (!mhVisible) return;
    ['mh-dist', 'mh-ele', 'mh-grad', 'mh-sec-len', 'mh-sec-rise', 'mh-sec-avg'].forEach(id => {
      document.getElementById(id).textContent = '\u2014';
    });
  }

  segmentLayers.forEach(line => {
    line.on('mouseover', () => {
      line.setStyle({ weight: 7 });
      updateMapHover(line._pointIndex);
    });
    line.on('mouseout', () => {
      line.setStyle({ weight: 4 });
      clearMapHover();
    });
  });

  baseRoute.on('mouseover', (e) => {
    const ll = e.latlng;
    let bestIdx = 0, bestDist = Infinity;
    for (let i = 0; i < points.length; i++) {
      const d = (points[i].lat - ll.lat) ** 2 + (points[i].lon - ll.lng) ** 2;
      if (d < bestDist) { bestDist = d; bestIdx = i; }
    }
    updateMapHover(bestIdx);
  });
  baseRoute.on('mouseout', () => clearMapHover());
}
