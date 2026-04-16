// --- Gradient color schemes, angle helpers, and shared mode state ---

export const DIRECTIONAL_RANGES = [
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

export const ABSOLUTE_RANGES = [
  { min: 0,  max: 2,        color: '#66bb6a', label: '0 to 2% (flat)' },
  { min: 2,  max: 5,        color: '#ffee58', label: '2 to 5%' },
  { min: 5,  max: 8,        color: '#ffa726', label: '5 to 8%' },
  { min: 8,  max: 12,       color: '#ef5350', label: '8 to 12%' },
  { min: 12, max: 16,       color: '#c62828', label: '12 to 16%' },
  { min: 16, max: Infinity, color: '#4a148c', label: '> 16%' },
];

// --- Mutable shared state ---
export let useAbsoluteMode = true;

export function setAbsoluteMode(val) {
  useAbsoluteMode = val;
}

export function toggleAbsoluteMode() {
  useAbsoluteMode = !useAbsoluteMode;
}

/**
 * rangeVisible is a mutable object shared across modules.
 * Importers hold the same object reference — never reassign it,
 * only mutate in place via resetRangeVisible().
 */
export const rangeVisible = {};

export function resetRangeVisible() {
  // Clear all keys in place (preserve the object reference)
  Object.keys(rangeVisible).forEach(k => delete rangeVisible[k]);
  activeRanges().forEach(r => {
    rangeVisible[r.label] = useAbsoluteMode ? r.min >= 10 : true;
  });
}

// --- Helpers ---

export function gradToAngle(g) {
  return Math.atan(g / 100) * (180 / Math.PI);
}

export function angleLabel(minPct, maxPct) {
  const a1 = gradToAngle(Math.abs(minPct)).toFixed(1);
  const a2 = gradToAngle(Math.abs(maxPct)).toFixed(1);
  if (!isFinite(minPct) || !isFinite(maxPct)) {
    return isFinite(minPct) ? `> ${a1}\u00b0` : `< ${a2}\u00b0`;
  }
  return `${a1}\u2013${a2}\u00b0`;
}

export function activeRanges() {
  return useAbsoluteMode ? ABSOLUTE_RANGES : DIRECTIONAL_RANGES;
}

export function effectiveGradient(g) {
  return useAbsoluteMode ? Math.abs(g) : g;
}

export function gradientColor(g) {
  const eg = effectiveGradient(g);
  for (const r of activeRanges()) {
    if (eg >= r.min && eg < r.max) return r.color;
  }
  return '#888';
}

export function rangeForGradient(g) {
  const eg = effectiveGradient(g);
  for (const r of activeRanges()) {
    if (eg >= r.min && eg < r.max) return r.label;
  }
  return null;
}
