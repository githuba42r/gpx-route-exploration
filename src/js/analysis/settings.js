// --- Analysis settings sliders, presets, and persistence ---

import { loadAnalysisSettings, saveAnalysisSettings, processTrackData } from './track-processor.js';

const PRESETS = {
  raw:     { smoothWindow: 1,  gradientDist: 0 },
  detail:  { smoothWindow: 3,  gradientDist: 25 },
  default: { smoothWindow: 7,  gradientDist: 100 },
  smooth:  { smoothWindow: 15, gradientDist: 200 },
};

/**
 * Initialize analysis settings controls.
 * Returns { settings, stats, onSettingsChange }.
 *
 * @param {Array} points - Track points array (mutated by processTrackData)
 * @param {Function} refreshAll - Callback invoked after settings change
 */
export function initSettings(points, refreshAll) {
  let settings = loadAnalysisSettings();
  let stats = processTrackData(points, settings);

  const smoothSlider = document.getElementById('set-smooth');
  const smoothVal = document.getElementById('set-smooth-val');
  const gradDistSlider = document.getElementById('set-graddist');
  const gradDistVal = document.getElementById('set-graddist-val');
  const presetSelect = document.getElementById('set-preset');

  function updateSettingsUI() {
    smoothSlider.value = settings.smoothWindow;
    smoothVal.textContent = settings.smoothWindow + ' pt';
    gradDistSlider.value = settings.gradientDist;
    gradDistVal.textContent = settings.gradientDist + 'm';

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

  // Return accessors (stats changes on each applySettings call)
  return {
    getSettings: () => settings,
    getStats: () => stats,
  };
}
