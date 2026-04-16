// --- Start/End markers, max gradient markers, position marker ---

/**
 * Create start and end circle markers on the map.
 */
export function createStartEndMarkers(map, points) {
  L.circleMarker([points[0].lat, points[0].lon], {
    radius: 8, color: '#00e676', fillColor: '#00e676', fillOpacity: 1
  }).addTo(map).bindPopup('Start');

  L.circleMarker([points[points.length - 1].lat, points[points.length - 1].lon], {
    radius: 8, color: '#ff1744', fillColor: '#ff1744', fillOpacity: 1
  }).addTo(map).bindPopup('End');
}

/**
 * Create markers for the steepest ascent and descent points.
 */
export function createGradientMarkers(map, points) {
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
    `Distance: ${(mp.dist / 1000).toFixed(2)} km`
  );

  const dp = points[minGradIdx];
  L.marker([dp.lat, dp.lon], { icon: downArrow }).addTo(map).bindPopup(
    `<b>Steepest Descent: ${dp.gradient.toFixed(1)}%</b><br>` +
    `Elevation: ${dp.eleSmooth.toFixed(1)}m<br>` +
    `Distance: ${(dp.dist / 1000).toFixed(2)} km`
  );
}

/**
 * Create the position marker (synced with profile hover).
 * Returns the circleMarker instance.
 */
export function createPosMarker(map, points) {
  return L.circleMarker([points[0].lat, points[0].lon], {
    radius: 6, color: '#fff', fillColor: '#e94560', fillOpacity: 1, weight: 2, opacity: 0
  }).addTo(map);
}
