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
