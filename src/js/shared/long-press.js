// --- Touch long-press helper ---
//
// onLongPress(target, handler, { ms, moveTolerance }) -> unsubscribe()
//
// `target` is a Leaflet map or layer (marker). After `ms` of a stationary
// one-finger press, handler({ latlng, originalEvent }) is called. The
// originalEvent is a plain object with clientX/clientY and a no-op
// preventDefault, shaped like what the contextmenu code already consumes.
//
// Why this exists: iOS Safari never fires `contextmenu` on long-press, and
// Chromium/Android does only on some builds. To make long-press the single
// path on touch, native contextmenu events that occur while a finger is down
// are swallowed here (mouse right-click is untouched). The click that follows
// a fired long-press is suppressed twice over: touchend is preventDefault'd,
// and longPressJustFired() lets click handlers (map tap-to-add) bail out.

// Event-based, not time-from-fire: set at touchend of a fired long-press
// (so a finger held past the threshold is still covered), cleared by the
// next touchstart or ~400ms after touchend, so a deliberate later tap is
// never swallowed.
const SUPPRESS_CLICK_MS = 400;
let justFired = false;
let justFiredTimer = null;

function clearJustFired() {
  justFired = false;
  if (justFiredTimer) { clearTimeout(justFiredTimer); justFiredTimer = null; }
}

export function longPressJustFired() {
  return justFired;
}

function elementOf(target) {
  if (typeof target.getContainer === 'function') return target.getContainer();
  if (typeof target.getElement === 'function') return target.getElement();
  return null;
}

function toLatLng(target, touch) {
  if (typeof target.mouseEventToLatLng === 'function') {
    return target.mouseEventToLatLng(touch);
  }
  return typeof target.getLatLng === 'function' ? target.getLatLng() : null;
}

export function onLongPress(target, handler, { ms = 500, moveTolerance = 10 } = {}) {
  const el = elementOf(target);
  if (!el) return () => {};

  let timer = null;
  let touching = false;
  let fired = false;
  let sx = 0, sy = 0;

  const clear = () => { if (timer) { clearTimeout(timer); timer = null; } };

  function onStart(e) {
    clear();
    clearJustFired();
    fired = false;
    touching = true;
    // A marker nested in the map container sees the same touch bubble up;
    // the innermost target owns it so only one menu opens.
    if (e.touches.length !== 1 || e._longPressOwned) return;
    e._longPressOwned = true;
    const t = e.touches[0];
    sx = t.clientX; sy = t.clientY;
    timer = setTimeout(() => {
      timer = null;
      fired = true;
      handler({
        latlng: toLatLng(target, t),
        originalEvent: {
          type: 'longpress', clientX: sx, clientY: sy,
          target: e.target, preventDefault() {}, stopPropagation() {},
        },
      });
    }, ms);
  }

  function onMove(e) {
    if (!timer) return;
    const t = e.touches[0];
    if (!t || Math.hypot(t.clientX - sx, t.clientY - sy) > moveTolerance) clear();
  }

  function onEnd(e) {
    clear();
    if (fired) {
      if (e.cancelable) e.preventDefault();  // no synthesised click
      clearJustFired();
      justFired = true;
      justFiredTimer = setTimeout(clearJustFired, SUPPRESS_CLICK_MS);
    }
    if (e.touches.length === 0) touching = false;
  }

  function onCancel() { clear(); touching = false; fired = false; }

  function onNativeContextMenu(e) {
    if (!touching) return;  // real mouse right-click: leave alone
    e.preventDefault();
    e.stopImmediatePropagation();
  }

  el.addEventListener('touchstart', onStart, { passive: true });
  el.addEventListener('touchmove', onMove, { passive: true });
  el.addEventListener('touchend', onEnd);
  el.addEventListener('touchcancel', onCancel, { passive: true });
  el.addEventListener('contextmenu', onNativeContextMenu, true);

  return function unsubscribe() {
    clear();
    el.removeEventListener('touchstart', onStart);
    el.removeEventListener('touchmove', onMove);
    el.removeEventListener('touchend', onEnd);
    el.removeEventListener('touchcancel', onCancel);
    el.removeEventListener('contextmenu', onNativeContextMenu, true);
  };
}
