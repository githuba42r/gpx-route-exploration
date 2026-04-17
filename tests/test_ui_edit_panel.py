"""Playwright E2E for the M2 inline Edit panel on the Analysis page."""

import os
import requests as http_requests
from playwright.sync_api import expect

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _create_recipe_route(server_url, n_waypoints=2):
    """Create a route that has BOTH a GPX file on disk AND a recipe.

    The Analysis page needs a GPX file at /api/gpx/<id> to render; the Edit
    button only enables when route_waypoints has rows. The test-space trick
    is to upload a real GPX file first (so the GPX endpoint serves it) and
    then POST waypoints to populate the recipe.
    """
    gpx = (b'<?xml version="1.0"?><gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">'
           b'<metadata><name>M2 test</name></metadata>'
           b'<trk><trkseg><trkpt lat="-27.4" lon="152.9"><ele>10</ele></trkpt>'
           b'<trkpt lat="-27.41" lon="152.91"><ele>11</ele></trkpt>'
           b'<trkpt lat="-27.42" lon="152.92"><ele>12</ele></trkpt></trkseg></trk></gpx>')
    r = http_requests.post(
        f"{server_url}/api/routes",
        files={"file": ("m2.gpx", gpx)},
        data={"title": "M2 test"},
    )
    rid = r.json()["id"]
    for i in range(n_waypoints):
        http_requests.post(
            f"{server_url}/api/routes/{rid}/waypoints",
            json={"name": f"WP{i}", "lat": -27.40 - i * 0.01, "lon": 152.90 + i * 0.01,
                  "kind": "stop"},
        )
    return rid


def _upload_gpx_only_route(server_url, title="legacy-gpx"):
    """Upload a plain GPX file — no recipe created."""
    gpx = (b'<?xml version="1.0"?><gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">'
           b'<trk><trkseg><trkpt lat="-27.4" lon="152.9"><ele>10</ele></trkpt>'
           b'<trkpt lat="-27.41" lon="152.91"><ele>11</ele></trkpt></trkseg></trk></gpx>')
    r = http_requests.post(
        f"{server_url}/api/routes",
        files={"file": ("legacy.gpx", gpx)},
        data={"title": title},
    )
    return r.json()["id"]


def _open_analysis(page, server_url, route_id):
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/route/{route_id}")
    expect(page.locator("#btn-open-edit")).to_be_visible(timeout=10000)


def test_edit_button_disabled_for_gpx_only_route(page, server_url):
    """Legacy GPX uploads (no recipe) render the Edit button disabled with
    an M6-hinting tooltip."""
    rid = _upload_gpx_only_route(server_url)
    _open_analysis(page, server_url, rid)
    btn = page.locator("#btn-open-edit")
    expect(btn).to_be_disabled()
    title = btn.get_attribute("title")
    assert title and "no recipe" in title.lower()


def test_edit_button_enabled_for_recipe_route(page, server_url):
    rid = _create_recipe_route(server_url)
    _open_analysis(page, server_url, rid)
    expect(page.locator("#btn-open-edit")).to_be_enabled()


def test_click_edit_opens_panel_with_current_waypoints(page, server_url):
    """Clicking Edit reveals the slide-out; waypoints in the sidebar match
    the recipe."""
    rid = _create_recipe_route(server_url, n_waypoints=2)
    _open_analysis(page, server_url, rid)
    page.locator("#btn-open-edit").click()
    expect(page.locator("#edit-panel-overlay")).to_have_class("open", timeout=2000)
    expect(page.locator(".wpe-item")).to_have_count(2)


def test_close_button_dismisses_panel(page, server_url):
    rid = _create_recipe_route(server_url)
    _open_analysis(page, server_url, rid)
    page.locator("#btn-open-edit").click()
    expect(page.locator("#edit-panel-overlay")).to_have_class("open")
    page.locator("#btn-close-edit").click()
    # open class is dropped and overlay becomes display:none.
    expect(page.locator("#edit-panel-overlay")).not_to_have_class("open")


def test_add_waypoint_via_map_click_inside_panel(page, server_url):
    """With the panel open, clicking on the map appends a waypoint and
    flips the status chip to 'Edits pending'."""
    rid = _create_recipe_route(server_url, n_waypoints=2)
    _open_analysis(page, server_url, rid)
    page.locator("#btn-open-edit").click()
    expect(page.locator(".wpe-item")).to_have_count(2)
    # Click somewhere on the map (left side so we miss any sidebar overlay).
    box = page.locator("#map").bounding_box()
    page.mouse.click(box["x"] + 0.2 * box["width"], box["y"] + 0.5 * box["height"])
    expect(page.locator(".wpe-item")).to_have_count(3, timeout=5000)
    expect(page.locator("#edit-panel-status")).to_contain_text("Edits pending")


def test_regenerate_button_calls_generate_and_reloads(page, server_url):
    """Clicking Regenerate hits /generate and then reloads the page. We
    mock /generate so the test is deterministic regardless of Valhalla."""
    rid = _create_recipe_route(server_url, n_waypoints=2)
    _open_analysis(page, server_url, rid)
    page.locator("#btn-open-edit").click()

    valid_polyline = '~rjgs@_ygsbH~oR_pR'
    page.route(f"**/api/routes/{rid}/generate", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=(f'{{"legs_count":1,"distance_km":0.5,"duration_s":120,'
              f'"gpx_url":"/api/gpx/{rid}",'
              f'"legs":[{{"from_position":0,"to_position":1,"distance_m":500,'
              f'"duration_s":120,"polyline":"{valid_polyline}"}}]}}'),
    ))

    with page.expect_navigation(timeout=10000):
        page.locator("#btn-regen-edit").click()

    # After reload, we're back on the analysis page.
    expect(page.locator("#btn-open-edit")).to_be_visible(timeout=10000)
