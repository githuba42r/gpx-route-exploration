"""M8 Task 5: Create page bookmark picker."""

import pytest
import requests as http_requests
from playwright.sync_api import expect

CENTRE = (-27.4705, 153.026)


@pytest.fixture(autouse=True)
def clean_bookmarks(server_url):
    def wipe():
        for b in http_requests.get(f"{server_url}/api/bookmarks").json():
            http_requests.delete(f"{server_url}/api/bookmarks/{b['id']}")
    wipe()
    yield
    wipe()


@pytest.fixture
def mobile_page(playwright):
    browser = playwright.chromium.launch()
    context = browser.new_context(
        viewport={"width": 390, "height": 844}, device_scale_factor=2,
        is_mobile=True, has_touch=True,
    )
    page = context.new_page()
    yield page
    context.close()
    browser.close()


def seed(server_url, name, lat=CENTRE[0], lon=CENTRE[1], tags=None, description=""):
    r = http_requests.post(
        f"{server_url}/api/bookmarks",
        json={"name": name, "lat": lat, "lon": lon, "description": description,
              "tags": tags or []},
    )
    assert r.status_code == 201, r.text
    return r.json()


def make_route(server_url, n=0):
    rid = http_requests.post(f"{server_url}/api/routes",
                             json={"title": "Picker", "profile": "bicycle"}).json()["id"]
    for i in range(n):
        r = http_requests.post(
            f"{server_url}/api/routes/{rid}/waypoints",
            json={"name": f"W{i}", "lat": CENTRE[0] + i * 0.01, "lon": CENTRE[1], "kind": "waypoint"})
        assert r.status_code == 201, r.text
    return rid


def order(server_url, rid):
    return [w["name"] for w in http_requests.get(f"{server_url}/api/routes/{rid}/waypoints").json()]


def open_create(page, server_url, rid, w=1280, h=900):
    page.set_viewport_size({"width": w, "height": h})
    page.goto(f"{server_url}/create?route_id={rid}")
    page.wait_for_function("() => window.__appState && window.__appState.map")
    page.wait_for_timeout(300)


def open_picker(page):
    page.locator("#btn-bookmarks").click()
    expect(page.locator("#bookmark-picker")).to_be_visible()
    expect(page.locator("#btn-bookmarks")).to_have_attribute("aria-expanded", "true")


def rows(page):
    return page.locator("#bookmark-picker .bp-row")


def test_opens_and_lists_nearest_first(page, server_url):
    seed(server_url, "Far", lat=-28.5, lon=153.5)
    seed(server_url, "Mid", lat=-27.6, lon=153.1)
    seed(server_url, "Near", lat=-27.4706, lon=153.0261)
    rid = make_route(server_url)
    open_create(page, server_url, rid)
    open_picker(page)
    expect(rows(page)).to_have_count(3)
    names = [t.strip() for t in page.locator("#bookmark-picker .bp-name").all_text_contents()]
    assert names == ["Near", "Mid", "Far"]
    expect(page.locator("#bookmark-picker .bp-dist").first).not_to_be_empty()
    page.locator("#btn-bookmarks").click()
    expect(page.locator("#bookmark-picker")).to_be_hidden()
    expect(page.locator("#btn-bookmarks")).to_have_attribute("aria-expanded", "false")


def test_search_and_tag_filter(page, server_url):
    seed(server_url, "Cafe One", tags=["food"], description="flat white")
    seed(server_url, "Lookout", tags=["view"], description="great panorama")
    seed(server_url, "Bakery", tags=["food", "view"])
    rid = make_route(server_url)
    open_create(page, server_url, rid)
    open_picker(page)
    search = page.locator("#bookmark-picker .bp-search")
    search.fill("cafe")
    expect(rows(page)).to_have_count(1)
    search.fill("panorama")
    expect(rows(page)).to_have_count(1)
    search.fill("")
    expect(rows(page)).to_have_count(3)
    page.locator("#bookmark-picker .bp-tag", has_text="food").click()
    expect(rows(page)).to_have_count(2)
    page.locator("#bookmark-picker .bp-tag", has_text="view").click()
    expect(rows(page)).to_have_count(1)
    search.fill("zzzz")
    expect(rows(page)).to_have_count(0)
    expect(page.locator("#bookmark-picker .bp-none")).to_be_visible()


def test_pick_appends_waypoint_marker_and_needs_regen(page, server_url):
    seed(server_url, "Pub", lat=-27.48, lon=153.03, description="d")
    rid = make_route(server_url, 2)
    open_create(page, server_url, rid)
    markers_before = page.locator(".leaflet-marker-icon").count()
    v_before = page.evaluate("window.__appState.currentVersion")
    open_picker(page)
    rows(page).first.click()
    expect(page.locator("#bookmark-picker")).to_be_hidden()
    expect(page.locator(".wpe-item")).to_have_count(3)
    assert page.locator(".leaflet-marker-icon").count() == markers_before + 1
    assert order(server_url, rid) == ["W0", "W1", "Pub"]
    st = page.evaluate("[window.__appState.currentVersion, window.__appState.generatedVersion]")
    assert st[0] > v_before and st[0] != st[1]


