/**
 * Bookmarks tab: toolbar (search, sort, new), card grid, tag filtering.
 * initBookmarksTab(container, { getTagNames, onChanged })
 *   -> { load, setTag }
 */

import { api } from './api-client.js';
import { showBookmarkEditor } from './bookmark-editor.js';
import { showBookmarkCreate } from './bookmark-create-modal.js';

const SORTS = {
  updated: null, // server order (updated desc)
  name: (a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }),
  created: (a, b) => String(b.created_at).localeCompare(String(a.created_at)),
};

export function formatCoords(lat, lon) {
  return `${Number(lat).toFixed(5)}, ${Number(lon).toFixed(5)}`;
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

export function initBookmarksTab(container, { getTagNames, onChanged }) {
  let bookmarks = [];
  let search = '';
  let sort = 'updated';
  let activeTag = null;
  let loaded = false;

  container.innerHTML = '';
  const toolbar = el('div', 'bookmarks-toolbar');
  const searchInput = el('input');
  searchInput.type = 'search';
  searchInput.id = 'bookmark-search';
  searchInput.placeholder = 'Search bookmarks...';
  searchInput.setAttribute('aria-label', 'Search bookmarks');
  const sortSel = el('select');
  sortSel.id = 'bookmark-sort';
  sortSel.setAttribute('aria-label', 'Sort bookmarks');
  [['updated', 'Recently updated'], ['name', 'Name'], ['created', 'Recently created']]
    .forEach(([v, t]) => {
      const o = el('option', null, t);
      o.value = v;
      sortSel.appendChild(o);
    });
  const newBtn = el('button', 'btn btn-primary', '+ New bookmark');
  newBtn.id = 'btn-new-bookmark';
  newBtn.type = 'button';
  toolbar.append(searchInput, sortSel, newBtn);

  const list = el('div', 'bookmark-grid');
  list.id = 'bookmark-list';
  container.append(toolbar, list);

  function visible() {
    const q = search.trim().toLowerCase();
    let out = bookmarks.filter((b) => {
      if (activeTag && !b.tags.some((t) => t.name === activeTag)) return false;
      if (!q) return true;
      return b.name.toLowerCase().includes(q)
        || b.tags.some((t) => t.name.toLowerCase().includes(q));
    });
    if (SORTS[sort]) out = [...out].sort(SORTS[sort]);
    return out;
  }

  function renderCard(b) {
    const card = el('div', 'bookmark-card');
    card.tabIndex = 0;
    card.setAttribute('role', 'button');
    card.dataset.id = b.id;

    const thumb = el('div', 'bookmark-thumb');
    if (b.thumb_url) {
      const img = document.createElement('img');
      img.src = b.thumb_url;
      img.alt = '';
      img.loading = 'lazy';
      thumb.appendChild(img);
    } else {
      thumb.appendChild(el('span', 'bookmark-thumb-placeholder', '⚑'));
    }
    card.appendChild(thumb);

    const body = el('div', 'bookmark-body');
    body.appendChild(el('div', 'bookmark-name', b.name));
    body.appendChild(el('div', 'bookmark-coords', formatCoords(b.lat, b.lon)));
    if (b.tags.length) {
      const tagsEl = el('div', 'bookmark-tags');
      b.tags.forEach((t) => tagsEl.appendChild(el('span', 'bookmark-tag', t.name)));
      body.appendChild(tagsEl);
    }
    card.appendChild(body);

    const open = () => showBookmarkEditor(b.id, {
      tagNames: getTagNames(),
      onChanged: async () => { await load(); if (onChanged) await onChanged(); },
    });
    card.addEventListener('click', open);
    card.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); }
    });
    return card;
  }

  function render() {
    list.innerHTML = '';
    const items = visible();
    if (!items.length) {
      list.appendChild(el('p', 'empty-message',
        bookmarks.length ? 'No bookmarks match.' : 'No bookmarks yet. Add one with "+ New bookmark".'));
      return;
    }
    items.forEach((b) => list.appendChild(renderCard(b)));
  }

  async function load() {
    try {
      bookmarks = await api.listBookmarks();
      loaded = true;
      render();
    } catch (err) {
      list.textContent = `Error loading bookmarks: ${err.message}`;
    }
  }

  searchInput.addEventListener('input', () => { search = searchInput.value; render(); });
  sortSel.addEventListener('change', () => { sort = sortSel.value; render(); });
  newBtn.addEventListener('click', () => showBookmarkCreate({
    onCreated: async () => { await load(); if (onChanged) await onChanged(); },
  }));

  return {
    load,
    isLoaded: () => loaded,
    setTag(name) { activeTag = name; render(); },
  };
}
