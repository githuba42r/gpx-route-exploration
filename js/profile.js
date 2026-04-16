// --- Elevation profile canvas drawing and interaction ---

function initProfile(points, stats, mapObj) {
  const { minEle, maxEle } = stats;
  const { map, posMarker } = mapObj;

  const canvas = document.getElementById('profile-canvas');
  const ctx = canvas.getContext('2d');
  const hoverInfo = document.getElementById('hover-info');

  // rangeVisible is accessed from the global scope (set in app.js)

  function drawProfile() {
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const W = rect.width;
    const H = rect.height;
    const padL = 50, padR = 16, padT = 16, padB = 30;
    const plotW = W - padL - padR;
    const plotH = H - padT - padB;

    const maxDist = points[points.length - 1].dist;
    const eleMin = minEle - 10;
    const eleMax = maxEle + 20;
    const eleRange = eleMax - eleMin;

    function xFor(dist) { return padL + (dist / maxDist) * plotW; }
    function yFor(ele) { return padT + plotH - ((ele - eleMin) / eleRange) * plotH; }

    // Background
    ctx.fillStyle = '#16213e';
    ctx.fillRect(0, 0, W, H);

    // Grid lines
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

    const distStep = maxDist > 40000 ? 10000 : maxDist > 20000 ? 5000 : 2000;
    for (let d = 0; d <= maxDist; d += distStep) {
      const x = xFor(d);
      ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, padT + plotH); ctx.stroke();
      ctx.fillStyle = '#6a7a9a';
      ctx.font = '10px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(`${(d/1000).toFixed(0)} km`, x, H - padB + 14);
    }

    // Filled profile with gradient coloring (respects visibility toggle)
    for (let i = 1; i < points.length; i++) {
      const x1 = xFor(points[i-1].dist);
      const x2 = xFor(points[i].dist);
      const y1 = yFor(points[i-1].eleSmooth);
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

    return { W, H, padL, padR, padT, padB, plotW, plotH, maxDist, eleMin, eleRange, xFor, yFor };
  }

  let profileParams = drawProfile();
  window.addEventListener('resize', () => { profileParams = drawProfile(); });

  // Return drawProfile so applyVisibility can call it
  const profileApi = { drawProfile: () => { profileParams = drawProfile(); } };

  // Hover interaction
  const profileContainer = document.getElementById('profile-container');
  profileContainer.addEventListener('mousemove', (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const { padL, plotW, maxDist } = profileParams;

    const dist = ((mx - padL) / plotW) * maxDist;
    if (dist < 0 || dist > maxDist) { hoverInfo.style.display = 'none'; return; }

    let closest = 0;
    let minD = Infinity;
    for (let i = 0; i < points.length; i++) {
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
  });

  profileContainer.addEventListener('mouseleave', () => {
    hoverInfo.style.display = 'none';
    posMarker.setStyle({ opacity: 0, fillOpacity: 0 });
  });

  profileContainer.addEventListener('click', (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const { padL, plotW, maxDist } = profileParams;
    const dist = ((mx - padL) / plotW) * maxDist;

    let closest = 0, minD = Infinity;
    for (let i = 0; i < points.length; i++) {
      const d = Math.abs(points[i].dist - dist);
      if (d < minD) { minD = d; closest = i; }
    }
    map.panTo([points[closest].lat, points[closest].lon]);
  });

  return profileApi;
}
