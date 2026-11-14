import threading
import time

import requests
from flask import current_app

from server.models.geocode_cache import get_cached, put_cached

USER_AGENT = "GPX-Route-Exploration/1.0"

_lock = threading.Lock()
_last_call = None  # monotonic timestamp of the previous network call


class GeocodeError(Exception):
    pass


def _wait_for_rate_limit(limit_s):
    """Block until limit_s has passed since the previous network call, then
    stamp this call. Held under the lock so threads are serialised."""
    global _last_call
    if _last_call is not None:
        wait = limit_s - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(min(wait, limit_s))
    _last_call = time.monotonic()


def geocode_address(address):
    cached = get_cached(address)
    if cached is not None:
        return {"lat": cached["lat"], "lon": cached["lon"],
                "display_name": cached["display_name"]}

    limit_s = current_app.config["NOMINATIM_RATE_LIMIT_MS"] / 1000.0
    url = current_app.config["NOMINATIM_URL"].rstrip("/") + "/search"
    with _lock:
        _wait_for_rate_limit(limit_s)
        try:
            resp = requests.get(
                url,
                params={"q": address, "format": "jsonv2", "limit": 1},
                headers={"User-Agent": USER_AGENT},
                timeout=10,
            )
        except requests.RequestException as e:
            raise GeocodeError(f"Nominatim request failed: {e}") from e

    if resp.status_code != 200:
        raise GeocodeError(f"Nominatim returned HTTP {resp.status_code}")
    try:
        data = resp.json()
    except ValueError as e:
        raise GeocodeError("Nominatim returned a non-JSON response") from e
    if not isinstance(data, list):
        raise GeocodeError("Unexpected Nominatim response shape")
    if not data:
        return None
    try:
        hit = data[0]
        result = {"lat": float(hit["lat"]), "lon": float(hit["lon"]),
                  "display_name": hit.get("display_name")}
    except (KeyError, TypeError, ValueError) as e:
        raise GeocodeError("Unexpected Nominatim result") from e
    put_cached(address, result["lat"], result["lon"], result["display_name"])
    return result


def geocode_search(query, limit=5):
    """Return up to `limit` Nominatim candidates for `query` (autocomplete).
    Does not read or write the geocode cache."""
    limit_s = current_app.config["NOMINATIM_RATE_LIMIT_MS"] / 1000.0
    url = current_app.config["NOMINATIM_URL"].rstrip("/") + "/search"
    with _lock:
        _wait_for_rate_limit(limit_s)
        try:
            resp = requests.get(
                url,
                params={"q": query, "format": "jsonv2", "limit": limit},
                headers={"User-Agent": USER_AGENT},
                timeout=10,
            )
        except requests.RequestException as e:
            raise GeocodeError(f"Nominatim request failed: {e}") from e

    if resp.status_code != 200:
        raise GeocodeError(f"Nominatim returned HTTP {resp.status_code}")
    try:
        data = resp.json()
    except ValueError as e:
        raise GeocodeError("Nominatim returned a non-JSON response") from e
    if not isinstance(data, list):
        raise GeocodeError("Unexpected Nominatim response shape")
    try:
        return [
            {"display_name": str(hit["display_name"]),
             "lat": float(hit["lat"]), "lon": float(hit["lon"])}
            for hit in data
        ]
    except (KeyError, TypeError, ValueError) as e:
        raise GeocodeError("Unexpected Nominatim result") from e
