/**
 * "Convert to recipe" dialog for GPX-only routes on the Analysis page.
 * POSTs /api/routes/<id>/convert-to-recipe then opens the editor.
 */

const DEFAULT_COUNT = 6;

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}

export function openConvertDialog(routeId) {
  document.getElementById('convert-overlay')?.remove();
  const overlay = document.createElement('div');
  overlay.id = 'convert-overlay';
  overlay.className = 'convert-overlay';
  overlay.innerHTML = `
    <div class="convert-box" role="dialog" aria-modal="true" aria-labelledby="convert-title">
      <h3 id="convert-title" class="convert-title">Convert to recipe</h3>
      <p>Converting is lossy: the track is reduced to a small set of editable waypoints.
        Creates N editable waypoints from this track. The track itself is not changed
        until you regenerate it; the original file is kept as a backup.</p>
      <label class="convert-row">Number of waypoints (N)
        <input type="number" id="convert-count" min="2" max="50" step="1" value="${esc(DEFAULT_COUNT)}">
      </label>
      <div id="convert-error" class="convert-error" role="alert"></div>
      <div class="convert-actions">
        <button type="button" id="convert-cancel" class="convert-btn">Cancel</button>
        <button type="button" id="convert-confirm" class="convert-btn convert-btn-primary">Convert</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  const $ = (sel) => overlay.querySelector(sel);
  const countEl = $('#convert-count');
  const confirmBtn = $('#convert-confirm');
  const errEl = $('#convert-error');
  let inFlight = false;

  function close() {
    document.removeEventListener('keydown', onKey, true);
    overlay.remove();
  }
  function onKey(e) {
    if (e.key === 'Escape' && !inFlight) close();
  }
  document.addEventListener('keydown', onKey, true);

  async function confirm() {
    if (inFlight) return;
    inFlight = true;
    errEl.textContent = '';
    confirmBtn.disabled = true;
    confirmBtn.classList.add('is-busy');
    countEl.disabled = true;
    $('#convert-cancel').disabled = true;
    try {
      const count = parseInt(countEl.value, 10);
      const resp = await fetch(`/api/routes/${encodeURIComponent(routeId)}/convert-to-recipe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ count }),
      });
      let data = {};
      try { data = await resp.json(); } catch (_) { /* non-JSON body */ }
      if (!resp.ok) throw new Error(data.error || `Conversion failed (${resp.status})`);
      // Success: navigate away; leave the busy state set.
      window.location.href = `/create?route_id=${encodeURIComponent(routeId)}`;
    } catch (e) {
      errEl.textContent = e.message || 'Conversion failed';
      inFlight = false;
      confirmBtn.disabled = false;
      confirmBtn.classList.remove('is-busy');
      countEl.disabled = false;
      $('#convert-cancel').disabled = false;
    }
  }

  confirmBtn.addEventListener('click', confirm);
  countEl.addEventListener('keydown', (e) => { if (e.key === 'Enter') confirm(); });
  $('#convert-cancel').addEventListener('click', () => { if (!inFlight) close(); });
  overlay.addEventListener('mousedown', (e) => { if (e.target === overlay && !inFlight) close(); });
  countEl.focus();
}

export function initConvertRecipe() {
  const btn = document.getElementById('btn-convert-recipe');
  if (!btn) return;
  btn.addEventListener('click', () => openConvertDialog(document.body.dataset.routeId));
}
