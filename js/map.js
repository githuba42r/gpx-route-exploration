// --- Leaflet map setup, segments, markers, hover panel ---

function initMap(points, stats) {
  const map = L.map('map', { zoomControl: true }).setView([points[0].lat, points[0].lon], 13);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19
  }).addTo(map);

  // Base route line (thin, always visible, neutral colour)
  const baseRoute = L.polyline(
    points.map(p => [p.lat, p.lon]),
    { color: '#555555', weight: 2, opacity: 0.6 }
  ).addTo(map);

  // Draw colored gradient overlay segments
  const segmentLayers = [];
  for (let i = 1; i < points.length; i++) {
    const color = gradientColor(points[i].gradient);
    const line = L.polyline(
      [[points[i-1].lat, points[i-1].lon], [points[i].lat, points[i].lon]],
      { color, weight: 4, opacity: 0.9 }
    ).addTo(map);
    line._pointIndex = i;
    line._gradientRange = rangeForGradient(points[i].gradient);
    segmentLayers.push(line);
  }

  // Start/End markers
  L.circleMarker([points[0].lat, points[0].lon], {
    radius: 8, color: '#00e676', fillColor: '#00e676', fillOpacity: 1
  }).addTo(map).bindPopup('Start');
  L.circleMarker([points[points.length-1].lat, points[points.length-1].lon], {
    radius: 8, color: '#ff1744', fillColor: '#ff1744', fillOpacity: 1
  }).addTo(map).bindPopup('End');

  // Max gradient and steepest descent markers
  let maxGradIdx = 1, minGradIdx = 1;
  for (let i = 2; i < points.length; i++) {
    if (points[i].gradient > points[maxGradIdx].gradient) maxGradIdx = i;
    if (points[i].gradient < points[minGradIdx].gradient) minGradIdx = i;
  }

  const markerIcon = (html) => L.divIcon({
    className: '',
    html,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    popupAnchor: [0, -16]
  });

  const upArrow = markerIcon(
    '<svg viewBox="0 0 28 28" width="28" height="28">' +
    '<polygon points="14,2 26,22 2,22" fill="#e94560" stroke="#fff" stroke-width="2"/>' +
    '</svg>'
  );
  const downArrow = markerIcon(
    '<svg viewBox="0 0 28 28" width="28" height="28">' +
    '<polygon points="14,26 26,6 2,6" fill="#1565c0" stroke="#fff" stroke-width="2"/>' +
    '</svg>'
  );

  const mp = points[maxGradIdx];
  L.marker([mp.lat, mp.lon], { icon: upArrow }).addTo(map).bindPopup(
    `<b>Max Gradient: ${mp.gradient.toFixed(1)}%</b><br>` +
    `Elevation: ${mp.eleSmooth.toFixed(1)}m<br>` +
    `Distance: ${(mp.dist/1000).toFixed(2)} km`
  );

  const dp = points[minGradIdx];
  L.marker([dp.lat, dp.lon], { icon: downArrow }).addTo(map).bindPopup(
    `<b>Steepest Descent: ${dp.gradient.toFixed(1)}%</b><br>` +
    `Elevation: ${dp.eleSmooth.toFixed(1)}m<br>` +
    `Distance: ${(dp.dist/1000).toFixed(2)} km`
  );

  // Fit bounds
  const bounds = L.latLngBounds(points.map(p => [p.lat, p.lon]));
  map.fitBounds(bounds, { padding: [30, 30] });

  // Position marker (synced with profile hover)
  const posMarker = L.circleMarker([points[0].lat, points[0].lon], {
    radius: 6, color: '#fff', fillColor: '#e94560', fillOpacity: 1, weight: 2, opacity: 0
  }).addTo(map);

  return { map, baseRoute, segmentLayers, posMarker };
}

function initMapHoverPanel(map, points, segmentLayers, baseRoute, gradSectionsRef) {
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
    document.getElementById('mh-grad').textContent = gradSign + displayGrad.toFixed(1) + '% / ' + ptAngle + '\u00b0';

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
      document.getElementById('mh-sec-avg').textContent = avgSign + absAvg.toFixed(1) + '% / ' + secAngle + '\u00b0';
    }
  }

  function clearMapHover() {
    if (!mhVisible) return;
    ['mh-dist','mh-ele','mh-grad','mh-sec-len','mh-sec-rise','mh-sec-avg'].forEach(id => {
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
      const d = (points[i].lat - ll.lat)**2 + (points[i].lon - ll.lng)**2;
      if (d < bestDist) { bestDist = d; bestIdx = i; }
    }
    updateMapHover(bestIdx);
  });
  baseRoute.on('mouseout', () => clearMapHover());
}
