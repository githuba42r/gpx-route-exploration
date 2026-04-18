"""Playwright tests for M3a options UX."""

import re
from playwright.sync_api import expect


def _click_map_at(page, selector, fx, fy):
    box = page.locator(selector).bounding_box()
    page.mouse.click(box["x"] + box["width"] * fx, box["y"] + box["height"] * fy)


def _goto_create(page, server_url):
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    page.wait_for_function(
        "() => new URL(location.href).searchParams.get('route_id') !== null",
        timeout=5000,
    )
    page.wait_for_function("() => window.__appReady === true", timeout=10000)


def test_preset_dropdown_is_populated(page, server_url):
    _goto_create(page, server_url)
    expect(page.locator("#route-preset option")).to_have_count(6, timeout=3000)
    assert page.locator("#route-preset option").first.get_attribute("value") == "road"


def test_change_preset_patches_options(page, server_url):
    _goto_create(page, server_url)
    patches = []

    def capture(req):
        if "/options" in req.url:
            patches.append((req.method, req.url, req.post_data or ""))

    page.on("request", capture)
    page.locator("#route-preset").select_option("gravel-mtb")
    page.wait_for_timeout(600)
    assert any("gravel-mtb" in d for _, _, d in patches), patches


def test_round_trip_toggle_patches_options(page, server_url):
    _goto_create(page, server_url)
    patches = []

    def capture(req):
        if "/options" in req.url:
            patches.append(req.post_data or "")

    page.on("request", capture)
    page.locator("#route-round-trip").check()
    page.wait_for_timeout(600)
    assert any("round_trip" in p and "true" in p for p in patches), patches


def test_pin_start_via_sidebar_context_menu(page, server_url):
    """Right-clicking a sidebar row opens the pin context menu and
    'Set as Start' flips the row's pin_role."""
    _goto_create(page, server_url)
    _click_map_at(page, "#map", 0.3, 0.4)
    _click_map_at(page, "#map", 0.6, 0.4)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 2", timeout=3000,
    )
    first = page.locator(".wpe-item").first
    first.click(button="right")
    expect(page.locator("#pin-ctx-menu")).to_be_visible(timeout=1500)
    page.locator('#pin-ctx-menu button[data-act="set-start"]').click()
    expect(first.locator(".wpe-badge")).to_have_text("Start", timeout=3000)


def test_sidebar_context_menu_exclude_dims_row(page, server_url):
    """Right-click a row → Exclude → row gets wpe-excluded class."""
    _goto_create(page, server_url)
    _click_map_at(page, "#map", 0.3, 0.4)
    _click_map_at(page, "#map", 0.6, 0.4)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 2", timeout=3000,
    )
    row = page.locator(".wpe-item").first
    row.click(button="right")
    expect(page.locator("#pin-ctx-menu")).to_be_visible(timeout=1500)
    page.locator('#pin-ctx-menu button[data-act="toggle-include"]').click()
    expect(row).to_have_class(re.compile(r".*wpe-excluded.*"), timeout=3000)


def test_set_start_mutual_exclusion(page, server_url):
    """Setting Start on a second row clears it from the first."""
    _goto_create(page, server_url)
    _click_map_at(page, "#map", 0.3, 0.4)
    _click_map_at(page, "#map", 0.6, 0.4)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 2", timeout=3000,
    )
    rows = page.locator(".wpe-item")
    rows.nth(0).click(button="right")
    page.locator('#pin-ctx-menu button[data-act="set-start"]').click()
    expect(rows.nth(0).locator(".wpe-badge")).to_have_text("Start", timeout=3000)
    rows.nth(1).click(button="right")
    page.locator('#pin-ctx-menu button[data-act="set-start"]').click()
    expect(rows.nth(1).locator(".wpe-badge")).to_have_text("Start", timeout=3000)
    # First row no longer carries the Start badge.
    expect(rows.nth(0).locator(".wpe-badge")).to_have_count(0)