def test_insert_select_forwards_position(page, server_url):
    seed(server_url, "Pub")
    rid = make_route(server_url, 3)
    open_create(page, server_url, rid)
    open_picker(page)
    sel = page.locator("#bookmark-picker .bp-insert")
    labels = sel.locator("option").all_text_contents()
    assert labels[0] == "At end of route"
    assert labels[1:] == ["After W0", "After W1", "After W2"]
    sel.select_option(label="After W0")
    rows(page).first.click()
    expect(page.locator(".wpe-item")).to_have_count(4)
    assert order(server_url, rid) == ["W0", "Pub", "W1", "W2"]
    positions = [w["position"] for w in
                 http_requests.get(f"{server_url}/api/routes/{rid}/waypoints").json()]
    assert positions == sorted(positions) and len(set(positions)) == 4


def test_double_click_adds_exactly_one(page, server_url):
    seed(server_url, "Pub")
    rid = make_route(server_url, 1)
    open_create(page, server_url, rid)
    posts = []
    page.on("request", lambda r: posts.append(r.url) if r.method == "POST" and "from-bookmark" in r.url else None)
    open_picker(page)
    rows(page).first.dblclick()
    page.wait_for_timeout(600)
    assert len(posts) == 1
    assert order(server_url, rid) == ["W0", "Pub"]


def test_escape_and_outside_click_close(page, server_url):
    seed(server_url, "Pub")
    rid = make_route(server_url)
    open_create(page, server_url, rid)
    open_picker(page)
    page.keyboard.press("Escape")
    expect(page.locator("#bookmark-picker")).to_be_hidden()
    assert page.evaluate("document.activeElement.id") == "btn-bookmarks"
    open_picker(page)
    page.locator("#route-title").click()
    expect(page.locator("#bookmark-picker")).to_be_hidden()


def test_empty_state_links_to_library(page, server_url):
    rid = make_route(server_url)
    open_create(page, server_url, rid)
    open_picker(page)
    link = page.locator("#bookmark-picker .bp-empty a")
    expect(link).to_be_visible()
    assert link.get_attribute("href") == "/#bookmarks"


def test_list_refetched_each_open(page, server_url):
    rid = make_route(server_url)
    open_create(page, server_url, rid)
    open_picker(page)
    expect(rows(page)).to_have_count(0)
    page.keyboard.press("Escape")
    seed(server_url, "Later")
    open_picker(page)
    expect(rows(page)).to_have_count(1)


def test_xss_rendered_as_text(page, server_url):
    evil = "<img src=x onerror=window.__pwn=1>"
    seed(server_url, evil, tags=["<b>t</b>"], description=evil)
    rid = make_route(server_url)
    open_create(page, server_url, rid)
    open_picker(page)
    expect(page.locator("#bookmark-picker .bp-name").first).to_have_text(evil)
    assert page.evaluate("window.__pwn") is None
    assert page.locator("#bookmark-picker b").count() == 0
    assert page.locator("#bookmark-picker .bp-row img[src='x']").count() == 0


def test_error_inline_and_stays_open(page, server_url):
    seed(server_url, "Pub")
    rid = make_route(server_url, 1)
    open_create(page, server_url, rid)
    page.route("**/waypoints/from-bookmark", lambda r: r.fulfill(status=500, body="x"))
    open_picker(page)
    rows(page).first.click()
    expect(page.locator("#bookmark-picker .bp-error")).to_have_text("Could not add bookmark")
    expect(page.locator("#bookmark-picker")).to_be_visible()
    assert order(server_url, rid) == ["W0"]
    expect(rows(page).first).to_be_enabled()


def test_mobile_panel_fits_rows_44_no_hscroll(mobile_page, server_url):
    for i in range(4):
        seed(server_url, f"Place {i}", lat=CENTRE[0] + i * 0.01, tags=["t"])
    rid = make_route(server_url, 2)
    open_create(mobile_page, server_url, rid, w=360, h=740)
    btn = mobile_page.locator("#btn-bookmarks")
    expect(btn).to_be_visible()
    assert btn.bounding_box()["height"] >= 44
    open_picker(mobile_page)
    box = mobile_page.locator("#bookmark-picker").bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= 360 + 0.5
    assert box["width"] >= 340
    assert box["y"] + box["height"] <= 740 + 0.5
    for r in rows(mobile_page).all():
        assert r.bounding_box()["height"] >= 44
    assert mobile_page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    # on top of the bottom sheet
    top = mobile_page.evaluate(
        """() => { const b = document.getElementById('bookmark-picker').getBoundingClientRect();
        const e = document.elementFromPoint(b.x + b.width / 2, b.y + b.height - 6);
        return !!e && !!e.closest('#bookmark-picker'); }""")
    assert top
    rows(mobile_page).first.click()
    expect(mobile_page.locator(".wpe-item")).to_have_count(3)


def test_opening_one_closes_the_other(page, server_url):
    seed(server_url, "Pub")
    rid = make_route(server_url)
    open_create(page, server_url, rid)
    page.route("**/api/geocode/search*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body='[{"display_name":"Queen St","lat":"-36.8","lon":"174.7"}]'))
    page.locator("#add-address").fill("Queen Street")
    expect(page.locator("#address-suggestions li")).to_have_count(1)
    open_picker(page)
    expect(page.locator("#address-suggestions li")).to_have_count(0)
    page.locator("#add-address").fill("Queen Stree")
    expect(page.locator("#address-suggestions li")).to_have_count(1)
    expect(page.locator("#bookmark-picker")).to_be_hidden()
