// --- Main application orchestration ---

// Shared mutable state
let rangeVisible = {};

async function main() {
  const { points, trackName } = await loadGPX();

  document.getElementById('track-name').textContent = trackName;

  // Compute distances once (independent of settings)
  const totalDist = computeDistances(points);

  // Current analysis settings
  let settings = loadAnalysisSettings();
  let stats = processTrackData(points, settings);

  // --- Settings controls ---
  const smoothSlider = document.getElementById('set-smooth');
  const smoothVal = document.getElementById('set-smooth-val');
  const gradDistSlider = document.getElementById('set-graddist');
  const gradDistVal = document.getElementById('set-graddist-val');
  const presetSelect = document.getElementById('set-preset');

  const PRESETS = {
    raw:     { smoothWindow: 1,  gradientDist: 0 },
    detail:  { smoothWindow: 3,  gradientDist: 25 },
    default: { smoothWindow: 7,  gradientDist: 100 },
    smooth:  { smoothWindow: 15, gradientDist: 200 },
  };

  function updateSettingsUI() {
    smoothSlider.value = settings.smoothWindow;
    smoothVal.textContent = settings.smoothWindow + ' pt';
    gradDistSlider.value = settings.gradientDist;
    gradDistVal.textContent = settings.gradientDist + 'm';

    // Match preset or show custom
    const match = Object.entries(PRESETS).find(([, v]) =>
      v.smoothWindow === settings.smoothWindow && v.gradientDist === settings.gradientDist
    );
    presetSelect.value = match ? match[0] : '';
  }

  function applySettings(newSettings) {
    settings = newSettings;
    saveAnalysisSettings(settings);
    stats = processTrackData(points, settings);
    updateSettingsUI();
    refreshAll();
  }

  smoothSlider.addEventListener('input', () => {
    applySettings({ ...settings, smoothWindow: parseInt(smoothSlider.value) });
  });

  gradDistSlider.addEventListener('input', () => {
    applySettings({ ...settings, gradientDist: parseInt(gradDistSlider.value) });
  });

  presetSelect.addEventListener('change', () => {
    const preset = PRESETS[presetSelect.value];
    if (preset) applySettings({ ...preset });
  });

  updateSettingsUI();

  // --- Render stats ---
  function renderStats() {
    const { minEle, maxEle, totalGain, totalLoss, maxGrad, minGrad } = stats;
    document.getElementById('stats').innerHTML = `
      <div class="stat"><div class="value">${(totalDist/1000).toFixed(1)} km</div><div class="label">Distance</div></div>
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
  renderStats();

  // --- Visibility state ---
  function resetVisibility() {
    rangeVisible = {};
    activeRanges().forEach(r => {
      rangeVisible[r.label] = useAbsoluteMode ? r.min >= 10 : true;
    });
  }
  resetVisibility();

  // Gradient sections (mutable ref so hover panel sees updates)
  const gradSectionsRef = { current: computeGradientSections(points) };

  // Init map
  const mapObj = initMap(points, stats);
  const { map, segmentLayers, baseRoute } = mapObj;

  // Rebuild segment colors and sections
  function rebuildSegmentColors() {
    segmentLayers.forEach(line => {
      const g = points[line._pointIndex].gradient;
      line.setStyle({ color: gradientColor(g) });
      line._gradientRange = rangeForGradient(g);
    });
    gradSectionsRef.current = computeGradientSections(points);
  }

  // Init profile
  const profileApi = initProfile(points, stats, mapObj);

  // Apply visibility to map segments and redraw profile
  function applyVisibility() {
    segmentLayers.forEach(line => {
      const visible = rangeVisible[line._gradientRange];
      if (visible && !map.hasLayer(line)) map.addLayer(line);
      if (!visible && map.hasLayer(line)) map.removeLayer(line);
    });
    profileApi.drawProfile();
  }

  // Legend (clickable)
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
      useAbsoluteMode = !useAbsoluteMode;
      resetVisibility();
      rebuildSegmentColors();
      applyVisibility();
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
        applyVisibility();
        renderLegend();
      });
      legendEl.appendChild(item);
    });

    const showBtn = document.createElement('button');
    showBtn.className = 'legend-btn';
    showBtn.textContent = 'Show All';
    showBtn.addEventListener('click', () => {
      activeRanges().forEach(r => rangeVisible[r.label] = true);
      applyVisibility();
      renderLegend();
    });

    const hideBtn = document.createElement('button');
    hideBtn.className = 'legend-btn';
    hideBtn.textContent = 'Hide All';
    hideBtn.addEventListener('click', () => {
      activeRanges().forEach(r => rangeVisible[r.label] = false);
      applyVisibility();
      renderLegend();
    });

    legendEl.appendChild(showBtn);
    legendEl.appendChild(hideBtn);
  }

  // Full refresh when settings change
  function refreshAll() {
    renderStats();
    rebuildSegmentColors();
    resetVisibility();
    applyVisibility();
    renderLegend();
  }

  renderLegend();

  // Init map hover panel and context menu
  initMapHoverPanel(map, points, segmentLayers, baseRoute, gradSectionsRef);
  initContextMenu(map, points, gradSectionsRef);

  // Apply initial visibility (after profile canvas is ready)
  applyVisibility();
}

main().catch(err => {
  document.getElementById('track-subtitle').textContent = 'Error: ' + err.message;
  console.error(err);
});
