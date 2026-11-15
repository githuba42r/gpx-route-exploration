// --- Elevation profile canvas drawing and interaction ---

import { useAbsoluteMode, gradToAngle, gradientColor, rangeForGradient, rangeVisible } from './gradient.js';

// Drag threshold in pixels — drags shorter than this are treated as clicks
// (keeping the existing "click to pan map" behavior).
const DRAG_THRESHOLD_PX = 5;
// Minimum selection width in metres — narrower selections are treated as clicks.
const MIN_SELECTION_M = 50;

/**
 * Initialize the elevation profile canvas with hover/click interaction,
 * plus drag-to-zoom selection with map highlighting.
 *
 * @param {Array}    points
 * @param {Object}   stats     { minEle, maxEle, ... } from processTrackData
 * @param {Object}   map       Leaflet map (for panTo on click)
 * @param {Object}   posMarker Position marker (synced with hover)
 * @param {Function} onSelectionChange  Called with {idxStart, idxEnd, distMin, distMax}
 *                                      when a zoom selection is made, and with
 *                                      null when the view is reset.
 * @returns {Object} { drawProfile, setViewRange, clearViewRange, isZoomed }
 */
export function initProfile(points, stats, map, posMarker, onSelectionChange) {
  const canvas = document.getElementById('profile-canvas');
  const ctx = canvas.getContext('2d');
  const hoverInfo = document.getElementById('hover-info');
  const container = document.getElementById('profile-container');

  const totalDist = points[points.length - 1].dist;
  // Active view range — defaults to the full track.
  let viewRange = { distMin: 0, distMax: totalDist };

  // --- Selection overlay (absolute <div> over the canvas) ---
  let selectionOverlay = container.querySelector('.profile-selection');
  if (!selectionOverlay) {
    selectionOverlay = document.createElement('div');
    selectionOverlay.className = 'profile-selection';
    selectionOverlay.style.display = 'none';
    container.appendChild(selectionOverlay);
  }

  // --- Reset-zoom button ---
  let resetBtn = container.querySelector('.profile-reset-zoom');
  if (!resetBtn) {
    resetBtn = document.createElement('button');
    resetBtn.className = 'profile-reset-zoom';
    resetBtn.type = 'button';
    resetBtn.textContent = 'Reset Zoom';
    resetBtn.style.display = 'none';
    container.appendChild(resetBtn);
  }
  resetBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    clearViewRange();
  });

  // --- Elevation range helpers ---
  function eleBoundsForRange(distMin, distMax) {
    let lo = Infinity, hi = -Infinity;
    for (const p of points) {
      if (p.dist < distMin || p.dist > distMax) continue;
      const e = p.eleSmooth != null ? p.eleSmooth : p.ele;
      if (e < lo) lo = e;
      if (e > hi) hi = e;
    }
    // Fallback — if no points in range (shouldn't happen with a valid range),
    // use the initial stats.
    if (!isFinite(lo) || !isFinite(hi)) return { minEle: stats.minEle, maxEle: stats.maxEle };
    return { minEle: lo, maxEle: hi };
  }

  function drawProfile() {
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const W = rect.width;
    const H = rect.height;
    const padL = 50, padR = 16, padT = 16, padB = 30;
    const plotW = W - padL - padR;
    const plotH = H - padT - padB;

    const { distMin, distMax } = viewRange;
    const distSpan = Math.max(1, distMax - distMin);
    const { minEle: vMinEle, maxEle: vMaxEle } = eleBoundsForRange(distMin, distMax);
    const eleMin = vMinEle - 10;
    const eleMax = vMaxEle + 20;
    const eleRange = eleMax - eleMin;

    function xFor(dist) { return padL + ((dist - distMin) / distSpan) * plotW; }
    function yFor(ele) { return padT + plotH - ((ele - eleMin) / eleRange) * plotH; }

    // Background
    ctx.fillStyle = '#16213e';
    ctx.fillRect(0, 0, W, H);

    // Grid — elevation
    ctx.strokeStyle = '#1a2a4a';
    ctx.lineWidth = 0.5;
    const eleStep = eleRange > 300 ? 100 : eleRange > 150 ? 50 : 25;
    for (let e = Math.ceil(eleMin / eleStep) * eleStep; e <= eleMax; e += eleStep) {
      const y = yFor(e);
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke();
      ctx.fillStyle = '#6a7a9a';
      ctx.font = '10px sans-serif';
      ctx.textAlign = 'right';
      ctx.fillText(`${e}m`, padL - 4, y + 3);
    }

    // Grid — distance
    const distStep = distSpan > 40000 ? 10000
                  : distSpan > 20000 ? 5000
                  : distSpan > 5000  ? 2000
                  : distSpan > 1000  ? 500
                  : 100;
    const firstTick = Math.ceil(distMin / distStep) * distStep;
    for (let d = firstTick; d <= distMax; d += distStep) {
      const x = xFor(d);
      ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, padT + plotH); ctx.stroke();
      ctx.fillStyle = '#6a7a9a';
      ctx.font = '10px sans-serif';
      ctx.textAlign = 'center';
      const label = distStep >= 1000
        ? `${(d / 1000).toFixed(0)} km`
        : `${(d / 1000).toFixed(1)} km`;
      ctx.fillText(label, x, H - padB + 14);
    }

    // Profile — filled + outlined, clipped to the view range
    for (let i = 1; i < points.length; i++) {
      const d1 = points[i - 1].dist;
      const d2 = points[i].dist;
      if (d2 < distMin || d1 > distMax) continue;
      const x1 = xFor(d1);
      const x2 = xFor(d2);
      const y1 = yFor(points[i - 1].eleSmooth);
      const y2 = yFor(points[i].eleSmooth);
      const yBase = yFor(eleMin);
      const rng = rangeForGradient(points[i].gradient);
      const visible = rangeVisible[rng];

      if (visible) {
        ctx.fillStyle = gradientColor(points[i].gradient) + '60';
        ctx.beginPath();
        ctx.moveTo(x1, yBase);
        ctx.lineTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.lineTo(x2, yBase);
        ctx.closePath();
        ctx.fill();

        ctx.strokeStyle = gradientColor(points[i].gradient);
        ctx.lineWidth = 1.5;
      } else {
        ctx.strokeStyle = '#ff5f15';
        ctx.lineWidth = 1;
      }
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    }

    return { W, H, padL, padR, padT, padB, plotW, plotH, distMin, distMax, distSpan, eleMin, eleRange, xFor, yFor };
  }

  let profileParams = drawProfile();
  window.addEventListener('resize', () => { profileParams = drawProfile(); });

  // --- View-range API ---
  function findIdxAtOrAfter(dist) {
    for (let i = 0; i < points.length; i++) if (points[i].dist >= dist) return i;
    return points.length - 1;
  }
  function findIdxAtOrBefore(dist) {
    for (let i = points.length - 1; i >= 0; i--) if (points[i].dist <= dist) return i;
    return 0;
  }

  function setViewRange({ distMin, distMax }) {
    distMin = Math.max(0, Math.min(totalDist, distMin));
    distMax = Math.max(0, Math.min(totalDist, distMax));
    if (distMax - distMin < MIN_SELECTION_M) return;
    viewRange = { distMin, distMax };
    profileParams = drawProfile();
    resetBtn.style.display = 'block';
    if (onSelectionChange) {
      onSelectionChange({
        distMin, distMax,
        idxStart: findIdxAtOrAfter(distMin),
        idxEnd: findIdxAtOrBefore(distMax),
      });
    }
  }

  function clearViewRange() {
    viewRange = { distMin: 0, distMax: totalDist };
    profileParams = drawProfile();
    resetBtn.style.display = 'none';
    if (onSelectionChange) onSelectionChange(null);
  }

  // --- Hover ---
  function distAtClientX(clientX) {
    const rect = canvas.getBoundingClientRect();
    const mx = clientX - rect.left;
    const { padL, plotW, distMin, distSpan } = profileParams;
    return distMin + ((mx - padL) / plotW) * distSpan;
  }

  // Touch devices emit compatibility mouse events after a touch; ignore them
  // so the pointer path below is the only one that handles touch input.
  let lastTouchTs = -Infinity;
  const TOUCH_MOUSE_GUARD_MS = 800;
  function isCompatMouse() { return performance.now() - lastTouchTs < TOUCH_MOUSE_GUARD_MS; }

  // Show hover info + map marker for clientX. Returns false when outside the view.
  function showHoverAt(clientX) {
    const { distMin, distMax } = profileParams;
    const dist = distAtClientX(clientX);
    if (dist < distMin || dist > distMax) { hoverInfo.style.display = 'none'; return false; }

    let closest = 0, minD = Infinity;
    for (let i = 0; i < points.length; i++) {
      if (points[i].dist < distMin || points[i].dist > distMax) continue;
      const d = Math.abs(points[i].dist - dist);
      if (d < minD) { minD = d; closest = i; }
    }

    const p = points[closest];
    document.getElementById('hi-dist').textContent = (p.dist / 1000).toFixed(2) + ' km';
    document.getElementById('hi-ele').textContent = p.eleSmooth.toFixed(1) + 'm';
    const displayGrad = useAbsoluteMode ? Math.abs(p.gradient) : p.gradient;
    const gradPrefix = useAbsoluteMode ? '' : (p.gradient > 0 ? '+' : '');
    const hiAngle = gradToAngle(Math.abs(displayGrad)).toFixed(1);
    document.getElementById('hi-grad').textContent =
      (useAbsoluteMode
        ? displayGrad.toFixed(1) + '% / ' + hiAngle + '\u00b0'
        : gradPrefix + displayGrad.toFixed(1) + '% / ' + hiAngle + '\u00b0');
    hoverInfo.style.display = 'block';

    posMarker.setLatLng([p.lat, p.lon]);
    posMarker.setStyle({ opacity: 1, fillOpacity: 1 });
    return true;
  }

  function hideHover() {
    hoverInfo.style.display = 'none';
    posMarker.setStyle({ opacity: 0, fillOpacity: 0 });
  }

  container.addEventListener('mousemove', (e) => {
    if (isCompatMouse()) return;
    if (dragState) return; // handled by drag handler
    showHoverAt(e.clientX);
  });

  container.addEventListener('mouseleave', () => {
    if (isCompatMouse()) return;
    hideHover();
  });

  // --- Drag-to-select (with click fallback for pan) ---
  let dragState = null;

  function positionOverlayFromPixels(xStart, xEnd) {
    const rect = canvas.getBoundingClientRect();
    const contRect = container.getBoundingClientRect();
    const left = Math.min(xStart, xEnd);
    const width = Math.abs(xEnd - xStart);
    selectionOverlay.style.left = (rect.left - contRect.left + left) + 'px';
    selectionOverlay.style.top = (rect.top - contRect.top) + 'px';
    selectionOverlay.style.width = width + 'px';
    selectionOverlay.style.height = rect.height + 'px';
    selectionOverlay.style.display = 'block';
  }

  function inPlotArea(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    const { padL, padR, padT, padB } = profileParams;
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    return x >= padL && x <= rect.width - padR && y >= padT && y <= rect.height - padB;
  }

  container.addEventListener('mousedown', (e) => {
    if (isCompatMouse()) return;
    if (e.button !== 0) return;
    if (!inPlotArea(e.clientX, e.clientY)) return;
    const rect = canvas.getBoundingClientRect();
    dragState = {
      startClientX: e.clientX,
      startCanvasX: e.clientX - rect.left,
      moved: false,
    };
    e.preventDefault();
  });

  window.addEventListener('mousemove', (e) => {
    if (isCompatMouse()) return;
    if (!dragState) return;
    const rect = canvas.getBoundingClientRect();
    const curCanvasX = Math.max(
      profileParams.padL,
      Math.min(rect.width - profileParams.padR, e.clientX - rect.left)
    );
    const dx = Math.abs(e.clientX - dragState.startClientX);
    if (dx >= DRAG_THRESHOLD_PX) {
      dragState.moved = true;
      hoverInfo.style.display = 'none';
      const startCanvasXClamped = Math.max(
        profileParams.padL,
        Math.min(rect.width - profileParams.padR, dragState.startCanvasX)
      );
      positionOverlayFromPixels(startCanvasXClamped, curCanvasX);
      dragState.endCanvasX = curCanvasX;
    }
  });

  window.addEventListener('mouseup', (e) => {
    if (isCompatMouse()) return;
    if (!dragState) return;
    const wasDrag = dragState.moved;
    const startCanvasX = dragState.startCanvasX;
    const endCanvasX = dragState.endCanvasX != null
      ? dragState.endCanvasX
      : startCanvasX;
    dragState = null;
    selectionOverlay.style.display = 'none';

    if (wasDrag) {
      const rect = canvas.getBoundingClientRect();
      const { padL, plotW, distMin, distSpan } = profileParams;
      const x1 = Math.max(padL, Math.min(rect.width - profileParams.padR, Math.min(startCanvasX, endCanvasX)));
      const x2 = Math.max(padL, Math.min(rect.width - profileParams.padR, Math.max(startCanvasX, endCanvasX)));
      const d1 = distMin + ((x1 - padL) / plotW) * distSpan;
      const d2 = distMin + ((x2 - padL) / plotW) * distSpan;
      setViewRange({ distMin: d1, distMax: d2 });
    } else {
      // Treat as click — pan map to nearest point (existing behavior).
      const dist = distAtClientX(e.clientX);
      let closest = 0, minD = Infinity;
      for (let i = 0; i < points.length; i++) {
        const d = Math.abs(points[i].dist - dist);
        if (d < minD) { minD = d; closest = i; }
      }
      map.panTo([points[closest].lat, points[closest].lon]);
    }
  });

  // --- Touch (Pointer Events): tap pins hover info, one-finger drag selects a zoom range ---
  let touchState = null;

  function commitSelection(startCanvasX, endCanvasX) {
    const rect = canvas.getBoundingClientRect();
    const { padL, plotW, distMin, distSpan } = profileParams;
    const x1 = Math.max(padL, Math.min(rect.width - profileParams.padR, Math.min(startCanvasX, endCanvasX)));
    const x2 = Math.max(padL, Math.min(rect.width - profileParams.padR, Math.max(startCanvasX, endCanvasX)));
    setViewRange({
      distMin: distMin + ((x1 - padL) / plotW) * distSpan,
      distMax: distMin + ((x2 - padL) / plotW) * distSpan,
    });
  }

  function panToNearest(clientX) {
    const dist = distAtClientX(clientX);
    let closest = 0, minD = Infinity;
    for (let i = 0; i < points.length; i++) {
      const d = Math.abs(points[i].dist - dist);
      if (d < minD) { minD = d; closest = i; }
    }
    map.panTo([points[closest].lat, points[closest].lon]);
  }

  const isTouchPointer = (e) => e.pointerType === 'touch' || e.pointerType === 'pen';

  container.addEventListener('pointerdown', (e) => {
    if (!isTouchPointer(e)) return;
    lastTouchTs = performance.now();
    if (e.target === resetBtn) return;
    if (touchState || !e.isPrimary) return;
    if (!inPlotArea(e.clientX, e.clientY)) return;
    const rect = canvas.getBoundingClientRect();
    touchState = {
      id: e.pointerId,
      startClientX: e.clientX,
      startCanvasX: e.clientX - rect.left,
      endCanvasX: null,
      moved: false,
    };
    try { container.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
  });

  container.addEventListener('pointermove', (e) => {
    if (!isTouchPointer(e)) return;
    lastTouchTs = performance.now();
    if (!touchState || e.pointerId !== touchState.id) return;
    const rect = canvas.getBoundingClientRect();
    if (Math.abs(e.clientX - touchState.startClientX) < DRAG_THRESHOLD_PX && !touchState.moved) return;
    touchState.moved = true;
    hoverInfo.style.display = 'none';
    const clamp = (x) => Math.max(profileParams.padL, Math.min(rect.width - profileParams.padR, x));
    touchState.endCanvasX = clamp(e.clientX - rect.left);
    positionOverlayFromPixels(clamp(touchState.startCanvasX), touchState.endCanvasX);
  });

  function endTouch(e, cancelled) {
    if (!isTouchPointer(e)) return;
    lastTouchTs = performance.now();
    if (!touchState || e.pointerId !== touchState.id) return;
    const st = touchState;
    touchState = null;
    selectionOverlay.style.display = 'none';
    try { container.releasePointerCapture(e.pointerId); } catch (_) { /* ignore */ }
    if (cancelled) return;
    if (st.moved) {
      commitSelection(st.startCanvasX, st.endCanvasX != null ? st.endCanvasX : st.startCanvasX);
    } else if (showHoverAt(e.clientX)) {
      panToNearest(e.clientX);
    }
  }
  container.addEventListener('pointerup', (e) => endTouch(e, false));
  container.addEventListener('pointercancel', (e) => endTouch(e, true));

  // A touch outside the profile dismisses the pinned hover info.
  document.addEventListener('pointerdown', (e) => {
    if (!isTouchPointer(e)) return;
    if (container.contains(e.target)) return;
    hideHover();
  }, true);

  // Cancel drag on Escape.
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      if (dragState) {
        dragState = null;
        selectionOverlay.style.display = 'none';
      } else if (viewRange.distMin > 0 || viewRange.distMax < totalDist) {
        clearViewRange();
      }
    }
  });

  return {
    drawProfile: () => { profileParams = drawProfile(); },
    setViewRange,
    clearViewRange,
    isZoomed: () => viewRange.distMin > 0 || viewRange.distMax < totalDist,
  };
}
