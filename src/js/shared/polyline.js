// --- Google encoded-polyline decoder (matches server/routing/gpx_writer.py) ---

/**
 * Decode a Google encoded polyline string into a list of [lat, lon] pairs.
 * Valhalla returns precision 6 by default; legacy Google Maps used 5.
 */
export function decodePolyline(encoded, precision = 6) {
  const factor = Math.pow(10, precision);
  const coords = [];
  let lat = 0, lng = 0, i = 0;
  while (i < encoded.length) {
    for (let k = 0; k < 2; k++) {
      let result = 0, shift = 0, b;
      do {
        b = encoded.charCodeAt(i++) - 63;
        result |= (b & 0x1f) << shift;
        shift += 5;
      } while (b >= 0x20);
      const delta = (result & 1) ? ~(result >> 1) : (result >> 1);
      if (k === 0) lat += delta; else lng += delta;
    }
    coords.push([lat / factor, lng / factor]);
  }
  return coords;
}
