"""Pure-Python route optimiser: nearest-neighbour + 2-opt over groups.

Groups
------
Every stop (kind='stop') starts a new group. Any subsequent waypoint
(kind='waypoint') with linked_to_previous=1 joins the current group.
An unlinked waypoint (linked_to_previous=0) starts its own group —
this is the "free-floating shape waypoint" case that the user gets by
right-click → Unlink from previous.

The optimiser reorders groups, never the interiors. Pinned-start /
pinned-end groups are held in place.

Cost
----
A distance between two groups is the cost from the last point of the
source group to the first point of the destination group. If a
`cost_matrix` is provided (keyed by `(from_waypoint_id, to_waypoint_id)`)
it overrides the haversine fallback. Cached `route_legs` is the
source of the matrix in the production endpoint; tests feed synthetic
matrices.
"""

from math import atan2, cos, radians, sin, sqrt


def _haversine(a_lat, a_lon, b_lat, b_lon):
    R = 6371000
    lat1, lon1 = radians(a_lat), radians(a_lon)
    lat2, lon2 = radians(b_lat), radians(b_lon)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    x = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(x), sqrt(1 - x))


def _cost(a, b, cost_matrix):
    if cost_matrix is not None:
        cached = cost_matrix.get((a["id"], b["id"]))
        if cached is not None:
            return cached
    return _haversine(a["lat"], a["lon"], b["lat"], b["lon"])


def build_groups(waypoints):
    """Chunk a waypoint list into groups.

    Rules:
      - The first waypoint always starts a group.
      - Every stop starts a new group.
      - A waypoint with linked_to_previous=0 starts a new group.
      - A waypoint with linked_to_previous=1 joins the current group.
    """
    groups = []
    current = []
    for w in waypoints:
        if not current:
            current = [w]
            continue
        if w["kind"] == "stop" or int(w.get("linked_to_previous", 1)) == 0:
            groups.append(current)
            current = [w]
        else:
            current.append(w)
    if current:
        groups.append(current)
    return groups


def _group_cost(group_a, group_b, cost_matrix):
    """Last-of-A → first-of-B. Intra-group costs are fixed and ignored."""
    return _cost(group_a[-1], group_b[0], cost_matrix)


def _pin_constraints(groups):
    """Return (start_idx, end_idx) — indices of the groups holding a
    pin_role='start' / 'end' waypoint, or None if absent."""
    start_idx = end_idx = None
    for i, g in enumerate(groups):
        for w in g:
            if w.get("pin_role") == "start":
                start_idx = i
            elif w.get("pin_role") == "end":
                end_idx = i
    return start_idx, end_idx


def _nearest_neighbour(groups, cost_matrix, start_idx):
    """Seed tour: greedy NN forced to begin at start_idx."""
    unvisited = list(range(len(groups)))
    order = [start_idx]
    unvisited.remove(start_idx)
    while unvisited:
        last = order[-1]
        best = min(
            unvisited,
            key=lambda j: _group_cost(groups[last], groups[j], cost_matrix),
        )
        order.append(best)
        unvisited.remove(best)
    return order


def _tour_cost(order, groups, cost_matrix):
    total = 0.0
    for i in range(len(order) - 1):
        total += _group_cost(groups[order[i]], groups[order[i + 1]], cost_matrix)
    return total


def _two_opt(order, groups, cost_matrix, *, fixed_first=True, fixed_last=False):
    """Standard 2-opt. Skips index 0 when start is pinned; skips the last
    index when end is pinned. Restarts on any improvement (classic impl)."""
    n = len(order)
    improved = True
    while improved:
        improved = False
        i_start = 1 if fixed_first else 0
        i_end = n - 2 if fixed_last else n - 1
        for i in range(i_start, i_end):
            j_end = n - 1 if fixed_last else n
            for j in range(i + 1, j_end):
                if j - i == 1:
                    continue
                new_order = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                if _tour_cost(new_order, groups, cost_matrix) + 1e-9 < \
                   _tour_cost(order, groups, cost_matrix):
                    order = new_order
                    improved = True
    return order


def optimise(waypoints, cost_matrix=None):
    """Return the optimised ordering as a flat list of waypoint ids.

    waypoints: list of waypoint dicts in the current recipe order.
    cost_matrix: optional {(from_id, to_id): metres}.
    """
    if not waypoints:
        return []
    included = [w for w in waypoints if w.get("included", 1)]
    if len(included) <= 1:
        return [w["id"] for w in included]

    groups = build_groups(included)
    start_idx, end_idx = _pin_constraints(groups)
    if start_idx is None:
        start_idx = 0

    order = _nearest_neighbour(groups, cost_matrix, start_idx)

    # Force the pinned end to the tail before 2-opt so local search
    # doesn't bounce it out of place.
    if end_idx is not None:
        order.remove(end_idx)
        order.append(end_idx)

    order = _two_opt(
        order, groups, cost_matrix,
        fixed_first=True,
        fixed_last=end_idx is not None,
    )

    out = []
    for gi in order:
        for w in groups[gi]:
            out.append(w["id"])
    return out
