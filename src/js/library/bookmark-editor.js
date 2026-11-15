/**
 * Bookmark editor modal: name, description, tags, photo gallery, delete.
 * showBookmarkEditor(id, { tagNames, onChanged })
 */

import Sortable from 'sortablejs';
import { api } from './api-client.js';
import { confirmAction } from './confirm-modal.js';
import { createTagInput } from './tag-input.js';

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

export async function showBookmarkEditor(id, { tagNames = [], onChanged }) {
  const overlay = document.getElementById('bookmark-modal-overlay');
  overlay.innerHTML = '';
  overlay.classList.add('visible');

  let bookmark;
  try {
    bookmark = await api.getBookmark(id);
  } catch (err) {
    overlay.classList.remove('visible');
    alert(err.message);
    return;
  }

  const box = document.createElement('div');
  box.id = 'bookmark-editor';
  box.className = 'confirm-box bookmark-modal';
  box.innerHTML = `
    <h3 class="modal-title">Edit bookmark</h3>
    <div class="form-group">
      <label>Name <span class="required">*</span></label>
      <input type="text" class="tag-input bm-name" maxlength="200" />
    </div>
    <div class="form-group">
      <label>Description</label>
      <textarea class="tag-input bm-desc" rows="3"></textarea>
    </div>
    <div class="form-group">
      <label>Tags</label>
      <div class="bm-tags"></div>
    </div>
    <div class="bm-location"></div>
    <div class="form-group">
      <label>Photos</label>
      <ul class="bm-photos"></ul>
      <label class="btn btn-secondary bm-add-photo">Add photos
        <input type="file" accept="image/jpeg,image/png,image/webp" multiple hidden />
      </label>
    </div>
    <span class="validation-error bm-error" style="display:none"></span>
    <div class="confirm-actions">
      <button type="button" class="btn btn-danger bm-delete">Delete bookmark</button>
      <span class="bm-spacer"></span>
      <button type="button" class="btn btn-secondary bm-close">Close</button>
      <button type="button" class="btn btn-primary bm-save">Save</button>
    </div>`;
  overlay.appendChild(box);

  const nameIn = box.querySelector('.bm-name');
  const descIn = box.querySelector('.bm-desc');
  const photosEl = box.querySelector('.bm-photos');
  const fileIn = box.querySelector('input[type=file]');
  const errEl = box.querySelector('.bm-error');
  const saveBtn = box.querySelector('.bm-save');
  const delBtn = box.querySelector('.bm-delete');

  nameIn.value = bookmark.name || '';
  descIn.value = bookmark.description || '';
  box.querySelector('.bm-location').textContent =
    `${Number(bookmark.lat).toFixed(5)}, ${Number(bookmark.lon).toFixed(5)}`;

  const tagInput = createTagInput(box.querySelector('.bm-tags'), tagNames, () => {});
  tagInput.setTags(bookmark.tags.map((t) => t.name));

  let photos = [...bookmark.photos];
  let busy = false;
  let dirty = false; // anything persisted that the list should reflect

  function showError(msg) {
    errEl.textContent = msg;
    errEl.style.display = msg ? '' : 'none';
  }

  function renderPhotos() {
    photosEl.innerHTML = '';
    photos.forEach((p) => {
      const li = el('li', 'bm-photo');
      li.dataset.photoId = p.id;
      const handle = el('span', 'bm-photo-handle', '☰');
      handle.title = 'Drag to reorder';
      const img = document.createElement('img');
      img.src = p.thumb_url;
      img.alt = '';
      const del = el('button', 'btn btn-danger btn-sm bm-photo-delete', 'Delete');
      del.type = 'button';
      del.addEventListener('click', async () => {
        if (del.disabled) return;
        del.disabled = true;
        try {
          await api.deleteBookmarkPhoto(id, p.id);
          photos = photos.filter((x) => x.id !== p.id);
          dirty = true;
          renderPhotos();
        } catch (err) {
          del.disabled = false;
          showError(err.message);
        }
      });
      li.append(handle, img, del);
      photosEl.appendChild(li);
    });
  }
  renderPhotos();

  Sortable.create(photosEl, {
    handle: '.bm-photo-handle',
    animation: 150,
    onEnd: async () => {
      const order = Array.from(photosEl.querySelectorAll('[data-photo-id]'))
        .map((e) => Number(e.dataset.photoId));
      const before = photos.map((p) => p.id);
      if (order.join() === before.join()) return;
      const byId = new Map(photos.map((p) => [p.id, p]));
      photos = order.map((pid) => byId.get(pid));
      try {
        await api.reorderBookmarkPhotos(id, order);
        dirty = true;
      } catch (err) {
        photos = before.map((pid) => byId.get(pid));
        renderPhotos();
        showError(err.message);
      }
    },
  });

  fileIn.addEventListener('change', async () => {
    const files = Array.from(fileIn.files);
    fileIn.value = '';
    if (!files.length || busy) return;
    busy = true;
    showError('');
    for (const f of files) {
      try {
        const p = await api.uploadBookmarkPhoto(id, f);
        photos.push(p);
        dirty = true;
        renderPhotos();
      } catch (err) {
        showError(`${f.name}: ${err.message}`);
      }
    }
    busy = false;
  });

  async function close() {
    overlay.classList.remove('visible');
    overlay.innerHTML = '';
    if (dirty && onChanged) await onChanged();
  }

  box.querySelector('.bm-close').addEventListener('click', close);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

  let saving = false;
  saveBtn.addEventListener('click', async () => {
    if (saving) return;
    const name = nameIn.value.trim();
    if (!name) { showError('Name is required'); nameIn.focus(); return; }
    saving = true;
    saveBtn.disabled = true;
    try {
      await api.updateBookmark(id, { name, description: descIn.value.trim() });
      await api.setBookmarkTags(id, tagInput.getTags());
    } catch (err) {
      saving = false;
      saveBtn.disabled = false;
      showError(err.message);
      return;
    }
    dirty = true;
    await close();
  });

  let deleting = false;
  delBtn.addEventListener('click', async () => {
    if (deleting) return;
    deleting = true;
    try {
      const ok = await confirmAction('Delete this bookmark and its photos? This cannot be undone.');
      if (!ok) return;
      try {
        await api.deleteBookmark(id);
      } catch (err) {
        showError(err.message);
        return;
      }
      dirty = true;
      await close();
    } finally {
      deleting = false;
    }
  });

  nameIn.focus();
}
