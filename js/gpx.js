// --- GPX parsing, distance, elevation smoothing, gradient calculation ---

function haversine(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat/2)**2 + Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dLon/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}

function smoothElevations(eles, window) {
  const half = Math.floor(window / 2);
  return eles.map((_, i) => {
    let sum = 0, count = 0;
    for (let j = Math.max(0, i - half); j <= Math.min(eles.length - 1, i + half); j++) {
      sum += eles[j]; count++;
    }
    return sum / count;
  });
}

async function loadGPX() {
  // Find the first .gpx file linked or default
  const gpxFiles = document.querySelectorAll('link[rel="gpx"]');
  let gpxUrl;
  if (gpxFiles.length > 0) {
    gpxUrl = gpxFiles[0].href;
  } else {
    // Auto-discover: try to find a .gpx file in the same directory
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

// Default analysis settings
const ANALYSIS_DEFAULTS = { smoothWindow: 7, gradientDist: 100 };
const ANALYSIS_STORAGE_KEY = 'gpx-analysis-settings';

function loadAnalysisSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem(ANALYSIS_STORAGE_KEY));
    return { ...ANALYSIS_DEFAULTS, ...saved };
  } catch { return { ...ANALYSIS_DEFAULTS }; }
}

function saveAnalysisSettings(settings) {
  localStorage.setItem(ANALYSIS_STORAGE_KEY, JSON.stringify(settings));
}

// Cumulative distances only need computing once (they don't change with settings)
function computeDistances(points) {
  let cumDist = 0;
  points[0].dist = 0;
  for (let i = 1; i < points.length; i++) {
    const d = haversine(points[i-1].lat, points[i-1].lon, points[i].lat, points[i].lon);
    cumDist += d;
    points[i].dist = cumDist;
  }
  return cumDist;
}

function processTrackData(points, settings) {
  const { smoothWindow, gradientDist } = settings || loadAnalysisSettings();

  // Smooth elevations
  const rawEles = points.map(p => p.ele);
  const smoothed = smoothElevations(rawEles, smoothWindow);
  points.forEach((p, i) => p.eleSmooth = smoothed[i]);

  // Calculate gradient over minimum distance window
  points[0].gradient = 0;
  for (let i = 1; i < points.length; i++) {
    let j = i - 1;
    while (j > 0 && (points[i].dist - points[j].dist) < gradientDist) j--;
    const dDist = points[i].dist - points[j].dist;
    points[i].gradient = dDist > 1 ? ((points[i].eleSmooth - points[j].eleSmooth) / dDist) * 100 : 0;
  }

  // Compute stats
  const totalDist = points[points.length - 1].dist;
  const minEle = Math.min(...rawEles);
  const maxEle = Math.max(...rawEles);
  let totalGain = 0, totalLoss = 0;
  for (let i = 1; i < points.length; i++) {
    const diff = smoothed[i] - smoothed[i-1];
    if (diff > 0) totalGain += diff; else totalLoss += Math.abs(diff);
  }
  const maxGrad = Math.max(...points.map(p => p.gradient));
  const minGrad = Math.min(...points.map(p => p.gradient));

  return { totalDist, minEle, maxEle, totalGain, totalLoss, maxGrad, minGrad };
}

function computeGradDist(points, totalDist) {
  const gd = {};
  activeRanges().forEach(r => gd[r.label] = 0);
  for (let i = 1; i < points.length; i++) {
    const segLen = points[i].dist - points[i-1].dist;
    const eg = effectiveGradient(points[i].gradient);
    for (const r of activeRanges()) {
      if (eg >= r.min && eg < r.max) { gd[r.label] += segLen; break; }
    }
  }
  return gd;
}

function computeGradientSections(points) {
  const sections = new Array(points.length);
  sections[0] = { startIdx: 0, endIdx: 0, label: rangeForGradient(0) };
  const runs = [];
  let runStart = 1;
  let runLabel = rangeForGradient(points[1].gradient);
  for (let i = 2; i <= points.length; i++) {
    const lbl = i < points.length ? rangeForGradient(points[i].gradient) : null;
    if (lbl !== runLabel || i === points.length) {
      runs.push({ startIdx: runStart, endIdx: i - 1, label: runLabel });
      runStart = i;
      runLabel = lbl;
    }
  }
  for (const run of runs) {
    for (let i = run.startIdx; i <= run.endIdx; i++) {
      sections[i] = run;
    }
  }
  return sections;
}
