/**
 * Shared CSV import dialog (Library + Create page).
 * Posts to /api/geocode/csv and follows the SSE progress stream.
 */
import Papa from 'papaparse';

const FIELDS = ['name', 'address', 'lat', 'lon', 'description'];
const FIELD_LABELS = {
  name: 'Name', address: 'Address', lat: 'Latitude', lon: 'Longitude', description: 'Description',
};
const ALIASES = {
  name: ['name', 'title'],
  address: ['address', 'addr', 'location'],
  lat: ['lat', 'latitude'],
  lon: ['lon', 'lng', 'long', 'longitude'],
  description: ['description', 'notes', 'note'],
};

export function guessMapping(headers) {
  const mapping = {};
  for (const field of FIELDS) {
    const hit = headers.find((h) => ALIASES[field].includes(String(h).trim().toLowerCase()));
    if (hit !== undefined) mapping[field] = hit;
  }
  return mapping;
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}

export function openCsvImport({ routeId = null, defaultTitle = '', onStart = () => {}, onDone } = {}) {
  document.getElementById('csv-import-overlay')?.remove();
  const overlay = document.createElement('div');
  overlay.id = 'csv-import-overlay';
  overlay.className = 'csv-import-overlay';
  overlay.innerHTML = `
    <div class="csv-import-box">
      <h3 class="csv-import-title">${routeId ? 'Append waypoints from CSV' : 'Import route from CSV'}</h3>
      <input type="file" id="csv-file-input" accept=".csv,text/csv">
      <div id="csv-config" hidden>
        <div id="csv-preview" class="csv-preview"></div>
        <div class="csv-mapping">
          ${FIELDS.map((f) => `<label>${FIELD_LABELS[f]}
            <select id="csv-map-${f}"></select></label>`).join('')}
        </div>
        ${routeId ? '' : '<label class="csv-title-row">Route title <input type="text" id="csv-title"></label>'}
      </div>
      <div id="csv-import-error" class="csv-import-error"></div>
      <div id="csv-progress-wrap" hidden>
        <progress id="csv-progress" value="0" max="1"></progress>
        <span id="csv-progress-text"></span>
      </div>
      <div class="csv-import-actions">
        <button type="button" id="csv-import-close" class="csv-btn">Cancel</button>
        <button type="button" id="csv-import-start" class="csv-btn csv-btn-primary" disabled>Start import</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  const $ = (sel) => overlay.querySelector(sel);
  let file = null;
  let source = null;
  let busy = false;
  let rowCount = 0;

  function close() {
    if (source) { source.close(); source = null; }
    overlay.remove();
  }

  function currentMapping() {
    const m = {};
    for (const f of FIELDS) {
      const v = $(`#csv-map-${f}`).value;
      if (v) m[f] = v;
    }
    return m;
  }

  function refreshStart() {
    const m = currentMapping();
    const ok = !busy && file && (m.address || (m.lat && m.lon));
    $('#csv-import-start').disabled = !ok;
  }

  $('#csv-import-close').addEventListener('click', close);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

  $('#csv-file-input').addEventListener('change', (e) => {
    file = e.target.files[0] || null;
    $('#csv-import-error').textContent = '';
    if (!file) { $('#csv-config').hidden = true; refreshStart(); return; }
    Papa.parse(file, {
      header: true,
      skipEmptyLines: 'greedy',
      complete: (res) => {
        rowCount = res.data.length;
        const headers = res.meta.fields || [];
        const guess = guessMapping(headers);
        for (const f of FIELDS) {
          const sel = $(`#csv-map-${f}`);
          sel.innerHTML = '<option value="">(none)</option>'
            + headers.map((h) => `<option value="${esc(h).replace(/"/g, '&quot;')}">${esc(h)}</option>`).join('');
          sel.value = guess[f] ?? '';
          sel.onchange = refreshStart;
        }
        $('#csv-preview').innerHTML = `<table><thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join('')}</tr></thead>
          <tbody>${res.data.slice(0, 5).map((r) => `<tr>${headers.map((h) => `<td>${esc(r[h])}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
        const titleEl = $('#csv-title');
        if (titleEl) titleEl.value = defaultTitle || file.name.replace(/\.[^.]*$/, '');
        $('#csv-config').hidden = false;
        refreshStart();
      },
      error: (err) => { $('#csv-import-error').textContent = `Could not read CSV: ${err.message}`; },
    });
  });

  $('#csv-import-start').addEventListener('click', async () => {
    const errEl = $('#csv-import-error');
    errEl.textContent = '';
    busy = true;
    refreshStart();
    const fd = new FormData();
    fd.append('file', file);
    fd.append('mapping', JSON.stringify(currentMapping()));
    const titleEl = $('#csv-title');
    if (titleEl && titleEl.value.trim()) fd.append('title', titleEl.value.trim());
    const url = '/api/geocode/csv' + (routeId ? `?route_id=${encodeURIComponent(routeId)}` : '');
    let data;
    try {
      const resp = await fetch(url, { method: 'POST', body: fd });
      data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.error || `Import failed (${resp.status})`);
    } catch (err) {
      errEl.textContent = err.message;
      busy = false;
      refreshStart();
      return;
    }
    onStart(data);
    $('#csv-progress-wrap').hidden = false;
    const prog = $('#csv-progress');
    const text = $('#csv-progress-text');
    const rows = new Map(); // index -> status; idempotent under SSE replay
    prog.max = Math.max(rowCount, 1);
    text.textContent = `0 of ${rowCount}`;
    source = new EventSource(`/api/geocode/csv/${data.job_id}/stream`);
    source.addEventListener('row', (ev) => {
      let row;
      try { row = JSON.parse(ev.data); } catch (_) { return; }
      rows.set(row.index ?? rows.size, row.status);
      const seen = rows.size;
      prog.max = Math.max(rowCount, seen, 1);
      prog.value = seen;
      text.textContent = `${seen} of ${prog.max}`;
    });
    source.addEventListener('done', (ev) => {
      let summary = {};
      try { summary = JSON.parse(ev.data); } catch (_) { /* ignore */ }
      prog.max = summary.total ?? prog.max;
      prog.value = prog.max;
      text.textContent = `${prog.max} of ${prog.max}`;
      source.close();
      source = null;
      close();
      if (onDone) onDone(summary);
    });
    source.onerror = () => {
      if (!source || source.readyState !== EventSource.CLOSED) return;
      source.close();
      source = null;
      busy = false;
      refreshStart();
      const failed = [...rows.values()].filter((st) => st === 'failed').length;
      errEl.textContent = 'The connection to the import progress stream was lost. '
        + 'The import may already have completed on the server. ';
      const rid = data.route_id;
      if (routeId) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.id = 'csv-import-refresh';
        btn.className = 'csv-btn';
        btn.textContent = 'Refresh';
        btn.addEventListener('click', () => {
          close();
          if (onDone) onDone({ route_id: rid, total: rows.size, failed, appended: rows.size - failed });
        });
        errEl.appendChild(btn);
      } else {
        const link = document.createElement('a');
        link.id = 'csv-import-open-route';
        link.href = `/create?route_id=${encodeURIComponent(rid)}`;
        link.textContent = 'Open the route';
        errEl.appendChild(link);
      }
    };
  });
}
