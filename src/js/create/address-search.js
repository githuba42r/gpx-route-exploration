// "Add by address" live search box. Suggestion text comes from Nominatim and
// is therefore untrusted: it is only ever written with textContent.
const DEBOUNCE_MS = 350;
const MIN_CHARS = 3;

export function initAddressSearch({ input, list, status, onSelect }) {
  const bar = input.closest('#address-bar') || input.parentElement;
  let timer = null;
  let seq = 0;
  let controller = null;
  let results = [];
  let active = -1;
  let adding = false;

  function setStatus(text) { status.textContent = text || ''; }

  function setBusy(on) { bar.classList.toggle('is-busy', on); }

  function setActive(i) {
    active = i;
    [...list.children].forEach((li, idx) => {
      const on = idx === i;
      li.classList.toggle('active', on);
      li.setAttribute('aria-selected', on ? 'true' : 'false');
    });
  }

  function clear() {
    results = [];
    list.textContent = '';
    active = -1;
  }

  function cancelPending() {
    clearTimeout(timer);
    seq += 1;
    if (controller) { controller.abort(); controller = null; }
    setBusy(false);
  }

  function render(items) {
    clear();
    results = items;
    items.forEach((it, idx) => {
      const li = document.createElement('li');
      li.setAttribute('role', 'option');
      li.textContent = it.display_name;
      // mousedown so the pick lands before the input's blur handling.
      li.addEventListener('mousedown', (e) => { e.preventDefault(); choose(idx); });
      list.appendChild(li);
    });
  }

  async function choose(idx) {
    if (adding) return;
    const it = results[idx];
    if (!it) return;
    adding = true;
    input.readOnly = true;
    const name = String(it.display_name).split(',')[0].trim() || it.display_name;
    cancelPending();
    try {
      await onSelect({
        name,
        address: it.display_name,
        lat: parseFloat(it.lat),
        lon: parseFloat(it.lon),
      });
    } catch (err) {
      // Keep the query and suggestions so the user can retry.
      setStatus('Could not add stop');
      return;
    } finally {
      adding = false;
      input.readOnly = false;
    }
    clear();
    setStatus('');
    input.value = '';
  }

  async function search(q) {
    const mine = ++seq;
    if (controller) controller.abort();
    controller = new AbortController();
    setBusy(true);
    setStatus('');
    try {
      const resp = await fetch(
        `/api/geocode/search?q=${encodeURIComponent(q)}&limit=5`,
        { signal: controller.signal });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      if (mine !== seq) return;
      render(Array.isArray(data) ? data : []);
      setStatus(results.length ? '' : 'No matches');
    } catch (err) {
      if (mine !== seq || (err && err.name === 'AbortError')) return;
      clear();
      setStatus('Address search unavailable');
    } finally {
      if (mine === seq) { setBusy(false); controller = null; }
    }
  }

  input.addEventListener('input', () => {
    cancelPending();
    const q = input.value.trim();
    if (q.length < MIN_CHARS) { clear(); setStatus(''); return; }
    timer = setTimeout(() => search(q), DEBOUNCE_MS);
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' && results.length) {
      e.preventDefault();
      setActive((active + 1) % results.length);
    } else if (e.key === 'ArrowUp' && results.length) {
      e.preventDefault();
      setActive(active <= 0 ? results.length - 1 : active - 1);
    } else if (e.key === 'Enter') {
      if (results.length) {
        e.preventDefault();
        choose(active >= 0 ? active : 0);
      }
    } else if (e.key === 'Escape') {
      cancelPending();
      clear();
      setStatus('');
    }
  });

  // Lets sibling popovers dismiss the suggestions without a synthetic key event.
  return { dismiss() { cancelPending(); clear(); setStatus(''); } };
}
