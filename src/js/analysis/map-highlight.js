// --- Highlight polyline for a selected track section ---

/**
 * Create a highlight layer that can mark a contiguous range of trackpoints
 * on the map. Returns { setRange, clear } — setRange({idxStart, idxEnd})
 * draws/updates the highlight; clear() removes it.
 */
export function createHighlight(map, points) {
  let layer = null;

  function setRange({ idxStart, idxEnd }) {
    if (idxStart == null || idxEnd == null || idxEnd <= idxStart) {
      clear();
      return;
    }
    const latlngs = [];
    for (let i = idxStart; i <= idxEnd; i++) {
      latlngs.push([points[i].lat, points[i].lon]);
    }
    if (layer) {
      layer.setLatLngs(latlngs);
    } else {
      layer = L.polyline(latlngs, {
        color: '#00e5ff',
        weight: 8,
        opacity: 0.75,
        lineCap: 'round',
        lineJoin: 'round',
        interactive: false,
      });
      layer.addTo(map);
      // Keep highlight below the gradient segments so colors remain visible.
      if (layer.bringToBack) layer.bringToBack();
    }
  }

  function clear() {
    if (layer) {
      map.removeLayer(layer);
      layer = null;
    }
  }

  return { setRange, clear };
}
