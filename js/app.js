// --- Main application orchestration ---

// Shared mutable state
let rangeVisible = {};

async function main() {
  const { points, trackName } = await loadGPX();

  document.getElementById('track-name').textContent = trackName;

  const stats = processTrackData(points);
  const { totalDist, minEle, maxEle, totalGain, totalLoss, maxGrad, minGrad } = stats;

  // Render stats bar
  document.getElementById('stats').innerHTML = `
    <div class="stat"><div class="value">${(totalDist/1000).toFixed(1)} km</div><div class="label">Distance</div></div>
    <div class="stat"><div class="value">${minEle.toFixed(0)}m</div><div class="label">Min Elevation</div></div>
    <div class="stat"><div class="value">${maxEle.toFixed(0)}m</div><div class="label">Max Elevation</div></div>
    <div class="stat"><div class="value">${totalGain.toFixed(0)}m</div><div class="label">Total Climb</div></div>
    <div class="stat"><div class="value">${totalLoss.toFixed(0)}m</div><div class="label">Total Descent</div></div>
    <div class="stat"><div class="value">${maxGrad.toFixed(1)}%</div><div class="label">Max Gradient</div></div>
    <div class="stat"><div class="value">${minGrad.toFixed(1)}%</div><div class="label">Steepest Descent</div></div>
  `;
  document.getElementById('track-subtitle').textContent =
    `${points.length} trackpoints | Elevation ${minEle.toFixed(0)}m \u2014 ${maxEle.toFixed(0)}m | Smoothed (7-pt) | Gradient over 100m window`;

  // Visibility state
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

  // Rebuild segment colors on mode switch
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

  renderLegend();

  // Init map hover panel
  initMapHoverPanel(map, points, segmentLayers, baseRoute, gradSectionsRef);

  // Apply initial visibility (after profile canvas is ready)
  applyVisibility();
}

main().catch(err => {
  document.getElementById('track-subtitle').textContent = 'Error: ' + err.message;
  console.error(err);
});
