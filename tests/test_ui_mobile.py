"""M7 mobile-responsive UI tests (iPhone 13 emulation)."""

import pytest
import requests as http_requests


@pytest.fixture
def mobile_page(playwright, server_url):
    device = playwright.devices["iPhone 13"]
    browser = playwright.chromium.launch()
    context = browser.new_context(**device)
    page = context.new_page()
    yield page
    context.close()
    browser.close()


def make_route(server_url, n_waypoints=3, title="Mobile test"):
    """Create a route with a GPX file on disk AND a recipe."""
    gpx = (
        b'<?xml version="1.0"?><gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">'
        b'<metadata><name>test</name></metadata>'
        b'<trk><trkseg>'
        b'<trkpt lat="-27.4" lon="152.9"><ele>10</ele></trkpt>'
        b'<trkpt lat="-27.41" lon="152.91"><ele>11</ele></trkpt>'
        b'<trkpt lat="-27.42" lon="152.92"><ele>12</ele></trkpt>'
        b'</trkseg></trk></gpx>'
    )
    r = http_requests.post(
        f"{server_url}/api/routes",
        files={"file": ("route.gpx", gpx)},
        data={"title": title},
    )
    rid = r.json()["id"]
    for i in range(n_waypoints):
        http_requests.post(
            f"{server_url}/api/routes/{rid}/waypoints",
            json={"name": f"WP{i}", "lat": -27.40 - i * 0.01,
                  "lon": 152.90 + i * 0.01, "kind": "stop"},
        )
    return rid


def assert_no_hscroll(page):
    sw, cw = page.evaluate(
        "[document.documentElement.scrollWidth, document.documentElement.clientWidth]"
    )
    assert sw <= cw, f"horizontal overflow: scrollWidth={sw} > clientWidth={cw}"


def test_no_horizontal_scroll_library(mobile_page, server_url):
    make_route(server_url)
    mobile_page.set_viewport_size({"width": 360, "height": 740})
    mobile_page.goto(f"{server_url}/")
    mobile_page.wait_for_timeout(800)
    assert_no_hscroll(mobile_page)


def test_no_horizontal_scroll_analysis(mobile_page, server_url):
    rid = make_route(server_url)
    mobile_page.set_viewport_size({"width": 360, "height": 740})
    mobile_page.goto(f"{server_url}/route/{rid}")
    mobile_page.wait_for_timeout(1500)
    assert_no_hscroll(mobile_page)


def test_no_horizontal_scroll_create(mobile_page, server_url):
    mobile_page.set_viewport_size({"width": 360, "height": 740})
    mobile_page.goto(f"{server_url}/create")
    mobile_page.wait_for_timeout(800)
    assert_no_hscroll(mobile_page)


def test_tap_targets_min_44(mobile_page, server_url):
    mobile_page.set_viewport_size({"width": 360, "height": 740})
    mobile_page.goto(f"{server_url}/create")
    mobile_page.wait_for_timeout(800)
    small = []
    for el in mobile_page.locator("#create-header button, #create-header select").all():
        if not el.is_visible():
            continue
        box = el.bounding_box()
        if box and box["height"] < 44:
            small.append((el.evaluate("e => e.id || e.textContent"), box["height"]))
    assert not small, f"tap targets under 44px: {small}"


LONG_TITLE = "A" * 80 + " " + "B" * 60


def test_library_cards_single_column(mobile_page, server_url):
    for _ in range(3):
        make_route(server_url, title=LONG_TITLE)
    mobile_page.set_viewport_size({"width": 390, "height": 800})
    mobile_page.goto(f"{server_url}/")
    mobile_page.wait_for_selector(".route-card")
    cards = mobile_page.locator(".route-card")
    assert cards.count() >= 3
    xs = {round(cards.nth(i).bounding_box()["x"]) for i in range(cards.count())}
    assert len(xs) == 1, f"cards not in one column: {xs}"
    assert_no_hscroll(mobile_page)
    sw, cw = mobile_page.evaluate(
        "[document.querySelector('#route-list').scrollWidth, document.querySelector('#route-list').clientWidth]"
    )
    assert sw <= cw, f"#route-list overflows: {sw} > {cw}"
    vw = mobile_page.evaluate("window.innerWidth")
    for i in range(cards.count()):
        assert cards.nth(i).bounding_box()["x"] + cards.nth(i).bounding_box()["width"] <= vw + 0.5


def _sidebar_in_viewport(page):
    return page.evaluate(
        "(() => { const r = document.querySelector('#sidebar').getBoundingClientRect();"
        " return r.right > 0 && r.left < window.innerWidth; })()"
    )


def test_library_filter_drawer_opens_and_closes(mobile_page, server_url):
    mobile_page.set_viewport_size({"width": 390, "height": 800})
    mobile_page.goto(f"{server_url}/")
    mobile_page.wait_for_selector("#btn-filters")
    assert not _sidebar_in_viewport(mobile_page)
    mobile_page.tap("#btn-filters")
    mobile_page.wait_for_timeout(400)
    assert _sidebar_in_viewport(mobile_page)
    assert mobile_page.locator("#category-panel").is_visible()  # tag cloud is empty without tags
    mobile_page.tap("#drawer-scrim", position={"x": 370, "y": 400})
    mobile_page.wait_for_timeout(400)
    assert not _sidebar_in_viewport(mobile_page)
    # Escape also closes
    mobile_page.tap("#btn-filters")
    mobile_page.wait_for_timeout(400)
    assert _sidebar_in_viewport(mobile_page)
    mobile_page.keyboard.press("Escape")
    mobile_page.wait_for_timeout(400)
    assert not _sidebar_in_viewport(mobile_page)


def test_library_drawer_resets_on_resize(mobile_page, server_url):
    mobile_page.set_viewport_size({"width": 390, "height": 800})
    mobile_page.goto(f"{server_url}/")
    mobile_page.wait_for_selector("#btn-filters")
    mobile_page.tap("#btn-filters")
    mobile_page.wait_for_timeout(400)
    mobile_page.set_viewport_size({"width": 1280, "height": 800})
    mobile_page.wait_for_timeout(400)
    pos = mobile_page.evaluate(
        "(() => { const s = getComputedStyle(document.querySelector('#sidebar'));"
        " return [s.position, document.querySelector('#sidebar').classList.contains('is-open')]; })()"
    )
    assert pos == ["static", False] or pos == ["relative", False], pos
    assert _sidebar_in_viewport(mobile_page)
    assert not mobile_page.locator("#btn-filters").is_visible()
    assert not mobile_page.locator("#drawer-scrim").is_visible()
