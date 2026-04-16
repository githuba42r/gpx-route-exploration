from server.models import get_db
from server.models.categories import get_category


def create_route(
    user_id,
    category_id,
    filename,
    storage_name,
    title,
    distance_km=None,
    min_elevation=None,
    max_elevation=None,
    max_gradient_asc=None,
    max_gradient_desc=None,
    point_count=None,
    description="",
    notes="",
):
    db = get_db()
    db.execute(
        """
        INSERT INTO routes (
            user_id, category_id, filename, storage_name, title,
            distance_km, min_elevation, max_elevation,
            max_gradient_asc, max_gradient_desc, point_count,
            description, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id, category_id, filename, storage_name, title,
            distance_km, min_elevation, max_elevation,
            max_gradient_asc, max_gradient_desc, point_count,
            description, notes,
        ),
    )
    db.commit()
    row = db.execute(
        "SELECT * FROM routes WHERE user_id = ? AND storage_name = ?",
        (user_id, storage_name),
    ).fetchone()
    return dict(row)


def get_routes(user_id, category_id=None):
    db = get_db()
    if category_id is not None:
        rows = db.execute(
            "SELECT * FROM routes WHERE user_id = ? AND category_id = ? ORDER BY created_at DESC",
            (user_id, category_id),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM routes WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_route(user_id, route_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM routes WHERE user_id = ? AND id = ?",
        (user_id, route_id),
    ).fetchone()
    return dict(row) if row else None


def update_route(user_id, route_id, title=None, description=None, notes=None):
    db = get_db()
    if title is not None:
        db.execute(
            "UPDATE routes SET title = ? WHERE user_id = ? AND id = ?",
            (title, user_id, route_id),
        )
    if description is not None:
        db.execute(
            "UPDATE routes SET description = ? WHERE user_id = ? AND id = ?",
            (description, user_id, route_id),
        )
    if notes is not None:
        db.execute(
            "UPDATE routes SET notes = ? WHERE user_id = ? AND id = ?",
            (notes, user_id, route_id),
        )
    db.commit()
    return get_route(user_id, route_id)


def touch_last_accessed(user_id, route_id):
    db = get_db()
    db.execute(
        "UPDATE routes SET last_accessed = CURRENT_TIMESTAMP WHERE user_id = ? AND id = ?",
        (user_id, route_id),
    )
    db.commit()


def delete_route(user_id, route_id):
    route = get_route(user_id, route_id)
    if route is None:
        return None
    db = get_db()
    db.execute("DELETE FROM routes WHERE user_id = ? AND id = ?", (user_id, route_id))
    db.commit()
    return route


def move_route(user_id, route_id, new_category_id):
    target = get_category(user_id, new_category_id)
    if target is None:
        raise ValueError("Target category not found or does not belong to user")
    db = get_db()
    db.execute(
        "UPDATE routes SET category_id = ? WHERE user_id = ? AND id = ?",
        (new_category_id, user_id, route_id),
    )
    db.commit()
    return get_route(user_id, route_id)
