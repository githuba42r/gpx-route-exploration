"""M8 Task 6: 'Save as bookmark' in the Create pin menu and Analysis marker menu, plus toast."""

import pytest
import requests as http_requests
from playwright.sync_api import expect

GPX = (
    b'<?xml version="1.0"?><gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">'
    b'<metadata><name>t</name></metadata><trk><trkseg>'
    b'<trkpt lat="-27.4" lon="152.9"><ele>10</ele></trkpt>'
    b'<trkpt lat="-27.41" lon="152.91"><ele>11</ele></trkpt>'
    b'<trkpt lat="-27.42" lon="152.92"><ele>12</ele></trkpt>'
    b'</trkseg></trk></gpx>'
)
HOSTILE = "<img src=x onerror=window.__pwn=1>"


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
    context = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                                  is_mobile=True, has_touch=True)
    page = context.new_page()
    yield page
    context.close()
    browser.close()


def bookmarks(server_url):
    return http_requests.get(f"{server_url}/api/bookmarks").json()


def make_route(server_url, names=("Cafe",), kind="stop", description="Good coffee", gpx=False):
    if gpx:
        rid = http_requests.post(f"{server_url}/api/routes", files={"file": ("r.gpx", GPX)},
                                 data={"title": "Save test"}).json()["id"]
    else:
        rid = http_requests.post(f"{server_url}/api/routes",
                                 json={"title": "Save test", "profile": "bicycle"}).json()["id"]
    for i, n in enumerate(names):
        r = http_requests.post(f"{server_url}/api/routes/{rid}/waypoints",
                               json={"name": n, "lat": -27.40 - i * 0.01, "lon": 152.90 + i * 0.01,
                                     "kind": kind, "description": description})
        assert r.status_code == 201, r.text
    return rid


def open_create(page, server_url, rid):
    page.goto(f"{server_url}/create?route_id={rid}")
    page.wait_for_selector(".wpe-marker", timeout=5000)
    page.wait_for_timeout(500)


def pin_menu_save(page):
    page.locator(".wpe-marker").first.click(button="right")
    menu = page.locator("#pin-ctx-menu")
    expect(menu).to_be_visible()
    return menu.locator("button[data-act='save-bookmark']")


def test_create_save_bookmark_toast_and_api(page, server_url):
    rid = make_route(server_url)
    open_create(page, server_url, rid)
    btn = pin_menu_save(page)
    expect(btn).to_have_text("Save as bookmark")
    btn.click()
    toast = page.locator(".app-toast")
    expect(toast).to_contain_text("Saved to bookmarks")
    expect(page.locator("#pin-ctx-menu")).to_be_hidden()
    assert toast.get_attribute("aria-live") == "polite"
    assert toast.get_attribute("role") == "status"
    link = toast.locator("a")
    assert link.get_attribute("href") == "/#bookmarks"
    assert link.inner_text() == "View"
    bms = bookmarks(server_url)
    assert len(bms) == 1
    b = bms[0]
    assert (b["name"], b["description"]) == ("Cafe", "Good coffee")
    assert abs(b["lat"] - -27.40) < 1e-6 and abs(b["lon"] - 152.90) < 1e-6


def test_create_menu_entry_on_plain_waypoint_too(page, server_url):
    rid = make_route(server_url, kind="waypoint", description="")
    open_create(page, server_url, rid)
    expect(pin_menu_save(page)).to_be_visible()


def test_create_double_click_posts_once(page, server_url):
    rid = make_route(server_url)
    open_create(page, server_url, rid)
    posts = []
    page.on("request", lambda r: posts.append(r.url) if r.method == "POST" and "/api/bookmarks" in r.url else None)
    btn = pin_menu_save(page)
    btn.evaluate("b => { b.click(); b.click(); }")
    expect(page.locator(".app-toast")).to_contain_text("Saved to bookmarks")
    page.wait_for_timeout(300)
    assert len(posts) == 1, posts
    assert len(bookmarks(server_url)) == 1


