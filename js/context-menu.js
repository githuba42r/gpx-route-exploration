// --- Right-click context menu, waypoints, and gradient info modal ---

const WAYPOINT_STORAGE_KEY = 'gpx-waypoints';

function initContextMenu(map, points, gradSectionsRef) {
  const ctxMenu = document.getElementById('ctx-menu');
  const ctxAddWaypoint = document.getElementById('ctx-add-waypoint');
  const ctxRemoveWaypoint = document.getElementById('ctx-remove-waypoint');
  const ctxGradInfo = document.getElementById('ctx-grad-info');
  const modalOverlay = document.getElementById('grad-modal-overlay');
  const modalClose = document.getElementById('gm-close');

  let ctxLatLng = null;
  let ctxNearestIdx = null;
  let ctxTargetWaypoint = null;

  // Temporary markers shown while gradient modal is open
  let modalMarkers = [];

  function clearModalMarkers() {
    modalMarkers.forEach(m => map.removeLayer(m));
    modalMarkers = [];
  }

  function addModalMarker(lat, lon, color, label) {
    const m = L.circleMarker([lat, lon], {
      radius: 8, color: '#fff', fillColor: color, fillOpacity: 1, weight: 2
    }).addTo(map);
    if (label) m.bindTooltip(label, { permanent: true, direction: 'right', className: 'modal-marker-tip' });
    modalMarkers.push(m);
    return m;
  }

  // --- Waypoint management ---
  const waypointMarkers = [];

  function loadWaypoints() {
    try {
      return JSON.parse(localStorage.getItem(WAYPOINT_STORAGE_KEY) || '[]');
    } catch { return []; }
  }

  function saveWaypoints() {
    const data = waypointMarkers.map(m => ({
      lat: m.getLatLng().lat,
      lng: m.getLatLng().lng,
      label: m._wpLabel || ''
    }));
    localStorage.setItem(WAYPOINT_STORAGE_KEY, JSON.stringify(data));
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

  function addWaypointToMap(lat, lng, label) {
    const marker = L.marker([lat, lng], {
      icon: createWaypointIcon(),
      draggable: true
    }).addTo(map);

    marker._wpLabel = label || '';
    marker.bindPopup(buildPopupContent(marker));

    marker.on('contextmenu', (e) => {
      L.DomEvent.stopPropagation(e);
      ctxTargetWaypoint = marker;
      ctxLatLng = e.latlng;
      ctxNearestIdx = findNearestPoint(e.latlng);
      ctxRemoveWaypoint.style.display = '';
      showCtxMenu(e.originalEvent);
    });

    marker.on('dragend', () => {
      marker.setPopupContent(buildPopupContent(marker));
      saveWaypoints();
    });

    waypointMarkers.push(marker);
    return marker;
  }

  function buildPopupContent(marker) {
    const ll = marker.getLatLng();
    const idx = findNearestPoint(ll);
    const p = points[idx];
    const displayGrad = useAbsoluteMode ? Math.abs(p.gradient) : p.gradient;
    const angle = gradToAngle(Math.abs(displayGrad)).toFixed(1);
    const label = marker._wpLabel ? `<b>${marker._wpLabel}</b><br>` : '';

    let nearbyHtml = '';
    const peak = findNearbyPeakGradient(ll);
    if (peak.idx !== null) {
      const pk = points[peak.idx];
      const pkGrad = useAbsoluteMode ? Math.abs(pk.gradient) : pk.gradient;
      const pkAngle = gradToAngle(Math.abs(pkGrad)).toFixed(1);
      nearbyHtml = `<br><i style="color:#888">Peak within ${peak.radius}m (${peak.dist.toFixed(0)}m away):</i><br>` +
        `Gradient: ${pkGrad.toFixed(1)}% / ${pkAngle}\u00b0`;
    }

    return `${label}` +
      `${ll.lat.toFixed(5)}, ${ll.lng.toFixed(5)}<br>` +
      `Track: ${(p.dist/1000).toFixed(2)} km<br>` +
      `Elevation: ${p.eleSmooth.toFixed(1)}m<br>` +
      `Gradient: ${displayGrad.toFixed(1)}% / ${angle}\u00b0` +
      nearbyHtml;
  }

  function removeWaypoint(marker) {
    const idx = waypointMarkers.indexOf(marker);
    if (idx !== -1) {
      map.removeLayer(marker);
      waypointMarkers.splice(idx, 1);
      saveWaypoints();
    }
  }

  // --- Nearest point lookup ---
  function findNearestPoint(latlng) {
    let bestIdx = 0, bestDist = Infinity;
    for (let i = 0; i < points.length; i++) {
      const d = (points[i].lat - latlng.lat)**2 + (points[i].lon - latlng.lng)**2;
      if (d < bestDist) { bestDist = d; bestIdx = i; }
    }
    return bestIdx;
  }

  // Find the steepest absolute gradient nearby.
  // Uses a dynamic radius: at least 50m, or nearest-point distance + 50m buffer,
  // so it always covers the track even when the click is far from it.
  function findNearbyPeakGradient(latlng) {
    const nearestIdx = findNearestPoint(latlng);
    const nearestDist = haversine(latlng.lat, latlng.lng, points[nearestIdx].lat, points[nearestIdx].lon);
    const searchRadius = Math.max(50, nearestDist + 50);
    // Rough degree filter: 1 degree ~ 111km, so radius/111000 plus margin
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
    ctxTargetWaypoint = null;
    ctxRemoveWaypoint.style.display = 'none';
  }

  // --- Map right-click ---
  map.on('contextmenu', (e) => {
    L.DomEvent.preventDefault(e.originalEvent);
    ctxLatLng = e.latlng;
    ctxNearestIdx = findNearestPoint(e.latlng);
    ctxTargetWaypoint = null;
    ctxRemoveWaypoint.style.display = 'none';
    showCtxMenu(e.originalEvent);
  });

  document.addEventListener('click', hideCtxMenu);
  document.addEventListener('contextmenu', (e) => {
    if (!e.target.closest('#map')) hideCtxMenu();
  });

  // --- Context menu actions ---
  ctxAddWaypoint.addEventListener('click', () => {
    if (!ctxLatLng) return;
    const label = prompt('Waypoint label (optional):') || '';
    addWaypointToMap(ctxLatLng.lat, ctxLatLng.lng, label);
    saveWaypoints();
    hideCtxMenu();
  });

  ctxRemoveWaypoint.addEventListener('click', () => {
    if (ctxTargetWaypoint) {
      removeWaypoint(ctxTargetWaypoint);
    }
    hideCtxMenu();
  });

  ctxGradInfo.addEventListener('click', () => {
    if (ctxNearestIdx === null) { hideCtxMenu(); return; }
    showGradientModal(ctxLatLng, ctxNearestIdx);
    hideCtxMenu();
  });

  // --- Gradient info modal ---
  function showGradientModal(latlng, ptIdx) {
    clearModalMarkers();

    const p = points[ptIdx];
    const displayGrad = useAbsoluteMode ? Math.abs(p.gradient) : p.gradient;
    const gradSign = (!useAbsoluteMode && p.gradient > 0) ? '+' : '';
    const angle = gradToAngle(Math.abs(displayGrad)).toFixed(1);

    document.getElementById('gm-pos').textContent = latlng.lat.toFixed(5) + ', ' + latlng.lng.toFixed(5);
    document.getElementById('gm-dist').textContent = (p.dist / 1000).toFixed(2) + ' km';
    document.getElementById('gm-ele').textContent = p.eleSmooth.toFixed(1) + ' m';
    document.getElementById('gm-grad').textContent = gradSign + displayGrad.toFixed(1) + '%';
    document.getElementById('gm-angle').textContent = angle + '\u00b0';

    // Show selected location marker (yellow)
    addModalMarker(latlng.lat, latlng.lng, '#ffee58', 'Selected');
    // Show nearest track point marker (cyan)
    addModalMarker(p.lat, p.lon, '#00bcd4', 'Nearest');

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
      document.getElementById('gm-sec-avg').textContent = avgSign + absAvg.toFixed(1) + '% / ' + secAngle + '\u00b0';
    }

    // Nearby peak gradient
    const peak = findNearbyPeakGradient(latlng);
    const radiusLabel = document.getElementById('gm-nearby-radius');
    if (radiusLabel) radiusLabel.textContent = peak.radius + 'm radius';

    if (peak.idx !== null) {
      const pk = points[peak.idx];
      const pkGrad = useAbsoluteMode ? Math.abs(pk.gradient) : pk.gradient;
      const pkSign = (!useAbsoluteMode && pk.gradient > 0) ? '+' : '';
      const pkAngle = gradToAngle(Math.abs(pkGrad)).toFixed(1);
      document.getElementById('gm-nearby-max').textContent = pkSign + pkGrad.toFixed(1) + '% / ' + pkAngle + '\u00b0';
      document.getElementById('gm-nearby-dist').textContent =
        (pk.dist / 1000).toFixed(2) + ' km (' + peak.dist.toFixed(0) + 'm from here)';
      document.getElementById('gm-nearby-ele').textContent = pk.eleSmooth.toFixed(1) + ' m';

      // Show peak gradient marker — large pulsing pin
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
      modalMarkers.push(peakMarker);

      // Draw search radius circle
      const circle = L.circle([latlng.lat, latlng.lng], {
        radius: peak.radius,
        color: '#ffee58', fillColor: '#ffee58', fillOpacity: 0.05,
        weight: 1, dashArray: '6,4'
      }).addTo(map);
      modalMarkers.push(circle);
    } else {
      document.getElementById('gm-nearby-max').textContent = '\u2014';
      document.getElementById('gm-nearby-dist').textContent = '\u2014';
      document.getElementById('gm-nearby-ele').textContent = '\u2014';
    }

    modalOverlay.classList.add('visible');
  }

  function closeModal() {
    modalOverlay.classList.remove('visible');
    clearModalMarkers();
  }

  modalClose.addEventListener('click', closeModal);
  modalOverlay.addEventListener('click', (e) => {
    if (e.target === modalOverlay) closeModal();
  });

  // --- Terrain gradient (DEM-based) ---
  const VALHALLA_URL = 'http://10.0.1.25:8002/height';
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
    // Center + 8 compass directions at SAMPLE_DIST
    const shape = [{ lat, lon }];
    for (const b of BEARINGS) {
      const pt = offsetLatLon(lat, lon, b.deg, SAMPLE_DIST);
      shape.push({ lat: parseFloat(pt.lat.toFixed(7)), lon: parseFloat(pt.lon.toFixed(7)) });
    }

    const resp = await fetch(VALHALLA_URL, {
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

  const terrainOverlay = document.getElementById('terrain-modal-overlay');
  const terrainClose = document.getElementById('tm-close');
  const ctxTerrainInfo = document.getElementById('ctx-terrain-info');

  ctxTerrainInfo.addEventListener('click', async () => {
    if (!ctxLatLng) { hideCtxMenu(); return; }
    hideCtxMenu();

    // Show loading state
    clearModalMarkers();
    addModalMarker(ctxLatLng.lat, ctxLatLng.lng, '#ffee58', 'Sampling...');

    try {
      const terrain = await sampleTerrainElevations(ctxLatLng.lat, ctxLatLng.lng);
      showTerrainModal(ctxLatLng, terrain);
    } catch (err) {
      clearModalMarkers();
      alert('Terrain gradient failed: ' + err.message);
    }
  });

  function gradientColorForValue(absGrad) {
    // Reuse the absolute gradient ranges for consistent coloring (maps/lines)
    for (const r of ABSOLUTE_RANGES) {
      if (absGrad >= r.min && absGrad < r.max) return r.color;
    }
    return '#888';
  }

  // Lighter text-safe versions for dark backgrounds
  function compassTextColor(absGrad) {
    if (absGrad < 2)  return '#a5d6a7'; // light green
    if (absGrad < 5)  return '#fff176'; // light yellow
    if (absGrad < 8)  return '#ffcc80'; // light orange
    if (absGrad < 12) return '#ef9a9a'; // light red
    if (absGrad < 16) return '#ff8a80'; // bright red
    return '#ea80fc';                    // bright purple
  }

  function showTerrainModal(latlng, terrain) {
    clearModalMarkers();

    const { centerEle, directions } = terrain;
    const steepest = directions.reduce((a, b) => a.absGradient > b.absGradient ? a : b);
    const steepAngle = gradToAngle(steepest.absGradient).toFixed(1);

    document.getElementById('tm-pos').textContent = latlng.lat.toFixed(5) + ', ' + latlng.lng.toFixed(5);
    document.getElementById('tm-ele').textContent = centerEle + ' m';
    document.getElementById('tm-max-grad').textContent = steepest.absGradient.toFixed(1) + '% / ' + steepAngle + '\u00b0';
    document.getElementById('tm-direction').textContent = steepest.label + ' (' + steepest.deg + '\u00b0) ' +
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

    // Simple marker on main map to show the sampled location
    addModalMarker(latlng.lat, latlng.lng, '#ffee58', 'Terrain sample');

    terrainOverlay.classList.add('visible');

    // Build mini-map inside the modal showing the zoomed detail
    buildTerrainMiniMap(latlng, terrain, steepest);
  }

  let terrainMiniMap = null;

  function buildTerrainMiniMap(latlng, terrain, steepest) {
    const container = document.getElementById('tm-minimap');

    // Destroy previous mini-map if any
    if (terrainMiniMap) {
      terrainMiniMap.remove();
      terrainMiniMap = null;
    }

    // Need a brief delay so the container is visible and has dimensions
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

      // Use the same base layer as the main map
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 20
      }).addTo(terrainMiniMap);

      const { centerEle, directions } = terrain;

      // Tooltip direction per compass bearing so labels radiate outward
      const tipDir = { 0:'top', 45:'right', 90:'right', 135:'right', 180:'bottom', 225:'left', 270:'left', 315:'left' };

      // Extend lines to 1.5x sample distance so labels sit outside the ring
      const LABEL_DIST = SAMPLE_DIST * 1.6;

      // Draw gradient lines from center to each sample direction
      directions.forEach(d => {
        const pt = offsetLatLon(latlng.lat, latlng.lng, d.deg, SAMPLE_DIST);
        const labelPt = offsetLatLon(latlng.lat, latlng.lng, d.deg, LABEL_DIST);
        const color = gradientColorForValue(d.absGradient);
        const isSteep = d === steepest;

        L.polyline(
          [[latlng.lat, latlng.lng], [pt.lat, pt.lon]],
          { color, weight: isSteep ? 6 : 3, opacity: 0.9 }
        ).addTo(terrainMiniMap);

        // Dot at sample point
        L.circleMarker([pt.lat, pt.lon], {
          radius: isSteep ? 7 : 4,
          color: '#fff', fillColor: color, fillOpacity: 1, weight: 2
        }).addTo(terrainMiniMap);

        // Text label outside the ring — no tooltip box, just a plain div icon
        const sign = d.gradient >= 0 ? '+' : '';
        const labelColor = isSteep ? '#e94560' : '#e0e0e0';
        const labelWeight = isSteep ? '700' : '400';
        const labelHtml = `<div style="color:${labelColor};font-weight:${labelWeight};font-size:11px;text-shadow:0 0 4px #000,0 0 2px #000;white-space:nowrap;text-align:center;">${d.label} ${sign}${d.gradient.toFixed(0)}%</div>`;
        L.marker([labelPt.lat, labelPt.lon], {
          icon: L.divIcon({ className: '', html: labelHtml, iconSize: [60, 16], iconAnchor: [30, 8] }),
          interactive: false
        }).addTo(terrainMiniMap);
      });

      // Center marker
      L.circleMarker([latlng.lat, latlng.lng], {
        radius: 6, color: '#fff', fillColor: '#ffee58', fillOpacity: 1, weight: 2
      }).addTo(terrainMiniMap);

      terrainMiniMap.invalidateSize();
    }, 50);
  }

  function closeTerrainModal() {
    terrainOverlay.classList.remove('visible');
    clearModalMarkers();
    if (terrainMiniMap) {
      terrainMiniMap.remove();
      terrainMiniMap = null;
    }
  }

  terrainClose.addEventListener('click', closeTerrainModal);
  terrainOverlay.addEventListener('click', (e) => {
    if (e.target === terrainOverlay) closeTerrainModal();
  });

  // --- Restore saved waypoints ---
  loadWaypoints().forEach(wp => {
    addWaypointToMap(wp.lat, wp.lng, wp.label);
  });
}
