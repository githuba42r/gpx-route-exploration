import { openCsvImport } from '../shared/csv-import.js';
/**
 * Library page entry point.
 * Fetches data from API and wires up all UI components.
 */

import { api } from './api-client.js';
import { confirmAction } from './confirm-modal.js';
import { renderTagCloud } from './tag-cloud.js';
import { renderRouteCards } from './route-cards.js';
import { renderCategoryPanel } from './category-panel.js';
import { initUpload } from './upload.js';
import { showMetadataEditor } from './metadata-editor.js';

let categories = [];
let routes = [];
let tags = [];
let activeTag = null;

const $ = (sel) => document.querySelector(sel);

async function loadData() {
  [categories, routes, tags] = await Promise.all([
    api.getCategories(),
    api.getRoutes(),
    api.getTags(),
  ]);
}

function filteredRoutes() {
  if (!activeTag) return routes;
  // Tag filtering not available on route list (no tag data in list response).
  // For now, activeTag filtering is a no-op placeholder.
  return routes;
}

function renderAll() {
  renderTagCloud($('#tag-cloud-container'), tags, (tagName) => {
    activeTag = tagName;
    renderAll();
  }, activeTag);

  renderCategoryPanel($('#category-panel'), categories, {
    onCreate: async (name, desc) => {
      try {
        await api.createCategory(name, desc);
        await refresh();
      } catch (err) { alert(err.message); }
    },
    onRename: async (id, name, desc) => {
      try {
        await api.updateCategory(id, { name, description: desc });
        await refresh();
      } catch (err) { alert(err.message); }
    },
    onDelete: async (id) => {
      const ok = await confirmAction('Delete this category? Routes will be moved to Default.');
      if (!ok) return;
      try {
        await api.deleteCategory(id, true);
        await refresh();
      } catch (err) { alert(err.message); }
    },
  });

  renderRouteCards($('#routes-container'), filteredRoutes(), categories, {
    onOpen: (id) => { window.location.href = `/route/${id}`; },
    onEdit: async (id) => {
      const route = routes.find((r) => r.id === id);
      if (!route) return;
      showMetadataEditor(route, async (data) => {
        try {
          await api.updateRoute(id, data);
          await refresh();
        } catch (err) { alert(err.message); }
      });
    },
    onDelete: async (id) => {
      const ok = await confirmAction('Delete this route? This cannot be undone.');
      if (!ok) return;
      try {
        await api.deleteRoute(id);
        await refresh();
      } catch (err) { alert(err.message); }
    },
    onMove: async (id) => {
      const route = routes.find((r) => r.id === id);
      if (!route) return;
      const others = categories.filter((c) => c.id !== route.category_id);
      if (!others.length) return;
      // Simple move: pick first other category, or show a quick selector
      showMoveSelector(id, route.category_id);
    },
  });

  initUpload($('#upload-area'), categories, refresh);
}

function showMoveSelector(routeId, currentCatId) {
  const overlay = document.getElementById('metadata-modal-overlay');
  overlay.innerHTML = '';
  overlay.classList.add('visible');

  const box = document.createElement('div');
  box.className = 'confirm-box';
  box.innerHTML = `
    <h3 class="modal-title">Move to Category</h3>
    <select class="tag-input move-select">
      ${categories.filter((c) => c.id !== currentCatId).map((c) => `<option value="${c.id}">${c.name}</option>`).join('')}
    </select>
    <div class="confirm-actions">
      <button class="btn btn-secondary cancel-move">Cancel</button>
      <button class="btn btn-primary confirm-move">Move</button>
    </div>
  `;
  overlay.appendChild(box);

  function close() { overlay.classList.remove('visible'); overlay.innerHTML = ''; }

  box.querySelector('.cancel-move').addEventListener('click', close);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
  box.querySelector('.confirm-move').addEventListener('click', async () => {
    const catId = parseInt(box.querySelector('.move-select').value, 10);
    close();
    try {
      await api.moveRoute(routeId, catId);
      await refresh();
    } catch (err) { alert(err.message); }
  });
}

async function refresh() {
  await loadData();
  renderAll();
}

document.addEventListener('DOMContentLoaded', async () => {
  // --- New Route button lives in the sidebar, above Categories ---
  const newRouteBtn = document.createElement('button');
  newRouteBtn.className = 'new-route-btn';
  newRouteBtn.textContent = '+ New Route';
  newRouteBtn.addEventListener('click', () => {
    window.location.href = '/create';
  });
  const slot = $('#sidebar-new-route');
  if (slot) slot.appendChild(newRouteBtn);

  const importCsvBtn = document.createElement('button');
  importCsvBtn.id = 'btn-import-csv';
  importCsvBtn.className = 'import-csv-btn';
  importCsvBtn.style.marginTop = '6px';
  importCsvBtn.textContent = '+ Import CSV';
  importCsvBtn.addEventListener('click', () => {
    openCsvImport({
      onDone: ({ route_id }) => {
        window.location.href = `/create?route_id=${route_id}`;
      },
    });
  });
  if (slot) slot.appendChild(importCsvBtn);

  try {
    await loadData();
    renderAll();
  } catch (err) {
    $('#routes-container').textContent = `Error loading data: ${err.message}`;
  }
});
