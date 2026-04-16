// --- Map gradient overlay segments and visibility ---

import { gradientColor, rangeForGradient, rangeVisible } from './gradient.js';
import { computeGradientSections } from './track-processor.js';

/**
 * Create colored gradient overlay segments on the map.
 * Returns the array of segment polyline layers.
 */
export function createSegments(map, points) {
  const segmentLayers = [];
  for (let i = 1; i < points.length; i++) {
    const color = gradientColor(points[i].gradient);
    const line = L.polyline(
      [[points[i - 1].lat, points[i - 1].lon], [points[i].lat, points[i].lon]],
      { color, weight: 4, opacity: 0.9 }
    ).addTo(map);
    line._pointIndex = i;
    line._gradientRange = rangeForGradient(points[i].gradient);
    segmentLayers.push(line);
  }
  return segmentLayers;
}

/**
 * Rebuild segment colors and gradient sections after settings change.
 * Updates gradSectionsRef.current in place.
 */
export function rebuildSegmentColors(segmentLayers, points, gradSectionsRef) {
  segmentLayers.forEach(line => {
    const g = points[line._pointIndex].gradient;
    line.setStyle({ color: gradientColor(g) });
    line._gradientRange = rangeForGradient(g);
  });
  gradSectionsRef.current = computeGradientSections(points);
}

/**
 * Show/hide segments based on rangeVisible state and redraw the profile.
 */
export function applyVisibility(map, segmentLayers, profileApi) {
  segmentLayers.forEach(line => {
    const visible = rangeVisible[line._gradientRange];
    if (visible && !map.hasLayer(line)) map.addLayer(line);
    if (!visible && map.hasLayer(line)) map.removeLayer(line);
  });
  profileApi.drawProfile();
}
