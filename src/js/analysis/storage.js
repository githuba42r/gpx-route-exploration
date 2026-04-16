// --- localStorage key helper with per-route prefixing ---

/**
 * Build a localStorage key, prefixed with the route ID when available.
 * Falls back to the legacy unprefixed key for backwards compatibility.
 */
export function storageKey(base) {
  const routeId = document.body.dataset.routeId;
  return routeId ? `gpx-${routeId}-${base}` : `gpx-${base}`;
}
