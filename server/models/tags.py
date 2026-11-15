from server.models import get_db


def _get_or_create_tag(user_id, name):
    db = get_db()
    name_lower = name.lower()
    row = db.execute(
        "SELECT * FROM tags WHERE user_id = ? AND name_lower = ?",
        (user_id, name_lower),
    ).fetchone()
    if row:
        return dict(row)
    db.execute(
        "INSERT INTO tags (user_id, name, name_lower) VALUES (?, ?, ?)",
        (user_id, name, name_lower),
    )
    db.commit()
    row = db.execute(
        "SELECT * FROM tags WHERE user_id = ? AND name_lower = ?",
        (user_id, name_lower),
    ).fetchone()
    return dict(row)


def set_route_tags(user_id, route_id, tag_names):
    db = get_db()
    db.execute("DELETE FROM route_tags WHERE route_id = ?", (route_id,))
    seen = set()
    for name in tag_names:
        name_lower = name.lower()
        if name_lower in seen:
            continue
        seen.add(name_lower)
        tag = _get_or_create_tag(user_id, name)
        db.execute(
            "INSERT OR IGNORE INTO route_tags (route_id, tag_id) VALUES (?, ?)",
            (route_id, tag["id"]),
        )
    db.commit()


def set_category_tags(user_id, category_id, tag_names):
    db = get_db()
    db.execute("DELETE FROM category_tags WHERE category_id = ?", (category_id,))
    seen = set()
    for name in tag_names:
        name_lower = name.lower()
        if name_lower in seen:
            continue
        seen.add(name_lower)
        tag = _get_or_create_tag(user_id, name)
        db.execute(
            "INSERT OR IGNORE INTO category_tags (category_id, tag_id) VALUES (?, ?)",
            (category_id, tag["id"]),
        )
    db.commit()


def set_bookmark_tags(user_id, bookmark_id, tag_names):
    db = get_db()
    owned = db.execute(
        "SELECT 1 FROM bookmarks WHERE id = ? AND user_id = ?", (bookmark_id, user_id)
    ).fetchone()
    if not owned:
        return
    db.execute("DELETE FROM bookmark_tags WHERE bookmark_id = ?", (bookmark_id,))
    seen = set()
    for name in tag_names:
        name_lower = name.lower()
        if name_lower in seen:
            continue
        seen.add(name_lower)
        tag = _get_or_create_tag(user_id, name)
        db.execute(
            "INSERT OR IGNORE INTO bookmark_tags (bookmark_id, tag_id) VALUES (?, ?)",
            (bookmark_id, tag["id"]),
        )
    db.execute(
        "UPDATE bookmarks SET updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
        (bookmark_id, user_id),
    )
    db.commit()


def get_tags_with_counts(user_id):
    db = get_db()
    rows = db.execute(
        """
        SELECT t.id, t.name, t.name_lower,
               (
                   SELECT COUNT(*) FROM route_tags rt
                   JOIN routes r ON r.id = rt.route_id
                   WHERE rt.tag_id = t.id AND r.user_id = t.user_id
               ) +
               (
                   SELECT COUNT(*) FROM category_tags ct
                   JOIN categories c ON c.id = ct.category_id
                   WHERE ct.tag_id = t.id AND c.user_id = t.user_id
               ) +
               (
                   SELECT COUNT(*) FROM bookmark_tags bt
                   JOIN bookmarks b ON b.id = bt.bookmark_id
                   WHERE bt.tag_id = t.id AND b.user_id = t.user_id
               ) AS usage_count
        FROM tags t
        WHERE t.user_id = ?
        ORDER BY t.name_lower
        """,
        (user_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_route_tags(user_id, route_id):
    db = get_db()
    rows = db.execute(
        """
        SELECT t.* FROM tags t
        JOIN route_tags rt ON rt.tag_id = t.id
        JOIN routes r ON r.id = rt.route_id
        WHERE rt.route_id = ? AND r.user_id = ?
        ORDER BY t.name_lower
        """,
        (route_id, user_id),
    ).fetchall()
    return [dict(row) for row in rows]


def get_category_tags(user_id, category_id):
    db = get_db()
    rows = db.execute(
        """
        SELECT t.* FROM tags t
        JOIN category_tags ct ON ct.tag_id = t.id
        JOIN categories c ON c.id = ct.category_id
        WHERE ct.category_id = ? AND c.user_id = ?
        ORDER BY t.name_lower
        """,
        (category_id, user_id),
    ).fetchall()
    return [dict(row) for row in rows]


def get_bookmark_tags(user_id, bookmark_id):
    db = get_db()
    rows = db.execute(
        """
        SELECT t.* FROM tags t
        JOIN bookmark_tags bt ON bt.tag_id = t.id
        JOIN bookmarks b ON b.id = bt.bookmark_id
        WHERE bt.bookmark_id = ? AND b.user_id = ?
        ORDER BY t.name_lower
        """,
        (bookmark_id, user_id),
    ).fetchall()
    return [dict(row) for row in rows]


def delete_tag(user_id, tag_id):
    db = get_db()
    # Explicit join-table cleanup (cascade also covers this when FKs are on).
    db.execute(
        "DELETE FROM bookmark_tags WHERE tag_id IN "
        "(SELECT id FROM tags WHERE user_id = ? AND id = ?)",
        (user_id, tag_id),
    )
    db.execute("DELETE FROM tags WHERE user_id = ? AND id = ?", (user_id, tag_id))
    db.commit()
