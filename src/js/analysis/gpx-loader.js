// --- GPX file loading and parsing ---

/**
 * Load and parse a GPX file.
 * Reads the URL from <link rel="gpx"> or document.body.dataset.gpxFile.
 * Returns { points, trackName }.
 */
export async function loadGPX() {
  const gpxFiles = document.querySelectorAll('link[rel="gpx"]');
  let gpxUrl;
  if (gpxFiles.length > 0) {
    gpxUrl = gpxFiles[0].href;
  } else {
    gpxUrl = document.body.dataset.gpxFile || null;
  }

  if (!gpxUrl) {
    throw new Error('No GPX file specified. Set data-gpx-file on <body>.');
  }

  const resp = await fetch(gpxUrl);
  if (!resp.ok) throw new Error(`Failed to load GPX: ${resp.status}`);
  const text = await resp.text();
  const parser = new DOMParser();
  const doc = parser.parseFromString(text, 'text/xml');

  const trkpts = doc.querySelectorAll('trkpt');
  const points = [];
  trkpts.forEach(pt => {
    const lat = parseFloat(pt.getAttribute('lat'));
    const lon = parseFloat(pt.getAttribute('lon'));
    const eleEl = pt.querySelector('ele');
    const ele = eleEl ? parseFloat(eleEl.textContent) : null;
    if (ele !== null) points.push({ lat, lon, ele });
  });

  const nameEl = doc.querySelector('metadata name');
  const trackName = nameEl ? nameEl.textContent : 'GPX Track';

  return { points, trackName };
}
