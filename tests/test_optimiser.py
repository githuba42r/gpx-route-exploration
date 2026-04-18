"""Tests for the pure-Python optimiser (M3b).

The optimiser is stateless and consumes plain dicts — no Flask, no DB.
Inputs are a list of waypoint dicts (the schema shape) and an optional
cost matrix; outputs are a list of waypoint ids in the optimised order.
Grouping: every stop starts a new group, followed by any consecutive
waypoints with linked_to_previous=1. 2-opt swaps groups wholesale,
never reaching inside one.
"""

import pytest

from server.routing import optimiser


def _wp(wid, pos, kind, lat, lon, **extra):
    """Waypoint dict in the shape models/waypoints.py returns."""
    return {
        "id": wid, "position": pos, "kind": kind,
        "name": f"W{wid}", "lat": lat, "lon": lon,
        "included": 1, "pin_role": extra.get("pin_role"),
        "linked_to_previous": extra.get("linked_to_previous", 1),
    }


def test_optimise_4_point_symmetric_square():
    wps = [
        _wp(1, 0, "stop", 0, 0),
        _wp(2, 1, "stop", 0, 1),
        _wp(3, 2, "stop", 1, 1),
        _wp(4, 3, "stop", 1, 0),
    ]
    wps_bad = [wps[0], wps[2], wps[1], wps[3]]
    new_order = optimiser.optimise(wps_bad)
    cost = _tour_cost(new_order, wps_bad)
    assert cost == pytest.approx(3.0, abs=1e-6)


def test_optimise_2opt_reduces_cost():
    wps = [
        _wp(1, 0, "stop",  0.0, 0.0),
        _wp(2, 1, "stop",  0.0, 3.0),
        _wp(3, 2, "stop",  4.0, 3.0),
        _wp(4, 3, "stop",  4.0, 0.0),
        _wp(5, 4, "stop",  2.0, 1.5),
    ]
    wps_seed = [wps[0], wps[2], wps[4], wps[1], wps[3]]
    initial = _tour_cost([w["id"] for w in wps_seed], wps_seed)
    new_order = optimiser.optimise(wps_seed)
    improved = _tour_cost(new_order, wps_seed)
    assert improved < initial, f"2-opt did not reduce cost: {initial} → {improved}"


def test_optimise_respects_pinned_start():
    wps = [
        _wp(1, 0, "stop", 0, 0),
        _wp(2, 1, "stop", 0, 10),
        _wp(3, 2, "stop", 10, 0, pin_role="start"),
    ]
    new_order = optimiser.optimise(wps)
    assert new_order[0] == 3


def test_optimise_respects_pinned_end():
    wps = [
        _wp(1, 0, "stop", 0, 0),
        _wp(2, 1, "stop", 0, 10, pin_role="end"),
        _wp(3, 2, "stop", 10, 0),
    ]
    new_order = optimiser.optimise(wps)
    assert new_order[-1] == 2


def test_optimise_keeps_linked_waypoint_with_its_stop():
    """Stop A → linked WP W → Stop B → Stop C. The optimiser would move
    B before A (shorter), but W must ride with A. So the result must
    have W immediately after A wherever A ends up."""
    wps = [
        _wp(1, 0, "stop",     0, 0, pin_role="start"),
        _wp(2, 1, "waypoint", 0.1, 0.1, linked_to_previous=1),
        _wp(3, 2, "stop",    10, 10),
        _wp(4, 3, "stop",     5, 5),
    ]
    new_order = optimiser.optimise(wps)
    a_idx = new_order.index(1)
    assert new_order[a_idx + 1] == 2


def test_unlinked_waypoint_is_free_to_reorder():
    """Same topology but W has linked_to_previous=0 — optimiser may place W anywhere."""
    wps = [
        _wp(1, 0, "stop",     0, 0, pin_role="start"),
        _wp(2, 1, "waypoint", 0.1, 0.1, linked_to_previous=0),
        _wp(3, 2, "stop",    10, 10),
        _wp(4, 3, "stop",     5, 5),
    ]
    new_order = optimiser.optimise(wps)
    assert set(new_order) == {1, 2, 3, 4}
    assert new_order[0] == 1


def test_cost_matrix_accepted_without_error():
    wps = [
        _wp(1, 0, "stop", 0, 0),
        _wp(2, 1, "stop", 0, 1),
    ]
    cost_matrix = {(1, 2): 1000.0, (2, 1): 1000.0}
    new_order = optimiser.optimise(wps, cost_matrix=cost_matrix)
    assert set(new_order) == {1, 2}


def test_optimise_prefers_cheaper_leg_when_available():
    """4 collinear points; override (1,3) with near-zero cost so the
    optimiser prefers 1→3 second."""
    wps = [
        _wp(1, 0, "stop", 0, 0),
        _wp(2, 1, "stop", 0, 1),
        _wp(3, 2, "stop", 0, 2),
        _wp(4, 3, "stop", 0, 3),
    ]
    cost_matrix = {
        (1, 2): 1000.0, (2, 1): 1000.0,
        (1, 3): 1.0,    (3, 1): 1.0,
        (1, 4): 1000.0, (4, 1): 1000.0,
        (2, 3): 1000.0, (3, 2): 1000.0,
        (2, 4): 1000.0, (4, 2): 1000.0,
        (3, 4): 1.0,    (4, 3): 1.0,
    }
    new_order = optimiser.optimise(wps, cost_matrix=cost_matrix)
    # Pin on the first waypoint is implicit (group 0 is start by default),
    # so the tour starts at 1; cheapest continuation is 1→3.
    assert new_order[:2] == [1, 3]


def test_optimise_skips_excluded_waypoints():
    """Excluded rows aren't in the returned order (the caller keeps them
    in the recipe at their current position)."""
    wps = [
        _wp(1, 0, "stop", 0, 0),
        _wp(2, 1, "stop", 0, 1),
        _wp(3, 2, "stop", 1, 1),
    ]
    wps[1]["included"] = 0
    new_order = optimiser.optimise(wps)
    assert 2 not in new_order
    assert set(new_order) == {1, 3}


def test_optimise_empty_input():
    assert optimiser.optimise([]) == []


def test_optimise_single_waypoint():
    wps = [_wp(1, 0, "stop", 0, 0)]
    assert optimiser.optimise(wps) == [1]


def _tour_cost(order_or_ids, wps):
    if order_or_ids and isinstance(order_or_ids[0], dict):
        ids = [w["id"] for w in order_or_ids]
    else:
        ids = list(order_or_ids)
    by_id = {w["id"]: w for w in wps}
    total = 0.0
    for a, b in zip(ids, ids[1:]):
        total += _hav(by_id[a], by_id[b])
    return total


def _hav(a, b):
    from math import radians, sin, cos, atan2, sqrt
    R = 6371000
    lat1, lon1 = radians(a["lat"]), radians(a["lon"])
    lat2, lon2 = radians(b["lat"]), radians(b["lon"])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    x = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(x), sqrt(1 - x))
