import { onLongPress } from './long-press.js';

// --- Leaflet marker factories for stops and waypoints ---
//
// Icons are HTML divIcons styled with CSS. Stop = red octagon,
// waypoint = cyan diamond. Number inside is the 1-based visit order.

function stopIconHtml(n, { isStart = false, isEnd = false, dimmed = false } = {}) {
  const cls = `wpe-marker wpe-stop${isStart ? ' wpe-start' : ''}${isEnd ? ' wpe-end' : ''}${dimmed ? ' wpe-dimmed' : ''}`;
  return `<div class="${cls}">${n}</div>`;
}

function waypointIconHtml(n, { dimmed = false } = {}) {
  return `<div class="wpe-marker wpe-waypoint${dimmed ? ' wpe-dimmed' : ''}"><span>${n}</span></div>`;
}

export function makeStopMarker(lat, lon, n, opts = {}) {
  const icon = L.divIcon({
    className: '',
    html: stopIconHtml(n, opts),
    iconSize: [30, 30],
    iconAnchor: [15, 15],
  });
  return L.marker([lat, lon], { icon, draggable: !!opts.draggable });
}

export function makeWaypointMarker(lat, lon, n, opts = {}) {
  const icon = L.divIcon({
    className: '',
    html: waypointIconHtml(n, opts),
    iconSize: [20, 20],
    iconAnchor: [10, 10],
  });
  return L.marker([lat, lon], { icon, draggable: !!opts.draggable });
}

/**
 * Build or replace markers for a route's waypoints.
 * @param {L.Map} map
 * @param {Array} waypoints — each { id, kind, lat, lon, pin_role }
 * @param {L.Marker[]} existingLayers — replaced in place
 * @param {Function} onClick — optional click handler: (waypoint) => void
 * @param {Function} onContextMenu — optional right-click handler: (waypoint) => void
 * @param {Function} onDragEnd — optional drag-end handler: (waypoint, {lat,lon}) => void
 * @returns updated layer array
 */
export function renderMarkers(map, waypoints, existingLayers,
                              { onClick, onContextMenu, onDragEnd, draggable = false } = {}) {
  existingLayers.forEach(m => map.removeLayer(m));
  const layers = [];
  waypoints.forEach((w, i) => {
    if (w.lat == null || w.lon == null) return;
    const n = i + 1;
    const make = w.kind === 'stop' ? makeStopMarker : makeWaypointMarker;
    const marker = make(w.lat, w.lon, n, {
      isStart: w.pin_role === 'start',
      isEnd: w.pin_role === 'end',
      dimmed: w.included === 0,
      draggable,
    });
    marker.addTo(map);
    marker._waypointId = w.id;
    if (onClick) marker.on('click', () => onClick(w));
    if (onContextMenu) {
      marker.on('contextmenu', (e) => {
        if (e.originalEvent) e.originalEvent.preventDefault();
        onContextMenu(w, e);
      });
      // Touch: long-press is the single path (native contextmenu is
      // swallowed by onLongPress while a finger is down). Unsubscribe when
      // the marker is removed so rebuilds don't leak listeners.
      const unsub = onLongPress(marker, (e) => onContextMenu(w, e));
      marker.once('remove', unsub);
    }
    if (onDragEnd) marker.on('dragend', (e) => {
      const { lat, lng } = e.target.getLatLng();
      onDragEnd(w, { lat, lon: lng });
    });
    layers.push(marker);
  });
  return layers;
}
