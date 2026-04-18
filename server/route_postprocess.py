"""Post-process Valhalla response legs: smooth elevations, compute
windowed gradient, emit warning ranges for sub-segments exceeding the
user-configured threshold.

Ported from src/js/analysis/track-processor.js (see plan Decision D3):
server-side is the right home because the warnings persist into
route_legs.warnings before the /generate response ships, and the
analysis page reads them as an input rather than recomputing.
"""

# Smoothing and windowed-gradient params match the frontend defaults.
# Frontend persists these in localStorage per-user; the server uses the
# app-level defaults since the DB doesn't carry per-user analysis prefs.
SMOOTH_WINDOW = 7
GRADIENT_DIST = 100.0   # minimum window (metres) over which gradient is measured


def _smooth(elevations, window):
    """Centred moving average. Matches track-processor.js::smoothElevations."""
    n = len(elevations)
    half = window // 2
    out = []
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n - 1, i + half)
        s = 0.0
        c = 0
        for j in range(lo, hi + 1):
            s += elevations[j]
            c += 1
        out.append(s / c)
    return out


def _windowed_gradient(distances_m, elevations_smoothed, gradient_dist=GRADIENT_DIST):
    """Gradient per-sample over the minimum `gradient_dist` window.

    For each index i, walk back until the window spans at least
    `gradient_dist` metres, then `grad = (ele_i - ele_j) / (dist_i - dist_j) * 100`.
    Mirrors track-processor.js::processTrackData's gradient loop.
    """
    n = len(distances_m)
    grads = [0.0] * n
    for i in range(1, n):
        j = i - 1
        while j > 0 and (distances_m[i] - distances_m[j]) < gradient_dist:
            j -= 1
        d = distances_m[i] - distances_m[j]
        if d > 1.0:
            grads[i] = ((elevations_smoothed[i] - elevations_smoothed[j]) / d) * 100.0
        else:
            grads[i] = 0.0
    return grads


def _warnings_for_leg(distances_m, elevations, max_gradient_warn):
    """Find sub-segments where |smoothed gradient| >= `max_gradient_warn`.

    Returns a list of {from_m, to_m, peak_grad_pct} dicts — JSON-safe so
    the caller can persist directly to route_legs.warnings.
    """
    if max_gradient_warn is None:
        return []
    smoothed = _smooth(elevations, SMOOTH_WINDOW)
    grads = _windowed_gradient(distances_m, smoothed)
    warnings = []
    in_run = False
    run_start_m = None
    run_peak = 0.0
    for i, g in enumerate(grads):
        over = abs(g) >= max_gradient_warn
        if over and not in_run:
            in_run = True
            run_start_m = distances_m[i]
            run_peak = abs(g)
        elif over:
            if abs(g) > run_peak:
                run_peak = abs(g)
        elif in_run:
            warnings.append({
                "from_m": round(run_start_m, 2),
                "to_m": round(distances_m[i], 2),
                "peak_grad_pct": round(run_peak, 2),
            })
            in_run = False
    if in_run:
        warnings.append({
            "from_m": round(run_start_m, 2),
            "to_m": round(distances_m[-1], 2),
            "peak_grad_pct": round(run_peak, 2),
        })
    return warnings


def _max_grade_for_leg(distances_m, elevations):
    """Peak smoothed gradient across the leg, with sign preserved."""
    if len(distances_m) < 2:
        return 0.0
    smoothed = _smooth(elevations, SMOOTH_WINDOW)
    grads = _windowed_gradient(distances_m, smoothed)
    peak = 0.0
    for g in grads:
        if abs(g) > abs(peak):
            peak = g
    return peak


def scan_legs_for_warnings(legs, max_gradient_warn):
    """Given Valhalla-parsed legs (with elevation samples), return a list
    parallel to `legs` of {max_grade_pct, warnings} dicts.

    Each input leg is a dict with:
      - elevation: list[float] of metre samples
      - elevation_interval_m: float — spacing between samples
      - distance_m: float (not read — sanity only)

    Empty / missing elevation yields {max_grade_pct: None, warnings: None}.
    """
    out = []
    for leg in legs:
        ele = leg.get("elevation") or []
        step = leg.get("elevation_interval_m") or 10.0
        if not ele:
            out.append({"max_grade_pct": None, "warnings": None})
            continue
        distances = [i * step for i in range(len(ele))]
        peak = _max_grade_for_leg(distances, ele)
        warnings = _warnings_for_leg(distances, ele, max_gradient_warn)
        out.append({
            "max_grade_pct": round(peak, 2),
            "warnings": warnings if warnings else None,
        })
    return out
