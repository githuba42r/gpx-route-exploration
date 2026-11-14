import time

from server.models import get_db


def normalise_query(q):
    return " ".join(q.split()).casefold()


def get_cached(query):
    row = get_db().execute(
        "SELECT lat, lon, display_name FROM geocode_cache WHERE query = ?",
        (normalise_query(query),),
    ).fetchone()
    if row is None:
        return None
    return {"lat": row["lat"], "lon": row["lon"], "display_name": row["display_name"]}


def put_cached(query, lat, lon, display_name):
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO geocode_cache (query, lat, lon, display_name, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (normalise_query(query), lat, lon, display_name, int(time.time())),
    )
    db.commit()
