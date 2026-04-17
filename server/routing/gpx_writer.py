"""GPX 1.1 writer. M1 writes <trk> only. M4 extends with <wpt> entries."""

import xml.etree.ElementTree as ET
from xml.dom import minidom


def decode_polyline(encoded, precision=6):
    """Decode a Google Encoded Polyline string into a list of (lat, lon)."""
    factor = 10 ** precision
    coords = []
    lat = lng = 0
    i = 0
    while i < len(encoded):
        for _ in range(2):
            result = 0
            shift = 0
            while True:
                b = ord(encoded[i]) - 63
                i += 1
                result |= (b & 0x1f) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else (result >> 1)
            if _ == 0:
                lat += delta
            else:
                lng += delta
        coords.append((lat / factor, lng / factor))
    return coords


def encode_polyline(points, precision=6):
    """Encode a list of (lat, lon) tuples into a Google Encoded Polyline."""
    factor = 10 ** precision
    result = []
    last_lat = last_lng = 0
    for lat, lng in points:
        lat_i = int(round(lat * factor))
        lng_i = int(round(lng * factor))
        dlat = lat_i - last_lat
        dlng = lng_i - last_lng
        last_lat, last_lng = lat_i, lng_i
        for v in (dlat, dlng):
            v = ~(v << 1) if v < 0 else (v << 1)
            while v >= 0x20:
                result.append(chr((0x20 | (v & 0x1f)) + 63))
                v >>= 5
            result.append(chr(v + 63))
    return "".join(result)


def write_track_gpx(path, *, title, legs, precision=6):
    """Write a track-only GPX file.

    legs: list of dicts, each with a 'polyline' key (encoded polyline).
          Consecutive legs are concatenated and the duplicate boundary
          point is dropped.
    """
    all_points = []
    for i, leg in enumerate(legs):
        decoded = decode_polyline(leg["polyline"], precision=precision)
        if i > 0 and decoded and all_points and all_points[-1] == decoded[0]:
            decoded = decoded[1:]
        all_points.extend(decoded)

    ns = "http://www.topografix.com/GPX/1/1"
    ET.register_namespace("", ns)
    gpx = ET.Element("gpx", {
        "version": "1.1",
        "creator": "GPX Route Exploration",
        "xmlns": ns,
    })
    meta = ET.SubElement(gpx, "metadata")
    ET.SubElement(meta, "name").text = title

    trk = ET.SubElement(gpx, "trk")
    ET.SubElement(trk, "name").text = title
    trkseg = ET.SubElement(trk, "trkseg")
    for lat, lon in all_points:
        ET.SubElement(trkseg, "trkpt", {"lat": f"{lat:.7f}", "lon": f"{lon:.7f}"})

    xml_bytes = ET.tostring(gpx, encoding="utf-8", xml_declaration=True)
    pretty = minidom.parseString(xml_bytes).toprettyxml(indent="  ", encoding="utf-8")
    with open(path, "wb") as f:
        f.write(pretty)
