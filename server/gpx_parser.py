"""GPX parser — Python port of the JS frontend algorithms in js/gpx.js.

Extracts route statistics from raw GPX bytes using the same haversine distance,
moving-average smoothing, and 100 m minimum-window gradient calculations as the
browser-side code, so server-computed stats are consistent with what the map
displays.
"""

import math
from lxml import etree

_NS = "http://www.topografix.com/GPX/1/1"
_GPX_TAG = f"{{{_NS}}}gpx"


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in metres between two WGS-84 points."""
    R = 6_371_000.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _smooth(elevations: list[float], window: int = 7) -> list[float]:
    """Centred moving-average smoothing (mirrors smoothElevations() in gpx.js)."""
    half = window // 2
    n = len(elevations)
    result = []
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n - 1, i + half)
        chunk = elevations[lo : hi + 1]
        result.append(sum(chunk) / len(chunk))
    return result


def parse_gpx(data: bytes) -> dict:
    """Parse raw GPX bytes and return a statistics dictionary.

    Returns
    -------
    dict with keys:
        name             – track/route name (str or None)
        point_count      – number of trackpoints with elevation (int)
        distance_km      – total distance in kilometres (float)
        min_elevation    – minimum raw elevation in metres (float)
        max_elevation    – maximum raw elevation in metres (float)
        max_gradient_asc – steepest ascending gradient as a percentage (float, > 0)
        max_gradient_desc– steepest descending gradient as a percentage (float, < 0)

    Raises
    ------
    ValueError("Invalid GPX: ...")       – data is not valid XML, or root is not <gpx>
    ValueError("No trackpoints found …") – the track contains zero <trkpt> elements
    ValueError("No trackpoints with …")  – trackpoints exist but none carry <ele>
    """
    # --- Parse XML ---------------------------------------------------------
    try:
        root = etree.fromstring(data)
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"Invalid GPX: not valid XML ({exc})") from exc

    if root.tag != _GPX_TAG:
        raise ValueError(
            f"Invalid GPX: root element is <{root.tag}>, expected <gpx>"
        )

    # --- Extract name ------------------------------------------------------
    name_el = root.find(f".//{{{_NS}}}metadata/{{{_NS}}}name")
    name = name_el.text.strip() if name_el is not None and name_el.text else None

    # --- Extract trackpoints -----------------------------------------------
    trkpts = root.findall(f".//{{{_NS}}}trkpt")
    if not trkpts:
        raise ValueError("No trackpoints found in GPX")

    points = []
    for pt in trkpts:
        ele_el = pt.find(f"{{{_NS}}}ele")
        if ele_el is None or not ele_el.text:
            continue
        points.append(
            {
                "lat": float(pt.get("lat")),
                "lon": float(pt.get("lon")),
                "ele": float(ele_el.text),
            }
        )

    if not points:
        raise ValueError("No trackpoints with elevation data")

    # --- Cumulative distances (mirrors computeDistances() in gpx.js) -------
    points[0]["dist"] = 0.0
    for i in range(1, len(points)):
        d = _haversine(
            points[i - 1]["lat"], points[i - 1]["lon"],
            points[i]["lat"],     points[i]["lon"],
        )
        points[i]["dist"] = points[i - 1]["dist"] + d

    total_dist_m = points[-1]["dist"]

    # --- Smooth elevations -------------------------------------------------
    raw_eles = [p["ele"] for p in points]
    smoothed = _smooth(raw_eles, window=7)
    for i, p in enumerate(points):
        p["ele_smooth"] = smoothed[i]

    # --- Gradients with 100 m minimum window (mirrors processTrackData()) --
    gradient_dist = 100.0  # metres
    gradients = [0.0]  # first point is always 0
    for i in range(1, len(points)):
        j = i - 1
        while j > 0 and (points[i]["dist"] - points[j]["dist"]) < gradient_dist:
            j -= 1
        d_dist = points[i]["dist"] - points[j]["dist"]
        if d_dist > 1.0:
            g = ((points[i]["ele_smooth"] - points[j]["ele_smooth"]) / d_dist) * 100.0
        else:
            g = 0.0
        gradients.append(g)

    # --- Aggregate stats ---------------------------------------------------
    min_ele = min(raw_eles)
    max_ele = max(raw_eles)
    max_grad_asc = max(gradients)
    max_grad_desc = min(gradients)

    return {
        "name": name,
        "point_count": len(points),
        "distance_km": total_dist_m / 1000.0,
        "min_elevation": min_ele,
        "max_elevation": max_ele,
        "max_gradient_asc": max_grad_asc,
        "max_gradient_desc": max_grad_desc,
    }