def test_toast_link_opens_library_bookmarks_tab(page, server_url):
    rid = make_route(server_url)
    open_create(page, server_url, rid)
    pin_menu_save(page).click()
    page.locator(".app-toast a").click()
    page.wait_for_url("**/#bookmarks")
    expect(page.locator("body")).to_contain_text("Cafe")


def test_toast_replaced_not_stacked_and_auto_dismisses(page, server_url):
    rid = make_route(server_url)
    open_create(page, server_url, rid)
    pin_menu_save(page).click()
    expect(page.locator(".app-toast")).to_have_count(1)
    first = page.locator(".app-toast").element_handle()
    pin_menu_save(page).click()
    page.wait_for_function("el => !el.isConnected", arg=first, timeout=3000)
    expect(page.locator(".app-toast")).to_have_count(1)
    page.wait_for_timeout(5600)
    expect(page.locator(".app-toast")).to_have_count(0)


def test_toast_close_button(page, server_url):
    rid = make_route(server_url)
    open_create(page, server_url, rid)
    pin_menu_save(page).click()
    page.locator(".app-toast-close").click()
    expect(page.locator(".app-toast")).to_have_count(0)


def test_create_failure_shows_server_error_in_toast(page, server_url):
    rid = make_route(server_url)
    open_create(page, server_url, rid)
    page.route("**/api/bookmarks/from-waypoint/*", lambda r: r.fulfill(
        status=404, content_type="application/json", body='{"error": "Not found"}'))
    pin_menu_save(page).click()
    toast = page.locator(".app-toast")
    expect(toast).to_contain_text("Not found")
    expect(toast.locator("a")).to_have_count(0)
    assert bookmarks(server_url) == []


def test_hostile_name_is_inert_in_toast_and_library(page, server_url):
    rid = make_route(server_url, names=(HOSTILE,), description="<b>x</b>")
    open_create(page, server_url, rid)
    pin_menu_save(page).click()
    expect(page.locator(".app-toast")).to_contain_text("Saved to bookmarks")
    assert bookmarks(server_url)[0]["name"] == HOSTILE
    page.goto(f"{server_url}/#bookmarks")
    page.wait_for_timeout(1200)
    assert page.evaluate("window.__pwn") is None
    assert page.locator("img[src='x']").count() == 0


def test_toast_above_pin_menu_and_sheet_on_mobile(mobile_page, server_url):
    rid = make_route(server_url)
    page = mobile_page
    open_create(page, server_url, rid)
    page.locator(".wpe-marker").first.dispatch_event("contextmenu")
    page.locator("#pin-ctx-menu button[data-act='save-bookmark']").tap()
    toast = page.locator(".app-toast")
    expect(toast).to_be_visible()
    b = toast.bounding_box()
    x, y = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
    assert page.evaluate("([x, y]) => !!document.elementFromPoint(x, y).closest('.app-toast')", [x, y])
    assert b["x"] >= 0 and b["x"] + b["width"] <= 390
    z = page.evaluate("getComputedStyle(document.querySelector('.app-toast')).zIndex")
    assert int(z) > 3000


# --- Analysis page ---

def goto_analysis(page, server_url, rid):
    page.goto(f"{server_url}/route/{rid}")
    page.wait_for_selector("#map .leaflet-tile-container", state="attached")
    page.wait_for_timeout(800)


def add_marker(page, label, frac=(0.5, 0.5)):
    box = page.locator("#map").bounding_box()
    page.mouse.click(box["x"] + box["width"] * frac[0], box["y"] + box["height"] * frac[1],
                     button="right")
    page.once("dialog", lambda d: d.accept(label))
    page.locator("#ctx-add-waypoint").click()
    page.wait_for_timeout(300)


