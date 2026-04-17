"""Tests for server.routing.gpx_writer."""

from server.routing.gpx_writer import decode_polyline, write_track_gpx


def test_decode_polyline_roundtrip():
    from server.routing.gpx_writer import encode_polyline
    points = [(45.0, -122.0), (45.01, -122.01)]
    encoded = encode_polyline(points, precision=6)
    decoded = decode_polyline(encoded, precision=6)
    assert len(decoded) == 2
    assert abs(decoded[0][0] - 45.0) < 1e-5
    assert abs(decoded[0][1] - (-122.0)) < 1e-5


def test_write_track_gpx_produces_valid_xml(tmp_path):
    from server.routing.gpx_writer import encode_polyline
    legs = [
        {"polyline": encode_polyline([(-27.4, 152.9), (-27.41, 152.91)], precision=6)},
        {"polyline": encode_polyline([(-27.41, 152.91), (-27.42, 152.92)], precision=6)},
    ]
    path = tmp_path / "out.gpx"
    write_track_gpx(str(path), title="Test Route", legs=legs, precision=6)
    content = path.read_text()
    assert content.startswith('<?xml')
    assert '<trk>' in content
    assert '<name>Test Route</name>' in content
    # Two legs concatenated → three distinct trkpts (leg boundary deduped).
    assert content.count('<trkpt') == 3
    # Every trkpt must carry <ele> — without it the analysis page's loader
    # drops the point and crashes on 'points[0].dist = ...'. Placeholder 0 is
    # fine until M3 wires real elevation from Valhalla's samples.
    assert content.count('<ele>') == 3
