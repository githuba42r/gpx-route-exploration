"""Playwright E2E for the Edit Route navigation flow.

The original M2 shipped an inline slide-out edit panel on the Analysis
page. That UX combined analysis + edit on one screen which users found
confusing, so we pivoted: the Analysis page now links out to the Create
page (which serves as the editor), and the Create page links back to
Analysis. A dirty-state guard warns before navigating away with
unsaved/unregenerated recipe edits.
"""

import os
import requests as http_requests
from playwright.sync_api import expect

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _create_recipe_route(server_url, n_waypoints=2):
    """Create a route that has BOTH a GPX file on disk AND a recipe.

    Analysis page needs a readable GPX at /api/gpx/<id>; the Edit Route
    link only goes to the editor when route_waypoints has rows.
    """
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
        data={"title": "Nav flow test"},
    )
    rid = r.json()["id"]
    for i in range(n_waypoints):
        http_requests.post(
            f"{server_url}/api/routes/{rid}/waypoints",
            json={
                "name": f"WP{i}",
                "lat": -27.40 - i * 0.01,
                "lon": 152.90 + i * 0.01,
                "kind": "stop",
            },
        )
    return rid


def _upload_gpx_only_route(server_url, title="legacy-gpx"):
    """Upload a plain GPX file — no recipe created."""
    gpx = (
        b'<?xml version="1.0"?><gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">'
        b'<trk><trkseg>'
        b'<trkpt lat="-27.4" lon="152.9"><ele>10</ele></trkpt>'
        b'<trkpt lat="-27.41" lon="152.91"><ele>11</ele></trkpt>'
        b'</trkseg></trk></gpx>'
    )
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
    """Legacy GPX uploads (no recipe) render a disabled placeholder button
    with an M6-hinting tooltip. Nothing to navigate to."""
    rid = _upload_gpx_only_route(server_url)
    _open_analysis(page, server_url, rid)
    btn = page.locator("#btn-open-edit")
    expect(btn).to_be_disabled()
    title = btn.get_attribute("title") or ""
    assert "no recipe" in title.lower()


def test_edit_button_links_to_create_for_recipe_route(page, server_url):
    """Recipe-backed routes show an <a href='/create?route_id=N'> link."""
    rid = _create_recipe_route(server_url)
    _open_analysis(page, server_url, rid)
    link = page.locator("a#btn-open-edit")
    expect(link).to_be_visible()
    href = link.get_attribute("href")
    assert href == f"/create?route_id={rid}", f"unexpected href: {href!r}"


def test_click_edit_navigates_to_create_page(page, server_url):
    """Clicking Edit Route takes the user to the Create page in edit mode
    (route_id in the URL)."""
    rid = _create_recipe_route(server_url)
    _open_analysis(page, server_url, rid)
    page.locator("a#btn-open-edit").click()
    page.wait_for_url(f"**/create?route_id={rid}", timeout=5000)
    expect(page.locator("#editor-panel")).to_be_visible(timeout=5000)


def test_create_page_shows_analysis_button_when_editing_existing_route(page, server_url):
    """When Create loads with ?route_id=<id>, a 'Route Analysis' nav link
    appears pointing back to /route/<id>."""
    rid = _create_recipe_route(server_url)
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create?route_id={rid}")
    btn = page.locator("a#btn-open-analysis")
    expect(btn).to_be_visible(timeout=5000)
    href = btn.get_attribute("href")
    assert href == f"/route/{rid}", f"unexpected href: {href!r}"


def test_create_page_hides_analysis_button_on_fresh_new_route(page, server_url):
    """Hitting /create without a route_id creates a fresh recipe route —
    the Analysis button stays hidden since there's nothing to analyse yet."""
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    page.wait_for_function(
        "() => new URL(location.href).searchParams.get('route_id') !== null",
        timeout=5000,
    )
    expect(page.locator("a#btn-open-analysis")).to_be_hidden()


def test_dirty_state_prompts_before_library_nav(page, server_url):
    """Editing a recipe after the initial generate puts the page in
    'dirty' state; clicking the Library link fires a window.confirm()."""
    rid = _create_recipe_route(server_url, n_waypoints=2)
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create?route_id={rid}")

    # Wait for the page to be fully interactive — this guarantees the
    # Library-link click handler has been attached.
    page.wait_for_function("() => window.__appReady === true", timeout=10000)

    # Force the page into the dirty state. Simpler than scripting a real
    # edit + regenerate cycle: set the counters the guard reads.
    page.evaluate(
        """() => {
            if (!window.__appState) throw new Error('state not exposed');
            window.__appState.generatedVersion = 0;
            window.__appState.currentVersion = 1;
        }"""
    )

    dialog_messages = []

    def _handle(dialog):
        dialog_messages.append(dialog.message)
        dialog.dismiss()  # Cancel: leave without regenerating.

    page.on("dialog", _handle)

    page.locator('a[href="/"]').first.click()
    page.wait_for_timeout(400)

    assert dialog_messages, (
        "expected a confirm() dialog to appear when navigating away with "
        "unregenerated edits, got none"
    )
    assert "regenerat" in dialog_messages[0].lower(), dialog_messages[0]


def test_analysis_link_from_editor_navigates_back(page, server_url):
    """With route_id in the URL, clicking the Analysis nav link returns
    the user to /route/<id> (no dirty edits = no prompt)."""
    rid = _create_recipe_route(server_url)
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create?route_id={rid}")
    expect(page.locator("a#btn-open-analysis")).to_be_visible(timeout=5000)
    page.locator("a#btn-open-analysis").click()
    page.wait_for_url(f"**/route/{rid}", timeout=5000)
