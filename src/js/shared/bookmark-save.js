// --- "Save as bookmark" from a marker menu: one POST, toast result ---

import { showToast } from './toast.js';

let pending = false;

async function post(url, body) {
  if (pending) return;           // re-entrancy guard: a second click is a no-op
  pending = true;
  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!resp.ok) {
      let msg = `Could not save bookmark (${resp.status})`;
      try { const j = await resp.json(); if (j && j.error) msg = j.error; } catch { /* keep default */ }
      showToast(msg);
      return;
    }
    showToast('Saved to bookmarks', { href: '/#bookmarks', linkText: 'View' });
  } catch (err) {
    showToast(err && err.message ? err.message : 'Could not save bookmark');
  } finally {
    pending = false;
  }
}

/** Copy a DB route waypoint (Create page). */
export function saveBookmarkFromWaypoint(waypointId) {
  return post(`/api/bookmarks/from-waypoint/${encodeURIComponent(waypointId)}`);
}

/** Save an arbitrary point (Analysis page: client-side waypoints). */
export function saveBookmarkPoint({ name, lat, lon }) {
  const n = (String(name || '').trim() || 'Waypoint').slice(0, 120);
  return post('/api/bookmarks', { name: n, lat, lon });
}
