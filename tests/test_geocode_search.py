from unittest.mock import MagicMock, patch

import pytest
import requests

from server import geocode_client
from server.models.geocode_cache import get_cached


@pytest.fixture(autouse=True)
def _reset(app):
    geocode_client._last_call = None
    app.config["NOMINATIM_RATE_LIMIT_MS"] = 0


def _resp(body, status=200):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = body
    return m


def test_search_returns_normalised_results_in_order(client):
    hits = [
        {"display_name": "A St, Town", "lat": "1.5", "lon": "2.5"},
        {"display_name": "B St, Town", "lat": "3", "lon": "4"},
    ]
    with patch("server.geocode_client.requests.get", return_value=_resp(hits)) as g:
        r = client.get("/api/geocode/search?q=High Street")
    assert r.status_code == 200
    assert r.get_json() == [
        {"display_name": "A St, Town", "lat": 1.5, "lon": 2.5},
        {"display_name": "B St, Town", "lat": 3.0, "lon": 4.0},
    ]
    kw = g.call_args.kwargs
    assert kw["params"]["format"] == "jsonv2"
    assert kw["params"]["limit"] == 5
    assert kw["headers"]["User-Agent"] == "GPX-Route-Exploration/1.0"


def test_search_short_query_returns_empty_without_network(client):
    with patch("server.geocode_client.requests.get") as g:
        for q in ("ab", "  a "):
            r = client.get("/api/geocode/search", query_string={"q": q})
            assert r.status_code == 200
            assert r.get_json() == []
    g.assert_not_called()


def test_search_limit_is_clamped_and_defaulted(client):
    for given, sent in (("0", 1), ("99", 10), ("abc", 5)):
        with patch("server.geocode_client.requests.get", return_value=_resp([])) as g:
            client.get(f"/api/geocode/search?q=High Street&limit={given}")
        assert g.call_args.kwargs["params"]["limit"] == sent


def test_search_does_not_write_the_cache(app, client):
    hits = [{"display_name": "A", "lat": "1", "lon": "2"}]
    with patch("server.geocode_client.requests.get", return_value=_resp(hits)):
        client.get("/api/geocode/search?q=High Street")
    with app.app_context():
        assert get_cached("High Street") is None


@pytest.mark.parametrize("effect", [
    {"return_value": _resp([], 500)},
    {"side_effect": requests.Timeout("t")},
    {"side_effect": requests.ConnectionError("c")},
    {"return_value": _resp({"not": "a list"})},
    {"return_value": _resp([{"display_name": "A", "lon": "2"}])},
])
def test_search_upstream_failures_give_502(client, effect):
    with patch("server.geocode_client.requests.get", **effect):
        r = client.get("/api/geocode/search?q=High Street")
    assert r.status_code == 502
    assert r.get_json() == {"error": "Address search is unavailable"}


def test_search_empty_results_give_empty_list(client):
    with patch("server.geocode_client.requests.get", return_value=_resp([])):
        r = client.get("/api/geocode/search?q=Nowhere Land")
    assert r.status_code == 200
    assert r.get_json() == []
