from unittest.mock import MagicMock, patch

import pytest
import requests

from server import geocode_client
from server.geocode_client import GeocodeError, geocode_address
from server.models.geocode_cache import get_cached, normalise_query, put_cached


@pytest.fixture(autouse=True)
def _no_rate_limit(app):
    app.config["NOMINATIM_RATE_LIMIT_MS"] = 0
    geocode_client._last_call = None


def _resp(payload, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload
    return r


def test_normalise_query_collapses_whitespace_and_case():
    assert normalise_query("  1  Main   St ") == normalise_query("1 main st")


def test_cache_roundtrip_and_replace(app):
    put_cached("  1  Main   St ", -27.0, 153.0, "A")
    assert get_cached("1 MAIN st") == {"lat": -27.0, "lon": 153.0, "display_name": "A"}
    put_cached("1 main st", -28.0, 154.0, "B")
    assert get_cached("1  main  st") == {"lat": -28.0, "lon": 154.0, "display_name": "B"}
    assert get_cached("nowhere") is None


def test_geocode_hit_returns_result_and_caches(app):
    with patch("server.geocode_client.requests.get") as get:
        get.return_value = _resp([{"lat": "-27.47", "lon": "153.02", "display_name": "X"}])
        result = geocode_address("1 Main St")
    assert result == {"lat": -27.47, "lon": 153.02, "display_name": "X"}
    assert isinstance(result["lat"], float) and isinstance(result["lon"], float)
    assert get.call_count == 1
    kwargs = get.call_args.kwargs
    assert kwargs["params"]["q"] == "1 Main St"
    assert kwargs["params"]["format"] == "jsonv2"
    assert kwargs["params"]["limit"] == 1
    assert kwargs["headers"]["User-Agent"] == "GPX-Route-Exploration/1.0"
    assert kwargs["timeout"] == 10


def test_geocode_same_address_twice_calls_network_once(app):
    with patch("server.geocode_client.requests.get") as get:
        get.return_value = _resp([{"lat": "1", "lon": "2", "display_name": "X"}])
        a = geocode_address("1 Main St")
        b = geocode_address("  1  MAIN st ")
    assert get.call_count == 1
    assert a["lat"] == b["lat"] and a["lon"] == b["lon"]


def test_geocode_no_results_returns_none_and_is_not_cached(app):
    with patch("server.geocode_client.requests.get") as get:
        get.return_value = _resp([])
        assert geocode_address("nowhere") is None
        assert geocode_address("nowhere") is None
    assert get.call_count == 2


def test_geocode_http_error_and_timeout_raise_geocode_error(app):
    with patch("server.geocode_client.requests.get") as get:
        get.return_value = _resp([], status=500)
        with pytest.raises(GeocodeError):
            geocode_address("a")
        get.side_effect = requests.Timeout()
        with pytest.raises(GeocodeError):
            geocode_address("b")
        bad = _resp(None)
        bad.json.side_effect = ValueError("no json")
        get.side_effect = None
        get.return_value = bad
        with pytest.raises(GeocodeError):
            geocode_address("c")


def test_geocode_rate_limit_waits_between_network_calls(app):
    app.config["NOMINATIM_RATE_LIMIT_MS"] = 200
    with patch("server.geocode_client.requests.get") as get, \
            patch("server.geocode_client.time.sleep") as sleep, \
            patch("server.geocode_client.time.monotonic", return_value=100.0):
        get.return_value = _resp([{"lat": "1", "lon": "2", "display_name": "X"}])
        geocode_address("first")
        assert sleep.call_count == 0
        geocode_address("second")
        assert sleep.call_count == 1
        assert sleep.call_args.args[0] == pytest.approx(0.2, abs=0.01)
        geocode_address("first")  # cache hit
        assert sleep.call_count == 1
    assert get.call_count == 2


def test_rate_limit_default_is_1000_ms(monkeypatch):
    import importlib
    import server.config as config

    monkeypatch.delenv("NOMINATIM_RATE_LIMIT_MS", raising=False)
    try:
        importlib.reload(config)
        assert config.Config.NOMINATIM_RATE_LIMIT_MS == 1000
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_csv_limit_defaults(monkeypatch):
    import importlib
    import server.config as config

    monkeypatch.delenv("CSV_MAX_BYTES", raising=False)
    monkeypatch.delenv("CSV_MAX_ROWS", raising=False)
    try:
        importlib.reload(config)
        assert config.Config.CSV_MAX_BYTES == 1048576
        assert config.Config.CSV_MAX_ROWS == 200
    finally:
        monkeypatch.undo()
        importlib.reload(config)
