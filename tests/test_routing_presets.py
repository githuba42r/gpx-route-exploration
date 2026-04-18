"""Unit tests for routing presets (M3a)."""

import pytest

from server.routing import presets


def test_preset_list_contains_expected_keys():
    listed = presets.list_presets()
    names = [p["name"] for p in listed]
    assert names == ["road", "gravel-mtb", "easy", "hike", "drive", "custom"]


def test_preset_list_hides_hybrid_alias():
    # 'hybrid' is a legacy DB value (see D1); it must NOT appear in the
    # user-facing preset list.
    names = [p["name"] for p in presets.list_presets()]
    assert "hybrid" not in names


def test_resolve_known_preset_returns_costing_options_and_profile():
    res = presets.resolve("gravel-mtb")
    assert res["profile"] == "bicycle"
    assert res["costing_options"]["bicycle_type"] == "Mountain"
    # gravel-mtb accepts unpaved surfaces.
    assert res["costing_options"]["use_roads"] < 0.6


def test_resolve_hybrid_alias_maps_to_road():
    # D1: legacy DB rows with costing_preset='hybrid' still resolve.
    alias = presets.resolve("hybrid")
    road = presets.resolve("road")
    assert alias == road


def test_resolve_custom_returns_empty_options():
    # 'custom' is the opt-out: the client supplies its own costing_options
    # and the preset contributes nothing.
    res = presets.resolve("custom")
    assert res["costing_options"] == {}


def test_resolve_unknown_preset_raises():
    with pytest.raises(ValueError):
        presets.resolve("not-a-preset")


def test_hike_uses_pedestrian_profile():
    res = presets.resolve("hike")
    assert res["profile"] == "pedestrian"


def test_drive_uses_auto_profile():
    res = presets.resolve("drive")
    assert res["profile"] == "auto"
