/**
 * Mobile bottom sheet for the Create page editor panel.
 *
 * Active only while (max-width: 900px) matches. State lives in
 * data-sheet="peek|half|full" on the panel. The .sheet-handle is the only
 * swipe origin (Pointer Events + touch-action:none on the handle alone) so
 * map panning is untouched. map.invalidateSize() runs after every state
 * change and after the layout flips.
 */
const STATES = ['peek', 'half', 'full'];
const SWIPE_PX = 30;

export function initBottomSheet({ panel, map, handleSelector = '.sheet-handle' }) {
  if (!panel) return null;
  const mq = window.matchMedia('(max-width: 900px)');
  let handle = panel.querySelector(handleSelector);
  if (!handle) {
    handle = document.createElement('div');
    handle.className = 'sheet-handle';
    handle.setAttribute('role', 'button');
    handle.setAttribute('aria-label', 'Resize editor panel');
    handle.innerHTML = '<span class="sheet-grip"></span>';
    panel.prepend(handle);
  }

  const refresh = () => {
    if (!map) return;
    map.invalidateSize();
    // The sheet height animates; re-measure once it settles.
    setTimeout(() => map.invalidateSize(), 250);
  };

  const setState = (next) => {
    if (!STATES.includes(next)) return;
    panel.dataset.sheet = next;
    refresh();
  };
  const step = (dir) => {
    const i = STATES.indexOf(panel.dataset.sheet);
    if (i < 0) return;
    setState(STATES[Math.max(0, Math.min(STATES.length - 1, i + dir))]);
  };

  let startY = null;
  let pointerId = null;
  handle.addEventListener('pointerdown', (e) => {
    if (!mq.matches) return;
    startY = e.clientY;
    pointerId = e.pointerId;
    try { handle.setPointerCapture(e.pointerId); } catch (_) { /* synthetic pointer */ }
  });
  const end = (e) => {
    if (startY === null || e.pointerId !== pointerId) return;
    const dy = e.clientY - startY;
    startY = null;
    pointerId = null;
    if (Math.abs(dy) >= SWIPE_PX) step(dy < 0 ? 1 : -1);
    else if (mq.matches) step(panel.dataset.sheet === 'full' ? -1 : 1); // tap cycles up/down
  };
  handle.addEventListener('pointerup', end);
  handle.addEventListener('pointercancel', () => { startY = null; pointerId = null; });
  handle.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowUp') step(1);
    else if (e.key === 'ArrowDown') step(-1);
  });
  handle.tabIndex = 0;

  const apply = () => {
    if (mq.matches) {
      if (!panel.dataset.sheet) panel.dataset.sheet = 'half';
    } else {
      delete panel.dataset.sheet;
    }
    refresh();
  };
  mq.addEventListener('change', apply);
  apply();

  return { setState, getState: () => panel.dataset.sheet || null };
}
