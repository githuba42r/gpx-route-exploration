// --- Track data processing: distances, smoothing, gradients, sections ---

import { activeRanges, effectiveGradient, rangeForGradient } from './gradient.js';
import { storageKey } from './storage.js';

// --- Haversine distance (also used by context-menu) ---
export function haversine(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
    Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// --- Elevation smoothing ---
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

// --- Analysis settings persistence ---
const ANALYSIS_DEFAULTS = { smoothWindow: 7, gradientDist: 100 };

export function loadAnalysisSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey('analysis-settings')));
    return { ...ANALYSIS_DEFAULTS, ...saved };
  } catch { return { ...ANALYSIS_DEFAULTS }; }
}

export function saveAnalysisSettings(settings) {
  localStorage.setItem(storageKey('analysis-settings'), JSON.stringify(settings));
}

// --- Cumulative distances (computed once, independent of settings) ---
export function computeDistances(points) {
  let cumDist = 0;
  points[0].dist = 0;
  for (let i = 1; i < points.length; i++) {
    const d = haversine(points[i - 1].lat, points[i - 1].lon, points[i].lat, points[i].lon);
    cumDist += d;
    points[i].dist = cumDist;
  }
  return cumDist;
}

// --- Process track data with current settings ---
export function processTrackData(points, settings) {
  const { smoothWindow, gradientDist } = settings || loadAnalysisSettings();

  const rawEles = points.map(p => p.ele);
  const smoothed = smoothElevations(rawEles, smoothWindow);
  points.forEach((p, i) => p.eleSmooth = smoothed[i]);

  // Gradient over minimum distance window
  points[0].gradient = 0;
  for (let i = 1; i < points.length; i++) {
    let j = i - 1;
    while (j > 0 && (points[i].dist - points[j].dist) < gradientDist) j--;
    const dDist = points[i].dist - points[j].dist;
    points[i].gradient = dDist > 1
      ? ((points[i].eleSmooth - points[j].eleSmooth) / dDist) * 100
      : 0;
  }

  // Stats
  const totalDist = points[points.length - 1].dist;
  const minEle = Math.min(...rawEles);
  const maxEle = Math.max(...rawEles);
  let totalGain = 0, totalLoss = 0;
  for (let i = 1; i < points.length; i++) {
    const diff = smoothed[i] - smoothed[i - 1];
    if (diff > 0) totalGain += diff; else totalLoss += Math.abs(diff);
  }
  const maxGrad = Math.max(...points.map(p => p.gradient));
  const minGrad = Math.min(...points.map(p => p.gradient));

  return { totalDist, minEle, maxEle, totalGain, totalLoss, maxGrad, minGrad };
}

// --- Gradient distribution by range ---
export function computeGradDist(points, totalDist) {
  const gd = {};
  activeRanges().forEach(r => gd[r.label] = 0);
  for (let i = 1; i < points.length; i++) {
    const segLen = points[i].dist - points[i - 1].dist;
    const eg = effectiveGradient(points[i].gradient);
    for (const r of activeRanges()) {
      if (eg >= r.min && eg < r.max) { gd[r.label] += segLen; break; }
    }
  }
  return gd;
}

// --- Gradient sections (contiguous runs of same range) ---
export function computeGradientSections(points) {
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
