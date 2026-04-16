/**
 * Route card renderer grouped by category.
 * renderRouteCards(container, routes, categories, handlers)
 */

function formatDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function formatKm(val) {
  return val != null ? `${val.toFixed(1)} km` : '—';
}

function formatElev(min, max) {
  if (min == null && max == null) return '—';
  return `${Math.round(min ?? 0)}m – ${Math.round(max ?? 0)}m`;
}

function formatGradient(asc, desc) {
  const parts = [];
  if (asc != null) parts.push(`+${asc.toFixed(1)}%`);
  if (desc != null) parts.push(`${desc.toFixed(1)}%`);
  return parts.length ? parts.join(' / ') : '—';
}

export function renderRouteCards(container, routes, categories, handlers) {
  container.innerHTML = '';

  if (!routes.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-message';
    empty.textContent = 'No routes yet. Upload a GPX file to get started.';
    container.appendChild(empty);
    return;
  }

  // Group routes by category
  const catMap = new Map();
  categories.forEach((c) => catMap.set(c.id, c));

  const grouped = new Map();
  routes.forEach((r) => {
    const cid = r.category_id;
    if (!grouped.has(cid)) grouped.set(cid, []);
    grouped.get(cid).push(r);
  });

  // Render each category section
  for (const [catId, catRoutes] of grouped) {
    const cat = catMap.get(catId) || { name: 'Unknown', route_count: catRoutes.length };
    const section = document.createElement('div');
    section.className = 'category-section';

    const header = document.createElement('div');
    header.className = 'category-header';
    header.innerHTML = `<span class="collapse-icon">&#9660;</span> <span class="cat-name">${cat.name}</span> <span class="cat-count">(${catRoutes.length})</span>`;
    header.addEventListener('click', () => {
      section.classList.toggle('collapsed');
      header.querySelector('.collapse-icon').innerHTML = section.classList.contains('collapsed') ? '&#9654;' : '&#9660;';
    });
    section.appendChild(header);

    const grid = document.createElement('div');
    grid.className = 'route-grid';

    catRoutes.forEach((route) => {
      const card = document.createElement('div');
      card.className = 'route-card';
      card.addEventListener('click', () => handlers.onOpen(route.id));

      card.innerHTML = `
        <h4 class="route-title">${route.title}</h4>
        <div class="route-meta">
          <span class="meta-item"><span class="meta-label">Distance</span> <span class="meta-val">${formatKm(route.distance_km)}</span></span>
          <span class="meta-item"><span class="meta-label">Elevation</span> <span class="meta-val">${formatElev(route.min_elevation, route.max_elevation)}</span></span>
          <span class="meta-item"><span class="meta-label">Max Gradient</span> <span class="meta-val">${formatGradient(route.max_gradient_asc, route.max_gradient_desc)}</span></span>
          <span class="meta-item"><span class="meta-label">Uploaded</span> <span class="meta-val">${formatDate(route.created_at)}</span></span>
          ${route.last_accessed ? `<span class="meta-item"><span class="meta-label">Last viewed</span> <span class="meta-val">${formatDate(route.last_accessed)}</span></span>` : ''}
        </div>
        <div class="route-actions"></div>
      `;

      // Action buttons (stop propagation so card click doesn't fire)
      const actionsEl = card.querySelector('.route-actions');
      [
        { label: 'Edit', handler: () => handlers.onEdit(route.id) },
        { label: 'Move', handler: () => handlers.onMove(route.id) },
        { label: 'Delete', handler: () => handlers.onDelete(route.id) },
      ].forEach(({ label, handler }) => {
        const btn = document.createElement('button');
        btn.className = `btn btn-sm ${label === 'Delete' ? 'btn-danger' : 'btn-secondary'}`;
        btn.textContent = label;
        btn.addEventListener('click', (e) => { e.stopPropagation(); handler(); });
        actionsEl.appendChild(btn);
      });

      grid.appendChild(card);
    });

    section.appendChild(grid);
    container.appendChild(section);
  }
}