def test_analysis_save_bookmark_from_marker(page, server_url):
    rid = make_route(server_url, names=(), gpx=True)
    goto_analysis(page, server_url, rid)
    add_marker(page, "Lookout")
    page.locator(".waypoint-icon").first.click(button="right")
    item = page.locator("#ctx-save-bookmark")
    expect(item).to_be_visible()
    item.click()
    toast = page.locator(".app-toast")
    expect(toast).to_contain_text("Saved to bookmarks")
    assert toast.locator("a").get_attribute("href") == "/#bookmarks"
    bms = bookmarks(server_url)
    assert len(bms) == 1 and bms[0]["name"] == "Lookout"
    assert -90 < bms[0]["lat"] < 90


def test_analysis_entry_absent_on_plain_map_click_and_double_click_once(page, server_url):
    rid = make_route(server_url, names=(), gpx=True)
    goto_analysis(page, server_url, rid)
    box = page.locator("#map").bounding_box()
    page.mouse.click(box["x"] + box["width"] * 0.3, box["y"] + box["height"] * 0.3, button="right")
    expect(page.locator("#ctx-menu")).to_be_visible()
    expect(page.locator("#ctx-save-bookmark")).to_be_hidden()
    page.keyboard.press("Escape")
    page.mouse.click(5, 5)
    add_marker(page, "")
    posts = []
    page.on("request", lambda r: posts.append(r.url) if r.method == "POST" and "/api/bookmarks" in r.url else None)
    page.locator(".waypoint-icon").first.click(button="right")
    page.locator("#ctx-save-bookmark").evaluate("b => { b.click(); b.click(); }")
    expect(page.locator(".app-toast")).to_contain_text("Saved to bookmarks")
    page.wait_for_timeout(300)
    assert len(posts) == 1
    bms = bookmarks(server_url)
    assert len(bms) == 1 and bms[0]["name"] == "Waypoint"  # empty label falls back


def test_analysis_hostile_label_inert(page, server_url):
    rid = make_route(server_url, names=(), gpx=True)
    goto_analysis(page, server_url, rid)
    add_marker(page, HOSTILE)
    page.locator(".waypoint-icon").first.click(button="right")
    page.locator("#ctx-save-bookmark").click()
    expect(page.locator(".app-toast")).to_contain_text("Saved to bookmarks")
    assert bookmarks(server_url)[0]["name"] == HOSTILE
    assert page.evaluate("window.__pwn") is None


# --- Touch ---

def hold(page, x, y, ms=700):
    cdp = page.context.new_cdp_session(page)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
    page.wait_for_timeout(ms)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    cdp.detach()
    page.wait_for_timeout(500)


def test_long_press_create_marker_entry_tall_enough_and_saves(mobile_page, server_url):
    rid = make_route(server_url)
    page = mobile_page
    open_create(page, server_url, rid)
    b = page.locator(".wpe-marker").first.bounding_box()
    hold(page, b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
    btn = page.locator("#pin-ctx-menu button[data-act='save-bookmark']")
    expect(btn).to_be_visible()
    assert btn.bounding_box()["height"] >= 44
    btn.tap()
    expect(page.locator(".app-toast")).to_contain_text("Saved to bookmarks")
    assert len(bookmarks(server_url)) == 1


def test_long_press_analysis_marker_entry_tall_enough(mobile_page, server_url):
    rid = make_route(server_url, names=(), gpx=True)
    page = mobile_page
    goto_analysis(page, server_url, rid)
    box = page.locator("#map").bounding_box()
    hold(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.once("dialog", lambda d: d.accept("Phone"))
    page.locator("#ctx-add-waypoint").tap()
    page.wait_for_timeout(500)
    mb = page.locator(".waypoint-icon").bounding_box()
    hold(page, mb["x"] + mb["width"] / 2, mb["y"] + mb["height"] / 2)
    item = page.locator("#ctx-save-bookmark")
    expect(item).to_be_visible()
    assert item.bounding_box()["height"] >= 44
    item.tap()
    expect(page.locator(".app-toast")).to_contain_text("Saved to bookmarks")
    assert bookmarks(server_url)[0]["name"] == "Phone"
