"""Playwright E2E tests for the Create Route page."""

from playwright.sync_api import expect


def _click_map_at(page, selector, x_frac, y_frac):
    box = page.locator(selector).bounding_box()
    assert box
    page.mouse.click(box["x"] + x_frac * box["width"], box["y"] + y_frac * box["height"])


def test_create_page_loads(page, server_url):
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    expect(page.locator("#map")).to_be_visible()
    expect(page.locator("#editor-panel")).to_be_visible()
    page.wait_for_function(
        "() => new URL(location.href).searchParams.get('route_id') !== null",
        timeout=5000,
    )


def test_click_map_adds_waypoint(page, server_url):
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    page.wait_for_function(
        "() => new URL(location.href).searchParams.get('route_id') !== null")
    _click_map_at(page, "#map", 0.3, 0.4)
    expect(page.locator(".wpe-item").first).to_be_visible(timeout=3000)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 1",
        timeout=3000,
    )


def test_add_three_waypoints_and_remove_one(page, server_url):
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    page.wait_for_function(
        "() => new URL(location.href).searchParams.get('route_id') !== null")
    _click_map_at(page, "#map", 0.25, 0.4)
    _click_map_at(page, "#map", 0.5, 0.4)
    _click_map_at(page, "#map", 0.75, 0.4)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 3",
        timeout=5000,
    )
    page.locator(".wpe-item").nth(1).locator(".wpe-remove").click()
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 2",
        timeout=3000,
    )


def test_marker_right_click_toggles_kind(page, server_url):
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    page.wait_for_function(
        "() => new URL(location.href).searchParams.get('route_id') !== null")
    _click_map_at(page, "#map", 0.3, 0.4)
    page.wait_for_selector(".wpe-item-waypoint", timeout=3000)
    page.locator(".wpe-marker.wpe-waypoint").first.click(button="right")
    page.wait_for_selector(".wpe-item-stop", timeout=3000)


def test_drag_reorder_waypoints(page, server_url):
    """Drag the second sidebar row above the first; verify the PUT reorder
    API landed and the list order swapped."""
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    page.wait_for_function(
        "() => new URL(location.href).searchParams.get('route_id') !== null")
    _click_map_at(page, "#map", 0.25, 0.4)
    _click_map_at(page, "#map", 0.5, 0.4)
    _click_map_at(page, "#map", 0.75, 0.4)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 3",
        timeout=5000,
    )
    names_before = page.locator(".wpe-item .wpe-name").all_text_contents()
    assert [n.strip() for n in names_before] == ["Waypoint 1", "Waypoint 2", "Waypoint 3"]
    src = page.locator(".wpe-item").nth(2).locator(".wpe-handle")
    dst = page.locator(".wpe-item").nth(0).locator(".wpe-handle")
    src.drag_to(dst)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item .wpe-name')[0].textContent.trim() === 'Waypoint 3'",
        timeout=3000,
    )


def test_pin_first_as_start(page, server_url):
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    page.wait_for_function(
        "() => new URL(location.href).searchParams.get('route_id') !== null")
    _click_map_at(page, "#map", 0.3, 0.4)
    _click_map_at(page, "#map", 0.6, 0.4)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 2",
        timeout=3000,
    )
    page.locator("#pin-start-cb").check()
    expect(page.locator(".wpe-item").first.locator(".wpe-badge")).to_have_text("Start", timeout=3000)
    page.locator("#pin-start-cb").uncheck()
    expect(page.locator(".wpe-item").first.locator(".wpe-badge")).to_have_count(0, timeout=3000)
