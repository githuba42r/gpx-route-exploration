"""Tests for server/route_postprocess.py — gradient-warning post-processor (M3c)."""

import json
import math

import pytest

from server.route_postprocess import (
    _max_grade_for_leg,
    _smooth,
    _warnings_for_leg,
    _windowed_gradient,
    scan_legs_for_warnings,
)


def test_smooth_flat_is_idempotent():
    flat = [100.0] * 20
    assert _smooth(flat, window=7) == pytest.approx(flat)


def test_smooth_spike_is_dampened():
    series = [100.0] * 10
    series[5] = 200.0
    smoothed = _smooth(series, window=7)
    assert smoothed[5] < 200.0
    assert smoothed[5] > 100.0


def test_windowed_gradient_constant_slope():
    """20 samples at 10 m spacing rising 1 m per sample = 10% grade.
    The first index is zero-initialised; mid-series samples settle to 10%."""
    distances_m = [i * 10.0 for i in range(20)]
    elevations = [i * 1.0 for i in range(20)]
    grads = _windowed_gradient(distances_m, elevations, gradient_dist=50.0)
    assert grads[15] == pytest.approx(10.0, abs=0.01)


def test_warnings_empty_when_below_threshold():
    ele = [i * 0.3 for i in range(20)]
    dist = [i * 10.0 for i in range(20)]
    w = _warnings_for_leg(dist, ele, max_gradient_warn=10.0)
    assert w == []


def test_warnings_picks_up_steep_run():
    """Flat start, then a steep 20%-grade climb. The post-processor must
    identify one warning spanning roughly the climb's extent."""
    # 40 samples: first 10 flat, then a sustained 20% grade for 30 samples.
    dist = [i * 10.0 for i in range(40)]
    ele = [50.0] * 10 + [50.0 + i * 2.0 for i in range(1, 31)]
    w = _warnings_for_leg(dist, ele, max_gradient_warn=10.0)
    assert len(w) >= 1
    # Peak gradient smooths to ~20%.
    assert w[0]["peak_grad_pct"] > 15.0
    # Warning starts somewhere in the climbing section (metre 100ish) and
    # extends into the tail.
    assert w[0]["from_m"] >= 80.0
    assert w[0]["to_m"] > w[0]["from_m"] + 50.0


def test_warnings_captures_sign_via_abs_on_descent():
    """A steep descent triggers a warning too — threshold is on |gradient|."""
    dist = [i * 10.0 for i in range(40)]
    # 10 flat, then 30 samples dropping 2m each = -20% grade.
    ele = [100.0] * 10 + [100.0 - i * 2.0 for i in range(1, 31)]
    w = _warnings_for_leg(dist, ele, max_gradient_warn=10.0)
    assert len(w) >= 1
    assert w[0]["peak_grad_pct"] > 15.0


def test_scan_legs_for_warnings_none_when_threshold_null():
    legs = [{
        "distance_m": 1000.0,
        "elevation": [i * 0.1 for i in range(100)],
        "elevation_interval_m": 10.0,
    }]
    result = scan_legs_for_warnings(legs, max_gradient_warn=None)
    assert len(result) == 1
    # max_grade_pct is still computed from the elevation data; warnings
    # is None because the threshold is unset.
    assert result[0]["warnings"] is None
    # ~1% grade; max_grade_pct is derived from the data regardless.
    assert result[0]["max_grade_pct"] is not None


def test_scan_legs_for_warnings_empty_elevation_returns_nulls():
    legs = [{"distance_m": 100.0, "elevation": [], "elevation_interval_m": 10.0}]
    result = scan_legs_for_warnings(legs, max_gradient_warn=10.0)
    assert result == [{"max_grade_pct": None, "warnings": None}]


def test_scan_legs_for_warnings_output_is_json_serialisable():
    """Output must survive json.dumps so it can be persisted into
    route_legs.warnings as a TEXT column."""
    legs = [{
        "distance_m": 1500.0,
        "elevation": [10 * math.pow(1.02, i) for i in range(100)],
        "elevation_interval_m": 15.0,
    }]
    result = scan_legs_for_warnings(legs, max_gradient_warn=1.0)
    for row in result:
        if row["warnings"] is not None:
            # Should not raise.
            json.dumps(row["warnings"])


def test_max_grade_for_leg_preserves_sign():
    """The signed peak gradient retains direction of steepest segment."""
    dist = [i * 10.0 for i in range(20)]
    ele_up = [i * 1.5 for i in range(20)]
    ele_down = [100.0 - i * 1.5 for i in range(20)]
    assert _max_grade_for_leg(dist, ele_up) > 0
    assert _max_grade_for_leg(dist, ele_down) < 0


def test_max_grade_for_leg_short_series_returns_zero():
    assert _max_grade_for_leg([0.0], [10.0]) == 0.0
