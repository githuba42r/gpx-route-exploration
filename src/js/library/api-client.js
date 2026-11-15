/**
 * API client for the route library.
 * Shared fetch wrapper and typed methods for every endpoint.
 */

export async function apiFetch(path, options = {}) {
  const headers = { ...options.headers };
  if (!options._skipContentType) {
    headers['Content-Type'] = 'application/json';
  }
  delete options._skipContentType;

  const resp = await fetch(path, { ...options, headers });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ error: resp.statusText }));
    throw new Error(err.error || resp.statusText);
  }
  if (resp.status === 204) return null;
  return resp.json();
}

export const api = {
  // Routes
  getRoutes: (categoryId) =>
    apiFetch(categoryId != null ? `/api/routes?category_id=${categoryId}` : '/api/routes'),
  getRoute: (id) => apiFetch(`/api/routes/${id}`),
  uploadRoute: (formData) =>
    apiFetch('/api/routes', { method: 'POST', body: formData, _skipContentType: true }),
  updateRoute: (id, data) =>
    apiFetch(`/api/routes/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteRoute: (id) =>
    apiFetch(`/api/routes/${id}`, { method: 'DELETE' }),
  moveRoute: (id, categoryId) =>
    apiFetch(`/api/routes/${id}/move`, { method: 'PATCH', body: JSON.stringify({ category_id: categoryId }) }),

  // Categories
  getCategories: () => apiFetch('/api/categories'),
  createCategory: (name, description) =>
    apiFetch('/api/categories', { method: 'POST', body: JSON.stringify({ name, description }) }),
  updateCategory: (id, data) =>
    apiFetch(`/api/categories/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteCategory: (id, moveToDefault) =>
    apiFetch(`/api/categories/${id}${moveToDefault ? '?move_to_default=true' : ''}`, { method: 'DELETE' }),

  // Tags
  getTags: () => apiFetch('/api/tags'),
  setRouteTags: (routeId, tags) =>
    apiFetch(`/api/routes/${routeId}/tags`, { method: 'PUT', body: JSON.stringify({ tags }) }),
  setCategoryTags: (categoryId, tags) =>
    apiFetch(`/api/categories/${categoryId}/tags`, { method: 'PUT', body: JSON.stringify({ tags }) }),
  deleteTag: (id) =>
    apiFetch(`/api/tags/${id}`, { method: 'DELETE' }),

  // Bookmarks
  listBookmarks: () => apiFetch('/api/bookmarks'),
  getBookmark: (id) => apiFetch(`/api/bookmarks/${id}`),
  createBookmark: (data) =>
    apiFetch('/api/bookmarks', { method: 'POST', body: JSON.stringify(data) }),
  updateBookmark: (id, data) =>
    apiFetch(`/api/bookmarks/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteBookmark: (id) =>
    apiFetch(`/api/bookmarks/${id}`, { method: 'DELETE' }),
  setBookmarkTags: (id, tags) =>
    apiFetch(`/api/bookmarks/${id}/tags`, { method: 'PUT', body: JSON.stringify({ tags }) }),
  uploadBookmarkPhoto: (id, file) => {
    const fd = new FormData();
    fd.append('file', file);
    return apiFetch(`/api/bookmarks/${id}/photos`, { method: 'POST', body: fd, _skipContentType: true });
  },
  deleteBookmarkPhoto: (id, photoId) =>
    apiFetch(`/api/bookmarks/${id}/photos/${photoId}`, { method: 'DELETE' }),
  reorderBookmarkPhotos: (id, order) =>
    apiFetch(`/api/bookmarks/${id}/photos/order`, { method: 'PUT', body: JSON.stringify({ order }) }),
};
