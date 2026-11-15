// Create-page bookmark picker: a popover (full-width panel on mobile) that
// lists saved bookmarks nearest-first and adds the chosen one to the route.
// All bookmark text is user content: it is only ever written via textContent.
import { addWaypointFromBookmark } from './route-api.js';

function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const rad = d => d * Math.PI / 180;
  const a = Math.sin(rad(lat2 - lat1) / 2) ** 2
    + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(rad(lon2 - lon1) / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
}

function fmtDist(km) {
  return km < 1 ? `${Math.round(km * 1000)} m` : `${km < 10 ? km.toFixed(1) : Math.round(km)} km`;
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

export function mountBookmarkPicker({
  button, container, getRouteId, getInsertPosition, getInsertChoices, getMapCenter, onAdded,
}) {
  let items = [];
  let query = '';
  let activeTags = new Set();
  let loadSeq = 0;
  let pending = false;
  let isOpen = false;

  container.hidden = true;
  container.setAttribute('role', 'dialog');
  container.setAttribute('aria-label', 'Add a bookmark to the route');
  button.setAttribute('aria-expanded', 'false');
  button.setAttribute('aria-controls', container.id);

  const search = el('input', 'bp-search');
  search.type = 'search';
  search.placeholder = 'Search bookmarks…';
  search.setAttribute('aria-label', 'Search bookmarks');
  search.autocomplete = 'off';

  const insertWrap = el('label', 'bp-insert-wrap');
  insertWrap.append(el('span', null, 'Insert:'));
  const insertSel = el('select', 'bp-insert');
  insertWrap.append(insertSel);

  const tagBar = el('div', 'bp-tags');
  const list = el('div', 'bp-list');
  const errBox = el('div', 'bp-error');
  errBox.setAttribute('role', 'alert');
  errBox.hidden = true;
  container.append(search, insertWrap, tagBar, errBox, list);

  function setError(msg) {
    errBox.textContent = msg || '';
    errBox.hidden = !msg;
  }

  function buildInsert() {
    insertSel.textContent = '';
    const choices = getInsertChoices ? getInsertChoices() : [];
    insertWrap.hidden = !choices.length;
    const end = el('option', null, 'At end of route');
    end.value = '';
    insertSel.append(end);
    choices.forEach(c => {
      const o = el('option', null, c.label);
      o.value = String(c.position);
      insertSel.append(o);
    });
    const pre = getInsertPosition ? getInsertPosition() : null;
    if (pre != null) insertSel.value = String(pre);
  }

  function selectedPosition() {
    return insertSel.value === '' ? null : Number(insertSel.value);
  }

  function distanceOf(b) {
    const c = getMapCenter && getMapCenter();
    if (!c) return null;
    return haversineKm(c.lat, c.lng, b.lat, b.lon);
  }

  function tagNames(b) {
    return (b.tags || []).map(t => (typeof t === 'string' ? t : t.name));
  }

  function renderTagBar() {
    tagBar.textContent = '';
    const all = [...new Set(items.flatMap(tagNames))].sort();
    tagBar.hidden = !all.length;
    all.forEach(name => {
      const chip = el('button', 'bp-tag', name);
      chip.type = 'button';
      chip.setAttribute('aria-pressed', activeTags.has(name) ? 'true' : 'false');
      chip.addEventListener('click', () => {
        if (activeTags.has(name)) activeTags.delete(name); else activeTags.add(name);
        renderTagBar();
        renderList();
      });
      tagBar.append(chip);
    });
  }

  function visible() {
    const q = query.trim().toLowerCase();
    return items
      .filter(b => {
        if (activeTags.size) {
          const have = new Set(tagNames(b));
          for (const t of activeTags) if (!have.has(t)) return false;
        }
        if (!q) return true;
        const hay = [b.name, b.description, ...tagNames(b)].join('\n').toLowerCase();
        return hay.includes(q);
      })
      .map(b => ({ b, d: distanceOf(b) }))
      .sort((x, y) => (x.d ?? Infinity) - (y.d ?? Infinity));
  }

  function renderList() {
    list.textContent = '';
    if (!items.length) {
      const empty = el('div', 'bp-empty', 'No bookmarks yet. ');
      const a = el('a', null, 'Create one in the Library');
      a.href = '/#bookmarks';
      empty.append(a);
      list.append(empty);
      return;
    }
    const shown = visible();
    if (!shown.length) {
      list.append(el('div', 'bp-none', 'No matching bookmarks'));
      return;
    }
    shown.forEach(({ b, d }) => {
      const row = el('button', 'bp-row');
      row.type = 'button';
      const thumb = el('span', 'bp-thumb');
      if (b.thumb_url) {
        const img = document.createElement('img');
        img.loading = 'lazy';
        img.alt = '';
        img.src = b.thumb_url;
        thumb.append(img);
      }
      const body = el('span', 'bp-body');
      body.append(el('span', 'bp-name', b.name));
      if (d != null) body.append(el('span', 'bp-dist', fmtDist(d)));
      const tags = tagNames(b);
      if (tags.length) {
        const tl = el('span', 'bp-rowtags');
        tags.forEach(t => tl.append(el('span', 'bp-rowtag', t)));
        body.append(tl);
      }
      row.append(thumb, body);
      row.addEventListener('click', () => pick(b, row));
      list.append(row);
    });
  }

  async function load() {
    const mine = ++loadSeq;
    try {
      const resp = await fetch('/api/bookmarks');
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      if (mine !== loadSeq) return;
      items = Array.isArray(data) ? data : (data.items || []);
      renderTagBar();
      renderList();
    } catch (err) {
      if (mine !== loadSeq) return;
      setError('Could not load bookmarks');
    }
  }

  async function pick(b, row) {
    if (pending) return;
    pending = true;
    row.disabled = true;
    setError('');
    try {
      const routeId = await getRouteId();
      const wp = await addWaypointFromBookmark(routeId, {
        bookmark_id: b.id, position: selectedPosition(),
      });
      pending = false;
      close();
      if (onAdded) await onAdded(wp);
    } catch (err) {
      pending = false;
      row.disabled = false;
      setError('Could not add bookmark');
    }
  }

  function open() {
    if (isOpen) return;
    isOpen = true;
    query = '';
    search.value = '';
    activeTags = new Set();
    setError('');
    buildInsert();
    container.hidden = false;
    button.setAttribute('aria-expanded', 'true');
    document.addEventListener('mousedown', onOutside, true);
    document.addEventListener('touchstart', onOutside, true);
    document.addEventListener('keydown', onKey, true);
    load();
  }

  function close({ restoreFocus = false } = {}) {
    if (!isOpen) return;
    isOpen = false;
    loadSeq += 1;
    container.hidden = true;
    button.setAttribute('aria-expanded', 'false');
    document.removeEventListener('mousedown', onOutside, true);
    document.removeEventListener('touchstart', onOutside, true);
    document.removeEventListener('keydown', onKey, true);
    if (restoreFocus) button.focus();
  }

  function onOutside(e) {
    if (container.contains(e.target) || button.contains(e.target)) return;
    close();
  }

  function onKey(e) {
    if (e.key === 'Escape') { e.stopPropagation(); close({ restoreFocus: true }); }
  }

  button.addEventListener('click', () => { if (isOpen) close(); else open(); });
  search.addEventListener('input', () => { query = search.value; renderList(); });

  return { open, close, isOpen: () => isOpen };
}