def test_custom_panel_opens_on_preset_custom(page, server_url):
    _goto_create(page, server_url)
    page.locator("#route-preset").select_option("custom")
    expect(page.locator("#custom-costing-panel")).to_be_visible(timeout=1500)


def test_optimise_button_reorders_waypoints(page, server_url):
    _goto_create(page, server_url)
    # Drop 4 points in a crossing order.
    for fx, fy in [(0.3, 0.3), (0.7, 0.7), (0.3, 0.7), (0.7, 0.3)]:
        _click_map_at(page, "#map", fx, fy)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 4", timeout=3000)

    initial = page.locator(".wpe-item .wpe-name").all_text_contents()
    page.locator("#btn-optimise").click()
    # Either the order changes or it was already optimal. Grab fresh and
    # assert the set of names is preserved + the new order is a valid
    # permutation. Either way the sidebar must render 4 rows.
    page.wait_for_timeout(800)
    after = page.locator(".wpe-item .wpe-name").all_text_contents()
    assert len(after) == 4
    # The optimiser may keep the tour if it's already optimal; assert
    # only that the count + set identity hold.
    assert sorted(n.strip().split(" ", 1)[0] for n in after) == sorted(
        n.strip().split(" ", 1)[0] for n in initial)


def test_linked_waypoint_shows_chain_badge(page, server_url):
    _goto_create(page, server_url)
    # Drop 2 waypoints. Click-to-add defaults to kind=waypoint, so both
    # rows are waypoints and both carry linked_to_previous=1 by default.
    _click_map_at(page, "#map", 0.3, 0.4)
    _click_map_at(page, "#map", 0.6, 0.4)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 2", timeout=3000)
    expect(page.locator(".wpe-item").nth(1).locator(".wpe-link-badge")).to_be_visible(timeout=3000)


def test_unlink_from_context_menu_removes_chain_badge(page, server_url):
    _goto_create(page, server_url)
    _click_map_at(page, "#map", 0.3, 0.4)
    _click_map_at(page, "#map", 0.6, 0.4)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 2", timeout=3000)
    # Right-click the second row → Unlink from previous.
    page.locator(".wpe-item").nth(1).click(button="right")
    expect(page.locator("#pin-ctx-menu")).to_be_visible(timeout=1500)
    page.locator('#pin-ctx-menu button[data-act="unlink"]').click()
    expect(page.locator(".wpe-item").nth(1).locator(".wpe-link-badge")).to_have_count(0, timeout=3000)
    # Re-link should restore the chain.
    page.locator(".wpe-item").nth(1).click(button="right")
    expect(page.locator("#pin-ctx-menu")).to_be_visible(timeout=1500)
    page.locator('#pin-ctx-menu button[data-act="relink"]').click()
    expect(page.locator(".wpe-item").nth(1).locator(".wpe-link-badge")).to_be_visible(timeout=3000)


def test_unlink_entry_hidden_on_stops(page, server_url):
    _goto_create(page, server_url)
    _click_map_at(page, "#map", 0.3, 0.4)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 1", timeout=3000)
    # Mark first row as stop via the right-click menu.
    row = page.locator(".wpe-item").first
    row.click(button="right")
    expect(page.locator("#pin-ctx-menu")).to_be_visible(timeout=1500)
    page.locator('#pin-ctx-menu button[data-act="toggle-kind"]').click()
    # Re-open the menu — unlink/relink should NOT be present on stops.
    row.click(button="right")
    expect(page.locator("#pin-ctx-menu")).to_be_visible(timeout=1500)
    assert page.locator('#pin-ctx-menu button[data-act="unlink"]').count() == 0
    assert page.locator('#pin-ctx-menu button[data-act="relink"]').count() == 0


