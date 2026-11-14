"""Playwright tests for the Create page 'Add by address' search box.

The live test server cannot mock Nominatim, so the browser's call to
/api/geocode/search is intercepted with page.route().
"""

import json
import re

import requests as http_requests
from playwright.sync_api import expect

RESULTS = [
    {"display_name": "Queen Street, Auckland, New Zealand", "lat": "-36.85", "lon": "174.76"},
    {"display_name": "Queen Street, Wellington, New Zealand", "lat": "-41.28", "lon": "174.77"},
    {"display_name": "Queen Street, Hamilton, New Zealand", "lat": "-37.78", "lon": "175.28"},
]


def _fulfil(route, body, status=200):
    route.fulfill(status=status, content_type="application/json", body=json.dumps(body))


def _open(page, server_url):
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    page.wait_for_function(
        "() => new URL(location.href).searchParams.get('route_id') !== null")
    expect(page.locator("#add-address")).to_be_visible()


def _route_id(page):
    return page.evaluate("new URL(location.href).searchParams.get('route_id')")


def test_typing_shows_live_suggestions(page, server_url):
    requests = []

    def handler(route):
        requests.append(route.request.url)
        _fulfil(route, RESULTS)

    page.route("**/api/geocode/search*", handler)
    _open(page, server_url)
    page.locator("#add-address").fill("Qu")
    page.wait_for_timeout(700)
    assert requests == []
    page.locator("#add-address").fill("Queen Street")
    items = page.locator("#address-suggestions li")
    expect(items).to_have_count(3)
    expect(items.nth(0)).to_have_text(RESULTS[0]["display_name"])
    expect(items.nth(1)).to_have_text(RESULTS[1]["display_name"])
    assert len(requests) == 1


def test_selecting_a_suggestion_appends_a_stop(page, server_url):
    page.route("**/api/geocode/search*", lambda r: _fulfil(r, RESULTS))
    _open(page, server_url)
    page.locator("#add-address").fill("Queen Street")
    page.locator("#address-suggestions li").nth(0).click()
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 1", timeout=5000)
    wps = http_requests.get(
        f"{server_url}/api/routes/{_route_id(page)}/waypoints").json()
    assert len(wps) == 1
    w = wps[0]
    assert w["kind"] == "stop"
    assert w["name"] == "Queen Street"
    assert w["address"] == RESULTS[0]["display_name"]
    assert abs(w["lat"] - -36.85) < 1e-6 and abs(w["lon"] - 174.76) < 1e-6
    expect(page.locator("#add-address")).to_have_value("")
    expect(page.locator("#address-suggestions li")).to_have_count(0)


def test_keyboard_navigation(page, server_url):
    page.route("**/api/geocode/search*", lambda r: _fulfil(r, RESULTS))
    _open(page, server_url)
    inp = page.locator("#add-address")
    inp.fill("Queen Street")
    expect(page.locator("#address-suggestions li")).to_have_count(3)
    inp.press("ArrowDown")
    inp.press("ArrowDown")
    inp.press("Enter")
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 1", timeout=5000)
    wps = http_requests.get(
        f"{server_url}/api/routes/{_route_id(page)}/waypoints").json()
    assert wps[0]["address"] == RESULTS[1]["display_name"]

    inp.fill("Queen Street")
    expect(page.locator("#address-suggestions li")).to_have_count(3)
    inp.press("Escape")
    expect(page.locator("#address-suggestions li")).to_have_count(0)


def test_stale_response_does_not_overwrite_newer_results(page, server_url):
    held = []
    newer = [{"display_name": "Newer Road, Town", "lat": "1", "lon": "2"}]

    def handler(route):
        if "q=first" in route.request.url.lower() or "first" in route.request.url:
            held.append(route)
        else:
            _fulfil(route, newer)

    page.route("**/api/geocode/search*", handler)
    _open(page, server_url)
    inp = page.locator("#add-address")
    inp.fill("first query")
    for _ in range(50):
        if held:
            break
        page.wait_for_timeout(100)
    assert held
    inp.fill("second query")
    expect(page.locator("#address-suggestions li")).to_have_count(1)
    try:
        _fulfil(held[0], [{"display_name": "STALE", "lat": "0", "lon": "0"}])
    except Exception:
        pass  # request was aborted by the client; that is also fine
    page.wait_for_timeout(300)
    expect(page.locator("#address-suggestions li")).to_have_count(1)
    expect(page.locator("#address-suggestions li").first).to_have_text("Newer Road, Town")


def test_search_failure_shows_inline_message_and_stays_usable(page, server_url):
    state = {"fail": True}

    def handler(route):
        if state["fail"]:
            _fulfil(route, {"error": "Address search is unavailable"}, status=502)
        else:
            _fulfil(route, RESULTS)

    page.route("**/api/geocode/search*", handler)
    _open(page, server_url)
    inp = page.locator("#add-address")
    inp.fill("Queen Street")
    expect(page.locator("#address-status")).to_contain_text("Address search unavailable")
    state["fail"] = False
    inp.fill("Queen Street 2")
    expect(page.locator("#address-suggestions li")).to_have_count(3)
    expect(page.locator("#address-status")).not_to_contain_text("unavailable")


def test_no_matches_message(page, server_url):
    page.route("**/api/geocode/search*", lambda r: _fulfil(r, []))
    _open(page, server_url)
    page.locator("#add-address").fill("Nowhereville")
    expect(page.locator("#address-status")).to_contain_text("No matches")


def test_suggestion_text_is_not_interpreted_as_html(page, server_url):
    payload = '<img src=x onerror="window.__xss=1">'
    page.route("**/api/geocode/search*", lambda r: _fulfil(
        r, [{"display_name": payload, "lat": "1", "lon": "2"}]))
    _open(page, server_url)
    page.locator("#add-address").fill("anything")
    item = page.locator("#address-suggestions li").first
    expect(item).to_have_text(payload)
    page.wait_for_timeout(300)
    assert page.evaluate("typeof window.__xss") == "undefined"
    assert page.locator("#address-suggestions img").count() == 0


def test_busy_class_while_request_in_flight(page, server_url):
    held = []
    page.route("**/api/geocode/search*", lambda r: held.append(r))
    _open(page, server_url)
    page.locator("#add-address").fill("Queen Street")
    expect(page.locator("#address-bar")).to_have_class(re.compile(r"is-busy"))
    _fulfil(held[0], RESULTS)
    expect(page.locator("#address-suggestions li")).to_have_count(3)
    expect(page.locator("#address-bar")).not_to_have_class(re.compile(r"is-busy"))


def test_failed_add_keeps_the_query_and_shows_a_message(page, server_url):
    page.route("**/api/geocode/search*", lambda r: _fulfil(r, RESULTS))

    def wp_handler(route):
        if route.request.method == "POST":
            _fulfil(route, {"error": "boom"}, status=500)
        else:
            route.continue_()

    page.route("**/api/routes/*/waypoints", wp_handler)
    _open(page, server_url)
    inp = page.locator("#add-address")
    inp.fill("Queen Street")
    expect(page.locator("#address-suggestions li")).to_have_count(3)
    page.locator("#address-suggestions li").nth(0).click()
    expect(page.locator("#address-status")).to_contain_text("Could not add stop")
    expect(inp).to_have_value("Queen Street")
    expect(page.locator("#address-suggestions li")).to_have_count(3)
    expect(page.locator(".wpe-item")).to_have_count(0)
    expect(page.locator("#address-bar")).not_to_have_class(re.compile(r"is-busy"))
