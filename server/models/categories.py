import re
import sqlite3

from server.models import get_db


def _slugify(name):
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


def ensure_default_category(user_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM categories WHERE user_id = ? AND slug = 'default'",
        (user_id,),
    ).fetchone()
    if row:
        return dict(row)
    db.execute(
        "INSERT INTO categories (user_id, name, slug, description) VALUES (?, ?, ?, ?)",
        (user_id, "Default", "default", ""),
    )
    db.commit()
    row = db.execute(
        "SELECT * FROM categories WHERE user_id = ? AND slug = 'default'",
        (user_id,),
    ).fetchone()
    return dict(row)


def create_category(user_id, name, description=""):
    db = get_db()
    slug = _slugify(name)
    db.execute(
        "INSERT INTO categories (user_id, name, slug, description) VALUES (?, ?, ?, ?)",
        (user_id, name, slug, description),
    )
    db.commit()
    row = db.execute(
        "SELECT * FROM categories WHERE user_id = ? AND slug = ?",
        (user_id, slug),
    ).fetchone()
    return dict(row)


def get_categories(user_id):
    db = get_db()
    rows = db.execute(
        """
        SELECT c.*, COUNT(r.id) AS route_count
        FROM categories c
        LEFT JOIN routes r ON r.category_id = c.id AND r.user_id = c.user_id
        WHERE c.user_id = ?
        GROUP BY c.id
        ORDER BY c.name
        """,
        (user_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_category(user_id, category_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM categories WHERE user_id = ? AND id = ?",
        (user_id, category_id),
    ).fetchone()
    return dict(row) if row else None


def rename_category(user_id, category_id, name=None, description=None):
    category = get_category(user_id, category_id)
    if category is None:
        raise ValueError("Category not found")
    if category["slug"] == "default":
        raise ValueError("Cannot rename the default category")

    db = get_db()
    if name is not None:
        new_slug = _slugify(name)
        db.execute(
            "UPDATE categories SET name = ?, slug = ? WHERE user_id = ? AND id = ?",
            (name, new_slug, user_id, category_id),
        )
    if description is not None:
        db.execute(
            "UPDATE categories SET description = ? WHERE user_id = ? AND id = ?",
            (description, user_id, category_id),
        )
    db.commit()
    return get_category(user_id, category_id)


def delete_category(user_id, category_id, move_to_default=False):
    category = get_category(user_id, category_id)
    if category is None:
        raise ValueError("Category not found")
    if category["slug"] == "default":
        raise ValueError("Cannot delete the default category")

    db = get_db()
    route_count = db.execute(
        "SELECT COUNT(*) FROM routes WHERE user_id = ? AND category_id = ?",
        (user_id, category_id),
    ).fetchone()[0]

    if route_count > 0:
        if not move_to_default:
            raise ValueError("Category is not empty; use move_to_default=True to move routes")
        default = ensure_default_category(user_id)
        db.execute(
            "UPDATE routes SET category_id = ? WHERE user_id = ? AND category_id = ?",
            (default["id"], user_id, category_id),
        )

    db.execute("DELETE FROM categories WHERE user_id = ? AND id = ?", (user_id, category_id))
    db.commit()
