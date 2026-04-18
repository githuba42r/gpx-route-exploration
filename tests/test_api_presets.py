"""Endpoint tests for /api/routing-presets (M3a)."""


def test_get_presets_returns_expected_shape(client):
    resp = client.get("/api/routing-presets")
    assert resp.status_code == 200
    body = resp.get_json()
    assert isinstance(body, list)
    names = [p["name"] for p in body]
    assert names == ["road", "gravel-mtb", "easy", "hike", "drive", "custom"]
    for p in body:
        assert "profile" in p
        assert "description" in p


def test_get_presets_hides_hybrid(client):
    body = client.get("/api/routing-presets").get_json()
    assert "hybrid" not in [p["name"] for p in body]
