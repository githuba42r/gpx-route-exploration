"""CRUD helpers for route_waypoints, route_options, route_legs."""

from server.models import get_db


# ---------- route_waypoints ----------

def _row_to_dict(row):
    return dict(row) if row else None


def list_waypoints(route_id):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM route_waypoints WHERE route_id = ? ORDER BY position",
        (route_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_waypoint(waypoint_id, route_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM route_waypoints WHERE id = ? AND route_id = ?",
        (waypoint_id, route_id),
    ).fetchone()
    return _row_to_dict(row)


def append_waypoint(route_id, *, name, lat, lon, kind,
                    address=None, description=None,
                    included=1, pin_role=None, dwell_minutes=0):
    db = get_db()
    next_pos_row = db.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 AS p FROM route_waypoints WHERE route_id = ?",
        (route_id,),
    ).fetchone()
    position = next_pos_row["p"]
    cur = db.execute(
        """
        INSERT INTO route_waypoints (
            route_id, position, kind, name, address, lat, lon,
            included, pin_role, dwell_minutes, description
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (route_id, position, kind, name, address, lat, lon,
         included, pin_role, dwell_minutes, description),
    )
    db.commit()
    return get_waypoint(cur.lastrowid, route_id)


def update_waypoint(waypoint_id, route_id, **fields):
    """Update any subset of: name, address, kind, lat, lon, included,
    pin_role, dwell_minutes, description. Position is handled separately
    via reorder_waypoints."""
    allowed = {"name", "address", "kind", "lat", "lon",
               "included", "pin_role", "dwell_minutes", "description"}
    # Fields in NULLABLE may be set to NULL explicitly (e.g. clearing pin_role).
    NULLABLE = {"pin_role", "address", "description"}
    updates = {k: v for k, v in fields.items()
               if k in allowed and (v is not None or k in NULLABLE)}
    if not updates:
        return get_waypoint(waypoint_id, route_id)
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [waypoint_id, route_id]
    db = get_db()
    db.execute(
        f"UPDATE route_waypoints SET {set_clause} WHERE id = ? AND route_id = ?",
        params,
    )
    db.commit()
    return get_waypoint(waypoint_id, route_id)


def delete_waypoint(waypoint_id, route_id):
    db = get_db()
    deleted = db.execute(
        "DELETE FROM route_waypoints WHERE id = ? AND route_id = ?",
        (waypoint_id, route_id),
    ).rowcount
    if not deleted:
        db.commit()
        return False
    # Re-pack positions 0..N-1
    rows = db.execute(
        "SELECT id FROM route_waypoints WHERE route_id = ? ORDER BY position",
        (route_id,),
    ).fetchall()
    for new_pos, row in enumerate(rows):
        db.execute(
            "UPDATE route_waypoints SET position = ? WHERE id = ?",
            (new_pos, row["id"]),
        )
    db.commit()
    return True


def reorder_waypoints(route_id, ordered_ids):
    """Replace the full position ordering. `ordered_ids` must contain
    every waypoint id in the route, in the desired order. Uses a
    two-phase update (stage negative, then final) to avoid tripping the
    UNIQUE(route_id, position) constraint."""
    db = get_db()
    existing = [r["id"] for r in db.execute(
        "SELECT id FROM route_waypoints WHERE route_id = ?", (route_id,),
    ).fetchall()]
    if set(existing) != set(ordered_ids):
        raise ValueError("ordered_ids must contain exactly the route's waypoint ids")
    # Phase 1: move all to negative positions
    for i, wid in enumerate(ordered_ids):
        db.execute(
            "UPDATE route_waypoints SET position = ? WHERE id = ? AND route_id = ?",
            (-(i + 1), wid, route_id),
        )
    # Phase 2: set final positions
    for i, wid in enumerate(ordered_ids):
        db.execute(
            "UPDATE route_waypoints SET position = ? WHERE id = ? AND route_id = ?",
            (i, wid, route_id),
        )
    db.commit()


# ---------- route_options ----------

def get_or_create_options(route_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM route_options WHERE route_id = ?", (route_id,),
    ).fetchone()
    if row is None:
        db.execute("INSERT INTO route_options (route_id) VALUES (?)", (route_id,))
        db.commit()
        row = db.execute(
            "SELECT * FROM route_options WHERE route_id = ?", (route_id,),
        ).fetchone()
    return dict(row)


def update_options(route_id, **fields):
    allowed = {"profile", "costing_preset", "costing_options",
               "round_trip", "max_gradient_warn",
               "last_optimised_at", "last_generated_at"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_or_create_options(route_id)
    # Ensure a row exists first.
    get_or_create_options(route_id)
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [route_id]
    db = get_db()
    db.execute(
        f"UPDATE route_options SET {set_clause} WHERE route_id = ?",
        params,
    )
    db.commit()
    return get_or_create_options(route_id)


# ---------- route_legs ----------

def replace_legs(route_id, legs):
    """Delete all existing legs for the route and insert the new set.
    `legs` is a list of dicts with keys:
      from_position, to_position, distance_m, duration_s, polyline,
      max_grade_pct (optional), warnings (optional — JSON string)."""
    db = get_db()
    db.execute("DELETE FROM route_legs WHERE route_id = ?", (route_id,))
    for leg in legs:
        db.execute(
            """
            INSERT INTO route_legs (
                route_id, from_position, to_position,
                distance_m, duration_s, polyline,
                max_grade_pct, warnings
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                route_id,
                leg["from_position"], leg["to_position"],
                leg["distance_m"], leg["duration_s"], leg["polyline"],
                leg.get("max_grade_pct"),
                leg.get("warnings"),
            ),
        )
    db.commit()


def list_legs(route_id):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM route_legs WHERE route_id = ? ORDER BY from_position",
        (route_id,),
    ).fetchall()
    return [dict(r) for r in rows]
