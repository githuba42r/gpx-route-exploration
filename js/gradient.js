// --- Gradient color schemes and mode state ---

const DIRECTIONAL_RANGES = [
  { min: -Infinity, max: -10, color: '#1a237e', label: '< -10%' },
  { min: -10, max: -5,       color: '#1565c0', label: '-10 to -5%' },
  { min: -5,  max: -2,       color: '#42a5f5', label: '-5 to -2%' },
  { min: -2,  max: 2,        color: '#66bb6a', label: '-2 to 2% (flat)' },
  { min: 2,   max: 5,        color: '#ffee58', label: '2 to 5%' },
  { min: 5,   max: 8,        color: '#ffa726', label: '5 to 8%' },
  { min: 8,   max: 12,       color: '#ef5350', label: '8 to 12%' },
  { min: 12,  max: 16,       color: '#c62828', label: '12 to 16%' },
  { min: 16,  max: Infinity, color: '#4a148c', label: '> 16%' },
];

const ABSOLUTE_RANGES = [
  { min: 0,  max: 2,        color: '#66bb6a', label: '0 to 2% (flat)' },
  { min: 2,  max: 5,        color: '#ffee58', label: '2 to 5%' },
  { min: 5,  max: 8,        color: '#ffa726', label: '5 to 8%' },
  { min: 8,  max: 12,       color: '#ef5350', label: '8 to 12%' },
  { min: 12, max: 16,       color: '#c62828', label: '12 to 16%' },
  { min: 16, max: Infinity, color: '#4a148c', label: '> 16%' },
];

let useAbsoluteMode = true;

function gradToAngle(g) {
  return Math.atan(g / 100) * (180 / Math.PI);
}

function angleLabel(minPct, maxPct) {
  const a1 = gradToAngle(Math.abs(minPct)).toFixed(1);
  const a2 = gradToAngle(Math.abs(maxPct)).toFixed(1);
  if (!isFinite(minPct) || !isFinite(maxPct)) {
    return isFinite(minPct) ? `> ${a1}\u00b0` : `< ${a2}\u00b0`;
  }
  return `${a1}\u2013${a2}\u00b0`;
}

function activeRanges() {
  return useAbsoluteMode ? ABSOLUTE_RANGES : DIRECTIONAL_RANGES;
}

function effectiveGradient(g) {
  return useAbsoluteMode ? Math.abs(g) : g;
}

function gradientColor(g) {
  const eg = effectiveGradient(g);
  for (const r of activeRanges()) {
    if (eg >= r.min && eg < r.max) return r.color;
  }
  return '#888';
}

function rangeForGradient(g) {
  const eg = effectiveGradient(g);
  for (const r of activeRanges()) {
    if (eg >= r.min && eg < r.max) return r.label;
  }
  return null;
}