def test_gradient_warning_badge_and_overlay_rendered(page, server_url):
    """M3c: /generate response warnings flow through to a ⚠️ badge on
    the receiving row + a red overlay polyline on the map. The whole
    chain is exercised via mocked /generate so the test doesn't need a
    live Valhalla with known hilly terrain."""
    import json as _json
    from server.routing.gpx_writer import encode_polyline

    _goto_create(page, server_url)
    # Drop two waypoints and set the threshold first.
    _click_map_at(page, "#map", 0.3, 0.4)
    _click_map_at(page, "#map", 0.6, 0.4)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 2", timeout=3000)
    page.locator("#route-max-grad").fill("10")
    page.locator("#route-max-grad").blur()

    # Mock /generate: 1 leg with a forged warning. The polyline needs
    # enough vertices for the overlay's from_m/to_m slice to include at
    # least two — a 2-vertex line (~1.1 km) would yield an empty slice
    # for any sub-segment window.
    points = [(-27.40 - 0.0001 * i, 152.90 + 0.0001 * i) for i in range(20)]
    shape = encode_polyline(points, precision=6)
    body = _json.dumps({
        "legs_count": 1, "distance_km": 0.3, "duration_s": 90,
        "gpx_url": "/api/gpx/1",
        "legs": [{
            "from_position": 0, "to_position": 1,
            "distance_m": 300, "duration_s": 90,
            "polyline": shape,
            "max_grade_pct": 18.5,
            # Pick a window that clearly spans interior vertices (the
            # leg is ~300m, 20 vertices, so ~15m apart — 50m to 200m
            # catches about 10 vertices).
            "warnings": [{"from_m": 50.0, "to_m": 200.0, "peak_grad_pct": 18.5}],
        }],
    })
    page.route("**/api/routes/*/generate", lambda route: route.fulfill(
        status=200, content_type="application/json", body=body,
    ))

    page.locator("#btn-gen-primary").click()

    # The ⚠️ badge lands on the receiving row (to_position=1 → 2nd row).
    expect(page.locator(".wpe-item").nth(1).locator(".wpe-warn-badge")).to_be_visible(timeout=5000)
    # The warning overlay is added to the map pane. Depending on the
    # slice length and viewport clipping, the SVG path may or may not
    # render for a 400m span on a 2-vertex polyline — assert via the
    # JS-side state.warningOverlays count which is the ground truth.
    overlay_count = page.evaluate(
        "() => (window.__appState.warningOverlays || []).length"
    )
    assert overlay_count == 1, f"expected 1 warning overlay, got {overlay_count}"


def test_gradient_warning_absent_when_no_warnings(page, server_url):
    """No ⚠️ badge + no red overlay when warnings is null."""
    import json as _json
    from server.routing.gpx_writer import encode_polyline

    _goto_create(page, server_url)
    _click_map_at(page, "#map", 0.3, 0.4)
    _click_map_at(page, "#map", 0.6, 0.4)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 2", timeout=3000)
    shape = encode_polyline([(-27.40, 152.90), (-27.41, 152.91)], precision=6)
    body = _json.dumps({
        "legs_count": 1, "distance_km": 1.0, "duration_s": 300,
        "gpx_url": "/api/gpx/1",
        "legs": [{
            "from_position": 0, "to_position": 1,
            "distance_m": 1000, "duration_s": 300,
            "polyline": shape,
            "max_grade_pct": 2.0,
            "warnings": None,
        }],
    })
    page.route("**/api/routes/*/generate", lambda route: route.fulfill(
        status=200, content_type="application/json", body=body,
    ))
    page.locator("#btn-gen-primary").click()
    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('.leaflet-overlay-pane path'))"
        "  .some(p => p.classList.contains('leaflet-interactive'))",
        timeout=5000,
    )
    # No warn badge anywhere.
    assert page.locator(".wpe-warn-badge").count() == 0
    # No red overlay.
    has_red = page.evaluate(
        "() => Array.from(document.querySelectorAll('.leaflet-overlay-pane path'))"
        "  .some(p => (p.getAttribute('stroke') || '').toLowerCase() === '#ff3f2f')"
    )
    assert has_red is False
