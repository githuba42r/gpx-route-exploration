// --- Thin client for /api/routes/... endpoints ---

async function json(method, url, body) {
  const resp = await fetch(url, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`${method} ${url} → ${resp.status}: ${text}`);
  }
  if (resp.status === 204) return null;
  return resp.json();
}

export function createRouteRecipe({ title, profile = 'bicycle', categoryId = null }) {
  const body = { title, profile };
  if (categoryId) body.category_id = categoryId;
  return json('POST', '/api/routes', body);
}

export function getRoute(routeId) {
  return json('GET', `/api/routes/${routeId}`);
}

export function listWaypoints(routeId) {
  return json('GET', `/api/routes/${routeId}/waypoints`);
}

export function appendWaypoint(
  routeId,
  { name, lat, lon, kind, address, description, linked_to_previous },
) {
  return json('POST', `/api/routes/${routeId}/waypoints`,
              { name, lat, lon, kind, address, description, linked_to_previous });
}

export function insertWaypointAt(
  routeId, position,
  { name, lat, lon, kind, address, description, linked_to_previous },
) {
  return json('POST', `/api/routes/${routeId}/waypoints`,
              { name, lat, lon, kind, address, description,
                linked_to_previous, position });
}

export function patchWaypoint(routeId, wptId, patch) {
  return json('PATCH', `/api/routes/${routeId}/waypoints/${wptId}`, patch);
}

export function deleteWaypoint(routeId, wptId) {
  return json('DELETE', `/api/routes/${routeId}/waypoints/${wptId}`);
}

export function reorderWaypoints(routeId, orderedIds) {
  return json('PUT', `/api/routes/${routeId}/waypoints`, { order: orderedIds });
}

export function generateRoute(routeId) {
  return json('POST', `/api/routes/${routeId}/generate`);
}

export function getRoutingPresets() {
  return json('GET', '/api/routing-presets');
}

export function patchRouteOptions(routeId, patch) {
  return json('PATCH', `/api/routes/${routeId}/options`, patch);
}

export function optimiseRoute(routeId) {
  return json('POST', `/api/routes/${routeId}/optimise`);
}
