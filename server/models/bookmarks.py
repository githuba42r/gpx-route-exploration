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
        SELECT bt.bookmark_id, t.* FROM bookmark_tags bt
        JOIN tags t ON t.id = bt.tag_id
        JOIN bookmarks b ON b.id = bt.bookmark_id
        WHERE b.user_id = ? ORDER BY t.name_lower
        """,
        (user_id,),
    ).fetchall()
    tags = {}
    for r in tag_rows:
        d = dict(r)
        tags.setdefault(d.pop("bookmark_id"), []).append(d)
    photo_rows = db.execute(
        """
        SELECT p.bookmark_id, p.id, p.position FROM bookmark_photos p
        JOIN bookmarks b ON b.id = p.bookmark_id
        WHERE b.user_id = ? ORDER BY p.bookmark_id, p.position
        """,
        (user_id,),
    ).fetchall()
    counts, first = {}, {}
    for r in photo_rows:
        counts[r["bookmark_id"]] = counts.get(r["bookmark_id"], 0) + 1
        first.setdefault(r["bookmark_id"], r["id"])
    out = []
    for r in rows:
        d = dict(r)
        d["tags"] = tags.get(d["id"], [])
        d["photo_count"] = counts.get(d["id"], 0)
        d["thumb_url"] = (
            photo_url(d["id"], first[d["id"]], thumb=True) if d["id"] in first else None
        )
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


# ---- photos -----------------------------------------------------------------

def photo_url(bookmark_id, photo_id, thumb=False):
    return f"/api/bookmarks/{bookmark_id}/photos/{photo_id}" + ("?thumb=1" if thumb else "")


def photo_public(row):
    """Row -> API shape (no storage_name)."""
    d = {k: row[k] for k in ("id", "position", "mime_type", "byte_size", "caption")}
    d["url"] = photo_url(row["bookmark_id"], row["id"])
    d["thumb_url"] = photo_url(row["bookmark_id"], row["id"], thumb=True)
    return d


def add_photo(bookmark_id, *, storage_name, mime_type, byte_size):
    db = get_db()
    nxt = db.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 FROM bookmark_photos WHERE bookmark_id = ?",
        (bookmark_id,),
    ).fetchone()[0]
    cur = db.execute(
        "INSERT INTO bookmark_photos (bookmark_id, position, storage_name, mime_type, byte_size) "
        "VALUES (?, ?, ?, ?, ?)",
        (bookmark_id, nxt, storage_name, mime_type, byte_size),
    )
    db.execute("UPDATE bookmarks SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (bookmark_id,))
    db.commit()
    return get_photo(bookmark_id, cur.lastrowid)


def list_photos(bookmark_id):
    rows = get_db().execute(
        "SELECT * FROM bookmark_photos WHERE bookmark_id = ? ORDER BY position", (bookmark_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_photo(bookmark_id, photo_id):
    row = get_db().execute(
        "SELECT * FROM bookmark_photos WHERE bookmark_id = ? AND id = ?", (bookmark_id, photo_id)
    ).fetchone()
    return dict(row) if row else None


def _apply_order(db, bookmark_id, ordered_ids):
    # Two-step: park every row on a distinct negative position first so the
    # UNIQUE(bookmark_id, position) constraint is never hit mid-update.
    db.execute(
        "UPDATE bookmark_photos SET position = -(position + 1) WHERE bookmark_id = ?",
        (bookmark_id,),
    )
    for pos, pid in enumerate(ordered_ids):
        db.execute(
            "UPDATE bookmark_photos SET position = ? WHERE bookmark_id = ? AND id = ?",
            (pos, bookmark_id, pid),
        )


def delete_photo(bookmark_id, photo_id):
    """Delete the row and re-compact positions to 0..n-1. Returns the deleted row."""
    row = get_photo(bookmark_id, photo_id)
    if row is None:
        return None
    db = get_db()
    db.execute("DELETE FROM bookmark_photos WHERE bookmark_id = ? AND id = ?", (bookmark_id, photo_id))
    _apply_order(db, bookmark_id, [p["id"] for p in list_photos(bookmark_id)])
    db.execute("UPDATE bookmarks SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (bookmark_id,))
    db.commit()
    return row


def reorder_photos(bookmark_id, ordered_ids):
    """Returns True on success, False if ordered_ids is not exactly the current id set."""
    if not isinstance(ordered_ids, list) or any(
        not isinstance(i, int) or isinstance(i, bool) for i in ordered_ids
    ):
        return False
    current = [p["id"] for p in list_photos(bookmark_id)]
    if len(ordered_ids) != len(current) or set(ordered_ids) != set(current):
        return False
    db = get_db()
    _apply_order(db, bookmark_id, ordered_ids)
    db.commit()
    return True
