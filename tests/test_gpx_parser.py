import os
import pytest
from server.gpx_parser import parse_gpx

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def test_parse_valid_gpx():
    with open(os.path.join(FIXTURES, "sample.gpx"), "rb") as f:
        result = parse_gpx(f.read())
    assert result["name"] == "Test Route"
    assert result["point_count"] == 10
    assert result["distance_km"] > 0
    assert result["min_elevation"] == pytest.approx(65.0)
    assert result["max_elevation"] == pytest.approx(95.0)
    assert result["max_gradient_asc"] > 0
    assert result["max_gradient_desc"] < 0


def test_parse_gpx_no_name():
    with open(os.path.join(FIXTURES, "sample_no_name.gpx"), "rb") as f:
        result = parse_gpx(f.read())
    assert result["name"] is None
    assert result["point_count"] == 2


def test_parse_invalid_file():
    with open(os.path.join(FIXTURES, "invalid.txt"), "rb") as f:
        with pytest.raises(ValueError, match="Invalid GPX"):
            parse_gpx(f.read())


def test_parse_empty_gpx():
    gpx = b"""<?xml version='1.0'?>
    <gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
    <trk><trkseg></trkseg></trk></gpx>"""
    with pytest.raises(ValueError, match="No trackpoints"):
        parse_gpx(gpx)
