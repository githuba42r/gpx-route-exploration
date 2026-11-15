/**
 * "+ New bookmark" modal: click the map (or type) to set coordinates.
 * showBookmarkCreate({ onCreated })
 */

import { api } from './api-client.js';
import { attachTileLayers } from '../shared/map-layers.js';
import { createTagInput } from './tag-input.js';

const DEFAULT_CENTER = [-27.4705, 153.0260];

function parseCoord(text, min, max) {
  const t = String(text).trim();
  if (t === '') return null;
  const n = Number(t);
  return Number.isFinite(n) && n >= min && n <= max ? n : null;
}

export function showBookmarkCreate({ onCreated, tagNames = [] }) {
  const overlay = document.getElementById('bookmark-modal-overlay');
  overlay.innerHTML = '';
  overlay.classList.add('visible');

  const box = document.createElement('div');
  box.id = 'bookmark-create';
  box.className = 'confirm-box bookmark-modal';
  box.innerHTML = `
    <h3 class="modal-title">New bookmark</h3>
    <div class="form-group">
      <label>Name <span class="required">*</span></label>
      <input type="text" class="tag-input bm-name" maxlength="120" />
    </div>
    <div class="form-group">
      <label>Description</label>
      <textarea class="tag-input bm-desc" rows="2"></textarea>
    </div>
    <div class="form-group">
      <label>Tags</label>
      <div class="bm-tags"></div>
    </div>
    <div class="form-group">
      <label>Location (click the map or type coordinates)</label>
      <div id="bookmark-create-map" class="bookmark-map"></div>
    </div>
    <div class="bm-coords">
      <div class="form-group"><label>Latitude</label>
        <input type="text" inputmode="decimal" class="tag-input bm-lat" /></div>
      <div class="form-group"><label>Longitude</label>
        <input type="text" inputmode="decimal" class="tag-input bm-lon" /></div>
    </div>
    <span class="validation-error bm-error" style="display:none"></span>
    <div class="confirm-actions">
      <button type="button" class="btn btn-secondary bm-cancel">Cancel</button>
      <button type="button" class="btn btn-primary bm-save" disabled>Save</button>
    </div>`;
  overlay.appendChild(box);

  const nameIn = box.querySelector('.bm-name');
  const descIn = box.querySelector('.bm-desc');
  const latIn = box.querySelector('.bm-lat');
  const lonIn = box.querySelector('.bm-lon');
  const saveBtn = box.querySelector('.bm-save');
  const errEl = box.querySelector('.bm-error');
  const tagInput = createTagInput(box.querySelector('.bm-tags'), tagNames, () => {});

  let map = null;
  let marker = null;
  let saving = false;

  let closed = false;
  const backdrop = new AbortController();
  function close() {
    if (closed) return;
    closed = true;
    backdrop.abort();
    if (map) { map.remove(); map = null; }
    overlay.classList.remove('visible');
    overlay.innerHTML = '';
  }

  function coords() {
    return [parseCoord(latIn.value, -90, 90), parseCoord(lonIn.value, -180, 180)];
  }

  function validate() {
    const [lat, lon] = coords();
    saveBtn.disabled = saving || !nameIn.value.trim() || lat == null || lon == null;
  }

  function syncMarker() {
    if (!map) return;
    const [lat, lon] = coords();
    if (lat == null || lon == null) return;
    if (marker) marker.setLatLng([lat, lon]);
    else marker = L.marker([lat, lon]).addTo(map);
  }

  if (typeof L !== 'undefined') {
    map = L.map('bookmark-create-map', { zoomControl: true }).setView(DEFAULT_CENTER, 11);
    attachTileLayers(map, { defaultBase: 'CyclOSM (Bicycle)' });
    map.on('click', (e) => {
      const ll = e.latlng.wrap();
      latIn.value = ll.lat.toFixed(5);
      lonIn.value = ll.lng.toFixed(5);
      syncMarker();
      validate();
    });
    setTimeout(() => map && map.invalidateSize(), 0);
  } else {
    box.querySelector('#bookmark-create-map').textContent = 'Map unavailable - type coordinates.';
  }

  [nameIn, latIn, lonIn].forEach((i) => i.addEventListener('input', () => {
    errEl.style.display = 'none';
    if (i !== nameIn) syncMarker();
    validate();
  }));
  box.querySelector('.bm-cancel').addEventListener('click', close);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); },
    { signal: backdrop.signal });

  saveBtn.addEventListener('click', async () => {
    if (saving) return;
    const [lat, lon] = coords();
    if (!nameIn.value.trim() || lat == null || lon == null) return;
    saving = true;
    saveBtn.disabled = true;
    try {
      await api.createBookmark({
        name: nameIn.value.trim(), description: descIn.value.trim(), lat, lon,
        tags: tagInput.getTags(),
      });
    } catch (err) {
      saving = false;
      errEl.textContent = err.message;
      errEl.style.display = '';
      validate();
      return;
    }
    close();
    if (onCreated) await onCreated();
  });

  nameIn.focus();
}
