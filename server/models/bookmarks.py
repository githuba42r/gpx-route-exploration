"""Per-user bookmarks (reusable locations). Every query is scoped by user_id."""

import math
import uuid

from server.models import get_db

NAME_MAX = 120
DESCRIPTION_MAX = 2000
_UPDATABLE = ("name", "description", "lat", "lon")


def _is_real(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def validate_bookmark_fields(data, *, partial):
    """Return (clean, error). With partial=True only supplied fields are checked
    and at least one must be present."""
    if not isinstance(data, dict):
        return None, "JSON object required"
    clean = {}
    if "name" in data or not partial:
        name = data.get("name")
        if not isinstance(name, str):
            return None, "name is required"
        name = name.strip()
        if not 1 <= len(name) <= NAME_MAX:
            return None, f"name must be 1-{NAME_MAX} characters"
        clean["name"] = name
    for key, limit in (("lat", 90), ("lon", 180)):
        if key in data or not partial:
            v = data.get(key)
            if not _is_real(v):
                return None, f"{key} must be a number"
            if abs(v) > limit:
                return None, f"{key} must be between -{limit} and {limit}"
            clean[key] = float(v)
    if "description" in data:
        d = data["description"]
        if d is None:
            d = ""
        if not isinstance(d, str):
            return None, "description must be a string"
        if len(d) > DESCRIPTION_MAX:
            return None, f"description must be at most {DESCRIPTION_MAX} characters"
        clean["description"] = d
    if partial and not clean:
        return None, "no valid fields to update"
    return clean, None


def create_bookmark(user_id, *, name, lat, lon, description=""):
    db = get_db()
    cur = db.execute(
        "INSERT INTO bookmarks (uuid, user_id, name, description, lat, lon) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (uuid.uuid4().hex, user_id, name, description or "", lat, lon),
    )
    db.commit()
    return get_bookmark(user_id, cur.lastrowid)


def get_bookmark(user_id, bookmark_id):
    row = get_db().execute(
        "SELECT * FROM bookmarks WHERE user_id = ? AND id = ?",
        (user_id, bookmark_id),
    ).fetchone()
    return dict(row) if row else None


def list_bookmarks(user_id):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM bookmarks WHERE user_id = ? ORDER BY updated_at DESC, id DESC",
        (user_id,),
    ).fetchall()
    tag_rows = db.execute(
        """
        SELECT bt.bookmark_id, t.name FROM bookmark_tags bt
        JOIN tags t ON t.id = bt.tag_id
        JOIN bookmarks b ON b.id = bt.bookmark_id
        WHERE b.user_id = ? ORDER BY t.name_lower
        """,
        (user_id,),
    ).fetchall()
    tags = {}
    for r in tag_rows:
        tags.setdefault(r["bookmark_id"], []).append(r["name"])
    out = []
    for r in rows:
        d = dict(r)
        d["tags"] = tags.get(d["id"], [])
        d["photo_count"] = 0  # filled in by the photo task
        d["thumb_url"] = None
        out.append(d)
    return out


def update_bookmark(user_id, bookmark_id, **fields):
    fields = {k: v for k, v in fields.items() if k in _UPDATABLE}
    if get_bookmark(user_id, bookmark_id) is None:
        return None
    db = get_db()
    sets = ", ".join(f"{k} = ?" for k in fields)
    sets = (sets + ", " if sets else "") + "updated_at = CURRENT_TIMESTAMP"
    db.execute(
        f"UPDATE bookmarks SET {sets} WHERE user_id = ? AND id = ?",
        (*fields.values(), user_id, bookmark_id),
    )
    db.commit()
    return get_bookmark(user_id, bookmark_id)


def delete_bookmark(user_id, bookmark_id):
    row = get_bookmark(user_id, bookmark_id)
    if row is None:
        return None
    db = get_db()
    # Foreign keys are ON in get_db(), but delete join rows explicitly anyway.
    db.execute("DELETE FROM bookmark_tags WHERE bookmark_id = ?", (bookmark_id,))
    db.execute("DELETE FROM bookmark_photos WHERE bookmark_id = ?", (bookmark_id,))
    db.execute("DELETE FROM bookmarks WHERE user_id = ? AND id = ?", (user_id, bookmark_id))
    db.commit()
    return row
