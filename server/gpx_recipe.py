"""Derive a waypoint recipe from an existing GPX track."""

import bisect
import math

from lxml import etree

from server.gpx_parser import _NS, _haversine


def extract_waypoints(gpx_bytes: bytes, count: int = 6) -> list[dict]:
    """Pick `count` points evenly spaced by distance along the track.

    Always includes the first and last trackpoint. A track with fewer
    trackpoints than `count` returns every trackpoint. Raises ValueError
    for invalid XML, fewer than 2 trackpoints, or count < 2.
    """
    if count < 2:
        raise ValueError("count must be at least 2")
    try:
        root = etree.fromstring(gpx_bytes)
    except etree.XMLSyntaxError:
        raise ValueError("The GPX file is not valid XML")

    pts = []
    for el in root.iter(f"{{{_NS}}}trkpt"):
        try:
            lat, lon = float(el.get("lat")), float(el.get("lon"))
        except (TypeError, ValueError):
            continue
        if math.isfinite(lat) and math.isfinite(lon):
            pts.append((lat, lon))
    if len(pts) < 2:
        raise ValueError("The track needs at least 2 trackpoints")

    n = len(pts)
    if n <= count:
        chosen = list(range(n))
    else:
        cum = [0.0]
        for a, b in zip(pts, pts[1:]):
            cum.append(cum[-1] + _haversine(a[0], a[1], b[0], b[1]))
        total = cum[-1]
        chosen = [0]
        for i in range(1, count - 1):
            target = total * i / (count - 1)
            j = bisect.bisect_left(cum, target)
            if j > 0 and (j >= n or target - cum[j - 1] <= cum[j] - target):
                j -= 1
            # Keep indices strictly increasing and leave room for the rest.
            j = max(j, chosen[-1] + 1)
            j = min(j, n - 1 - (count - 1 - i))
            chosen.append(j)
        chosen.append(n - 1)

    return [
        {"name": f"Point {k}", "lat": pts[i][0], "lon": pts[i][1]}
        for k, i in enumerate(chosen, start=1)
    ]
