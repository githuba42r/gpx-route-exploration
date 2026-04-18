// --- Pick the correct insert position for a line-drag on the generated route ---
//
// When Valhalla returns a route with interior through-points collapsed
// into a single leg (typical when waypoints are kind="waypoint"), one
// polyline spans many waypoints and `leg.from_position` is always the
// first break's position. Relying on that alone inserts every dragged
// point between the first two pins, regardless of where the user
// actually dragged.
//
// This module projects the drag point onto the polyline — picking the
// nearest SEGMENT rather than the nearest VERTEX so a drop at the
// midpoint between two consecutive vertices lands unambiguously on the
// segment that connects them. Each included waypoint's nearest vertex
// index tells us which pair of pins bracket the drop.

/** Squared planar distance between two lat/lng pairs (cheap, no sqrt). */
function sqDist(lat1, lng1, lat2, lng2) {
  const dLat = lat1 - lat2;
  const dLng = lng1 - lng2;
  return dLat * dLat + dLng * dLng;
}

/** Squared distance from (px, py) to the segment a→b. */
function pointToSegmentSqDist(px, py, ax, ay, bx, by) {
  const dx = bx - ax;
  const dy = by - ay;
  const lenSq = dx * dx + dy * dy;
  let t = 0;
  if (lenSq > 0) {
    t = ((px - ax) * dx + (py - ay) * dy) / lenSq;
    if (t < 0) t = 0;
    else if (t > 1) t = 1;
  }
  const cx = ax + t * dx;
  const cy = ay + t * dy;
  return sqDist(px, py, cx, cy);
}

/** Index of the polyline vertex closest to (lat, lng). */
export function nearestPolylineIndex(polylinePoints, lat, lng) {
  let best = -1;
  let bestDist = Infinity;
  for (let i = 0; i < polylinePoints.length; i++) {
    const [plat, plng] = polylinePoints[i];
    const d = sqDist(plat, plng, lat, lng);
    if (d < bestDist) {
      bestDist = d;
      best = i;
    }
  }
  return best;
}

/** Index i of the polyline segment (points[i] → points[i+1]) closest to (lat, lng). */
export function nearestSegmentIndex(polylinePoints, lat, lng) {
  if (polylinePoints.length < 2) return -1;
  let bestIdx = 0;
  let bestDist = Infinity;
  for (let i = 0; i < polylinePoints.length - 1; i++) {
    const [alat, alng] = polylinePoints[i];
    const [blat, blng] = polylinePoints[i + 1];
    const d = pointToSegmentSqDist(lat, lng, alat, alng, blat, blng);
    if (d < bestDist) {
      bestDist = d;
      bestIdx = i;
    }
  }
  return bestIdx;
}

/**
 * Given the ordered waypoint list, the flat array of polyline vertices
 * the route follows, and the drag-origin lat/lng, return the position at
 * which the new waypoint should be inserted.
 *
 * Only included waypoints participate — excluded ones aren't in the
 * polyline so a drag can't meaningfully land between them.
 */
export function insertionPositionForDrag(waypoints, polylinePoints, dragLat, dragLng) {
  if (!polylinePoints || polylinePoints.length < 2) {
    // No route drawn yet — fall back to tail append.
    return waypoints.length;
  }
  const included = waypoints
    .filter(w => w.included !== 0 && w.lat != null && w.lon != null)
    .slice()
    .sort((a, b) => a.position - b.position);
  if (included.length < 2) {
    // Fewer than two included waypoints: nothing meaningful to bracket.
    return (waypoints[waypoints.length - 1]?.position ?? -1) + 1;
  }

  // Each included waypoint's nearest polyline-vertex index. Because
  // the route visits them in order these are monotonically
  // non-decreasing in practice.
  const wpVertexIdx = included.map(w =>
    nearestPolylineIndex(polylinePoints, w.lat, w.lon));

  // Which polyline segment did the drag land on? The start-vertex of
  // that segment tells us the "before" side of the bracket.
  const segIdx = nearestSegmentIndex(polylinePoints, dragLat, dragLng);

  // Walk waypoints in order; the last one whose vertex-index is <=
  // segIdx is the waypoint the drag is "after". Insert right below
  // the next one.
  let fromSlot = 0;
  for (let i = 0; i < wpVertexIdx.length; i++) {
    if (wpVertexIdx[i] <= segIdx) fromSlot = i;
    else break;
  }
  if (fromSlot >= included.length - 1) {
    // Drag landed past the last waypoint's vertex — still insert
    // inside the chain, not after the tail.
    fromSlot = included.length - 2;
  }
  return included[fromSlot].position + 1;
}
