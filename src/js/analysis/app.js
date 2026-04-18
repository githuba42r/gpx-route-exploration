// --- Main entry point: imports all modules and orchestrates initialization ---

import {
  activeRanges, angleLabel, gradientColor, rangeForGradient,
  useAbsoluteMode, toggleAbsoluteMode, rangeVisible, resetRangeVisible,
} from './gradient.js';
import { loadGPX } from './gpx-loader.js';
import {
  computeDistances, computeGradDist, computeGradientSections,
  loadAnalysisSettings, processTrackData,
} from './track-processor.js';
import { initMap } from './map-init.js';
import { createSegments, rebuildSegmentColors, applyVisibility } from './map-segments.js';
import { createStartEndMarkers, createGradientMarkers, createPosMarker } from './map-markers.js';
import { createHighlight } from './map-highlight.js';
import { initMapHoverPanel } from './map-hover.js';
import { initProfile } from './profile.js';
import { initContextMenu } from './context-menu.js';
import { initSettings } from './settings.js';
import { initNav } from './nav.js';

async function main() {
  const { points, trackName } = await loadGPX();

  document.getElementById('track-name').textContent = trackName;

  // Compute distances once (independent of settings)
  const totalDist = computeDistances(points);

  // Pre-compute smoothed elevations and gradients up front — downstream
  // setup (createGradientMarkers, createSegments, computeGradientSections,
  // profile rendering) reads points[i].gradient / points[i].eleSmooth.
  // initSettings will re-run processTrackData when the user adjusts a slider.
  processTrackData(points, loadAnalysisSettings());

  // Gradient sections (mutable ref so hover panel sees updates)
  const gradSectionsRef = { current: computeGradientSections(points) };

  // --- Map setup ---
  const { map, baseRoute } = initMap(points);
  const segmentLayers = createSegments(map, points);
  createStartEndMarkers(map, points);
  createGradientMarkers(map, points);
  const posMarker = createPosMarker(map, points);

  // --- Visibility state ---
  resetRangeVisible();

  // profileApi is assigned after settings init (refreshAll is only called
  // when a slider fires, never during initSettings itself)
  let profileApi;

  // --- Full refresh callback (called by settings and legend) ---
  function refreshAll() {
    renderStats();
    rebuildSegmentColors(segmentLayers, points, gradSectionsRef);
    resetRangeVisible();
    applyVisibility(map, segmentLayers, profileApi);
    renderLegend();
  }

  // --- Settings ---
  const settingsApi = initSettings(points, refreshAll);

  // --- Selection highlight on the map ---
  const highlight = createHighlight(map, points);

  // --- Profile (init once with correct stats) ---
  // When the user drag-selects a range on the profile, highlight the matching
  // section on the map and pan to it. Reset → clear highlight.
  profileApi = initProfile(points, settingsApi.getStats(), map, posMarker, (sel) => {
    if (!sel) {
      highlight.clear();
      return;
    }
    highlight.setRange(sel);
    const mid = Math.floor((sel.idxStart + sel.idxEnd) / 2);
    map.panTo([points[mid].lat, points[mid].lon]);
  });

  // --- Stats rendering ---
  function renderStats() {
    const stats = settingsApi.getStats();
    const settings = settingsApi.getSettings();
    const { minEle, maxEle, totalGain, totalLoss, maxGrad, minGrad } = stats;
    document.getElementById('stats').innerHTML = `
      <div class="stat"><div class="value">${(totalDist / 1000).toFixed(1)} km</div><div class="label">Distance</div></div>
      <div class="stat"><div class="value">${minEle.toFixed(0)}m</div><div class="label">Min Elevation</div></div>
      <div class="stat"><div class="value">${maxEle.toFixed(0)}m</div><div class="label">Max Elevation</div></div>
      <div class="stat"><div class="value">${totalGain.toFixed(0)}m</div><div class="label">Total Climb</div></div>
      <div class="stat"><div class="value">${totalLoss.toFixed(0)}m</div><div class="label">Total Descent</div></div>
      <div class="stat"><div class="value">${maxGrad.toFixed(1)}%</div><div class="label">Max Gradient</div></div>
      <div class="stat"><div class="value">${minGrad.toFixed(1)}%</div><div class="label">Steepest Descent</div></div>
    `;
    const winLabel = settings.gradientDist > 0 ? settings.gradientDist + 'm window' : 'point-to-point';
    document.getElementById('track-subtitle').textContent =
      `${points.length} trackpoints | Elevation ${stats.minEle.toFixed(0)}m \u2014 ${stats.maxEle.toFixed(0)}m | Smoothing: ${settings.smoothWindow}-pt | Gradient: ${winLabel}`;
  }

  // --- Legend ---
  function renderLegend() {
    const legendEl = document.getElementById('legend');
    legendEl.innerHTML = '';

    const title = document.createElement('span');
    title.className = 'title';
    title.textContent = 'Gradient:';
    legendEl.appendChild(title);

    // Abs/Directional toggle
    const modeBtn = document.createElement('button');
    modeBtn.className = 'legend-btn' + (useAbsoluteMode ? ' active' : '');
    modeBtn.textContent = useAbsoluteMode ? 'Absolute' : 'Directional';
    modeBtn.title = 'Toggle between directional (+/-) and absolute gradient ranges';
    modeBtn.addEventListener('click', () => {
      toggleAbsoluteMode();
      resetRangeVisible();
      rebuildSegmentColors(segmentLayers, points, gradSectionsRef);
      applyVisibility(map, segmentLayers, profileApi);
      renderLegend();
    });
    legendEl.appendChild(modeBtn);

    const gradDist = computeGradDist(points, totalDist);
    activeRanges().forEach(r => {
      const pct = ((gradDist[r.label] || 0) / totalDist * 100).toFixed(1);
      const item = document.createElement('span');
      item.className = 'legend-item' + (rangeVisible[r.label] ? '' : ' disabled');
      const ang = angleLabel(r.min, r.max);
      item.innerHTML = `<span class="legend-swatch" style="background:${r.color}"></span>${r.label} / ${ang} (${pct}%)`;
      item.addEventListener('click', () => {
        rangeVisible[r.label] = !rangeVisible[r.label];
        applyVisibility(map, segmentLayers, profileApi);
        renderLegend();
      });
      legendEl.appendChild(item);
    });

    const showBtn = document.createElement('button');
    showBtn.className = 'legend-btn';
    showBtn.textContent = 'Show All';
    showBtn.addEventListener('click', () => {
      activeRanges().forEach(r => rangeVisible[r.label] = true);
      applyVisibility(map, segmentLayers, profileApi);
      renderLegend();
    });

    const hideBtn = document.createElement('button');
    hideBtn.className = 'legend-btn';
    hideBtn.textContent = 'Hide All';
    hideBtn.addEventListener('click', () => {
      activeRanges().forEach(r => rangeVisible[r.label] = false);
      applyVisibility(map, segmentLayers, profileApi);
      renderLegend();
    });

    legendEl.appendChild(showBtn);
    legendEl.appendChild(hideBtn);
  }

  // --- Initial render ---
  renderStats();
  renderLegend();

  // --- Map hover panel and context menu ---
  initMapHoverPanel(map, points, segmentLayers, baseRoute, gradSectionsRef);
  initContextMenu(map, points, gradSectionsRef);

  // Apply initial visibility (after profile canvas is ready)
  applyVisibility(map, segmentLayers, profileApi);

  // Nav (no-op for now)
  initNav();
  // Edit Route in the nav is now a plain anchor navigating to /create?route_id=<id>
  // (the Create page serves as the editor). No JS needed here.
}

main().catch(err => {
  document.getElementById('track-subtitle').textContent = 'Error: ' + err.message;
  console.error(err);
});
