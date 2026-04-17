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
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
    const eleEl = pt.querySelector('ele');
    // Default elevation to 0 when the trkpt has no <ele> — the whole
    // analysis pipeline (distance, gradient, profile) happily runs on flat
    // data. Previously we dropped such points silently, which left the
    // points array empty and threw 'Cannot set properties of undefined
    // (setting "dist")' inside computeDistances on any GPX without ele.
    const ele = eleEl ? parseFloat(eleEl.textContent) : 0;
    points.push({ lat, lon, ele: Number.isFinite(ele) ? ele : 0 });
  });

  const nameEl = doc.querySelector('metadata name');
  const trackName = nameEl ? nameEl.textContent : 'GPX Track';

  return { points, trackName };
}
