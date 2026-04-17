// --- Shared sidebar editor: list, tabs, drag-reorder, collapse ---
//
// Consumed by src/js/create/app.js (M1) and src/js/analysis/edit-panel.js (M2).
// Emits callbacks for reorder / update / remove — owning page decides how to
// persist.

import Sortable from 'sortablejs';

const TAB_ALL = 'all';
const TAB_STOPS = 'stops';
const TAB_WAYPOINTS = 'waypoints';

/**
 * Mount the editor into the given container element.
 * @param {HTMLElement} container
 * @param {Object} handlers  { onReorder(orderedIds), onUpdate(wptId, patch),
 *                             onRemove(wptId), onCollapseToggle(isCollapsed) }
 * @returns API: { setWaypoints(list), setTotals({distanceKm, durationS}),
 *                 getState(): {collapsed, tab} }
 */
export function mountWaypointEditor(container, handlers = {}) {
  container.innerHTML = `
    <div class="wpe">
      <div class="wpe-head">
        <strong>Route stops &amp; waypoints</strong>
        <button class="wpe-collapse" title="Collapse panel" type="button">▶</button>
      </div>
      <div class="wpe-tabs">
        <div class="wpe-tab active" data-tab="${TAB_ALL}"
             title="All route points — both stops and waypoints, in visit order.">
          All<span class="wpe-count" data-count="all">(0)</span>
        </div>
        <div class="wpe-tab" data-tab="${TAB_STOPS}"
             title="Stops — locations where an extended stop is scheduled (visits, breaks, destinations). Stops carry dwell-time for ETA calculation.">
          🛑 Stops<span class="wpe-count" data-count="stops">(0)</span>
        </div>
        <div class="wpe-tab" data-tab="${TAB_WAYPOINTS}"
             title="Waypoints — transit-only points that shape the route but aren't destinations. Use to force the route along a specific path (e.g. a preferred pass or fire trail). No dwell time.">
          ◆ WP<span class="wpe-count" data-count="waypoints">(0)</span>
        </div>
      </div>
      <div class="wpe-totals">
        <span>Distance: <strong data-totals-distance>—</strong></span>
        <span>Drive: <strong data-totals-time>—</strong></span>
      </div>
      <ul class="wpe-list"></ul>
      <div class="wpe-empty">Click the map to add your first waypoint.</div>
    </div>
  `;

  const listEl = container.querySelector('.wpe-list');
  const emptyEl = container.querySelector('.wpe-empty');
  const collapseBtn = container.querySelector('.wpe-collapse');
  const totalsDist = container.querySelector('[data-totals-distance]');
  const totalsTime = container.querySelector('[data-totals-time]');
  const counts = {
    [TAB_ALL]:        container.querySelector('[data-count="all"]'),
    [TAB_STOPS]:      container.querySelector('[data-count="stops"]'),
    [TAB_WAYPOINTS]:  container.querySelector('[data-count="waypoints"]'),
  };

  let state = {
    waypoints: [],
    tab: TAB_ALL,
    collapsed: false,
  };

  // --- Tab switching ---
  container.querySelectorAll('.wpe-tab').forEach(tabEl => {
    tabEl.addEventListener('click', () => {
      state.tab = tabEl.dataset.tab;
      container.querySelectorAll('.wpe-tab').forEach(t => t.classList.toggle('active', t === tabEl));
      render();
    });
  });

  // --- Collapse toggle ---
  collapseBtn.addEventListener('click', () => {
    state.collapsed = !state.collapsed;
    container.classList.toggle('wpe-collapsed', state.collapsed);
    collapseBtn.textContent = state.collapsed ? '◀' : '▶';
    if (handlers.onCollapseToggle) handlers.onCollapseToggle(state.collapsed);
  });

  // --- Sortable ---
  Sortable.create(listEl, {
    handle: '.wpe-handle',
    animation: 150,
    onEnd: () => {
      const orderedIds = Array.from(listEl.querySelectorAll('[data-wpt-id]'))
        .map(el => Number(el.dataset.wptId));
      if (state.tab === TAB_ALL && handlers.onReorder) {
        handlers.onReorder(orderedIds);
      } else {
        render();
      }
    },
  });

  function render() {
    const filtered = state.waypoints.filter(w =>
      state.tab === TAB_ALL
      || (state.tab === TAB_STOPS && w.kind === 'stop')
      || (state.tab === TAB_WAYPOINTS && w.kind === 'waypoint')
    );
    emptyEl.style.display = state.waypoints.length ? 'none' : '';
    listEl.innerHTML = '';
    filtered.forEach((w) => {
      const actualIdx = state.waypoints.indexOf(w);
      const visitN = actualIdx + 1;
      const li = document.createElement('li');
      li.className = `wpe-item wpe-item-${w.kind}`;
      li.dataset.wptId = w.id;
      li.innerHTML = `
        <span class="wpe-handle" title="Drag to reorder">⋮⋮</span>
        <span class="wpe-icon wpe-icon-${w.kind}">${w.kind === 'stop' ? visitN : `<span>${visitN}</span>`}</span>
        <div class="wpe-body">
          <div class="wpe-name">${escape(w.name)}${w.pin_role ? ` <span class="wpe-badge">${w.pin_role === 'start' ? 'Start' : 'End'}</span>` : ''}</div>
          <div class="wpe-sub">${escape(w.address || (w.lat != null ? `${w.lat.toFixed(4)}, ${w.lon.toFixed(4)}` : ''))}</div>
        </div>
        <button class="wpe-remove" title="Remove" type="button">✕</button>
      `;
      li.querySelector('.wpe-remove').addEventListener('click', (e) => {
        e.stopPropagation();
        if (handlers.onRemove) handlers.onRemove(w.id);
      });
      listEl.appendChild(li);
    });

    counts[TAB_ALL].textContent = `(${state.waypoints.length})`;
    counts[TAB_STOPS].textContent = `(${state.waypoints.filter(w => w.kind === 'stop').length})`;
    counts[TAB_WAYPOINTS].textContent = `(${state.waypoints.filter(w => w.kind === 'waypoint').length})`;
  }

  function escape(s) {
    return String(s || '').replace(/[&<>"']/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  return {
    setWaypoints(list) {
      state.waypoints = list.slice();
      render();
    },
    setTotals({ distanceKm, durationS }) {
      totalsDist.textContent = distanceKm != null ? `${distanceKm.toFixed(1)} km` : '—';
      totalsTime.textContent = durationS != null ? `${Math.round(durationS / 60)} min` : '—';
    },
    getState() {
      return { collapsed: state.collapsed, tab: state.tab };
    },
  };
}
