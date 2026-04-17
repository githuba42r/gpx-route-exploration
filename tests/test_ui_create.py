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


# --------------------------------------------------------------------------
# Auto-generate + split-button tests
#
# The split-button at #generate-control carries a data-variant attribute that
# drives all its visual state (manual / ready / debounce / rate / busy), and
# the dropdown menu's content varies with autoGenerate state. Those are the
# contract we assert against — not specific pixel colors.
# --------------------------------------------------------------------------


def _goto_create_fresh(page, server_url):
    """Clear localStorage first so saved prefs from a prior test don't leak in."""
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create")
    page.evaluate("() => localStorage.clear()")
    page.reload()
    page.wait_for_function(
        "() => new URL(location.href).searchParams.get('route_id') !== null",
        timeout=5000,
    )


def test_generate_button_defaults_to_manual_variant(page, server_url):
    """Fresh page with no saved prefs → auto OFF, split-button in manual state."""
    _goto_create_fresh(page, server_url)
    expect(page.locator("#generate-control")).to_have_attribute("data-variant", "manual")
    expect(page.locator("#gen-primary-label")).to_have_text("Generate Now")


def test_dropdown_menu_when_auto_off_offers_enable(page, server_url):
    """Clicking the ▾ arrow with auto OFF shows a single Enable Auto option."""
    _goto_create_fresh(page, server_url)
    page.locator("#btn-gen-dropdown").click()
    expect(page.locator("#gen-menu")).to_be_visible()
    expect(page.locator("#menu-enable-auto")).to_be_visible()
    # No debounce slider in this menu.
    expect(page.locator("#menu-debounce-slider")).to_have_count(0)


def test_enable_auto_flips_variant_and_exposes_debounce(page, server_url):
    """Enable auto → variant moves off manual; menu now shows debounce slider +
    Generate Now action."""
    _goto_create_fresh(page, server_url)
    # Add two waypoints first so auto-generate has something to schedule.
    _click_map_at(page, "#map", 0.3, 0.4)
    _click_map_at(page, "#map", 0.6, 0.4)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 2", timeout=5000)

    page.locator("#btn-gen-dropdown").click()
    page.locator("#menu-enable-auto").click()

    # Menu closed itself; variant is no longer "manual".
    expect(page.locator("#gen-menu")).to_be_hidden()
    page.wait_for_function(
        "() => document.getElementById('generate-control').dataset.variant !== 'manual'",
        timeout=3000,
    )

    # Re-open menu — now it has the debounce slider + Generate Now.
    page.locator("#btn-gen-dropdown").click()
    expect(page.locator("#menu-debounce-slider")).to_be_visible()
    expect(page.locator("#menu-debounce-seconds")).to_be_visible()
    expect(page.locator("#menu-generate-now")).to_be_visible()


def test_primary_button_when_auto_on_disables_auto(page, server_url):
    """When auto is ON, clicking the primary button turns auto OFF."""
    _goto_create_fresh(page, server_url)
    _click_map_at(page, "#map", 0.3, 0.4)
    _click_map_at(page, "#map", 0.6, 0.4)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 2", timeout=5000)

    # Enable auto via the menu.
    page.locator("#btn-gen-dropdown").click()
    page.locator("#menu-enable-auto").click()
    page.wait_for_function(
        "() => document.getElementById('generate-control').dataset.variant !== 'manual'",
        timeout=3000,
    )

    # Click primary → flips back to manual.
    page.locator("#btn-gen-primary").click()
    expect(page.locator("#generate-control")).to_have_attribute("data-variant", "manual", timeout=3000)
    expect(page.locator("#gen-primary-label")).to_have_text("Generate Now")


def test_debounce_slider_and_number_stay_in_sync(page, server_url):
    """Slider and number field are bidirectionally bound; localStorage persists."""
    _goto_create_fresh(page, server_url)
    _click_map_at(page, "#map", 0.3, 0.4)
    _click_map_at(page, "#map", 0.6, 0.4)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 2", timeout=5000)

    page.locator("#btn-gen-dropdown").click()
    page.locator("#menu-enable-auto").click()
    page.locator("#btn-gen-dropdown").click()

    # Default 5 in both.
    expect(page.locator("#menu-debounce-slider")).to_have_value("5")
    expect(page.locator("#menu-debounce-seconds")).to_have_value("5")

    # Change the number field → slider should follow + localStorage updated.
    page.locator("#menu-debounce-seconds").fill("12")
    page.locator("#menu-debounce-seconds").dispatch_event("change")
    expect(page.locator("#menu-debounce-slider")).to_have_value("12")
    stored = page.evaluate("() => localStorage.getItem('gpx-create-debounce-ms')")
    assert stored == "12000"


def test_auto_generate_preference_persists_across_reload(page, server_url):
    """Turn auto ON, reload page — the primary button is still in auto-ready
    variant (saved to localStorage)."""
    _goto_create_fresh(page, server_url)
    _click_map_at(page, "#map", 0.3, 0.4)
    _click_map_at(page, "#map", 0.6, 0.4)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 2", timeout=5000)

    page.locator("#btn-gen-dropdown").click()
    page.locator("#menu-enable-auto").click()
    page.wait_for_function(
        "() => document.getElementById('generate-control').dataset.variant !== 'manual'",
        timeout=3000,
    )

    stored = page.evaluate("() => localStorage.getItem('gpx-create-auto-generate')")
    assert stored == "1"

    page.reload()
    # After reload, variant should still not be manual. We don't assert ready
    # specifically because the page may kick a debounce scheduler immediately.
    page.wait_for_function(
        "() => document.getElementById('generate-control').dataset.variant !== 'manual'",
        timeout=5000,
    )


def test_adding_waypoint_while_auto_on_shows_pending_countdown(page, server_url):
    """Auto ON + add a waypoint → variant becomes 'debounce' and the
    countdown SVG is visible."""
    _goto_create_fresh(page, server_url)
    _click_map_at(page, "#map", 0.3, 0.4)
    _click_map_at(page, "#map", 0.6, 0.4)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 2", timeout=5000)

    # Enable auto first.
    page.locator("#btn-gen-dropdown").click()
    page.locator("#menu-enable-auto").click()

    # Set a short debounce (2s) so the debounce state is observable and the
    # test doesn't hang on the default 5s.
    page.locator("#btn-gen-dropdown").click()
    page.locator("#menu-debounce-seconds").fill("2")
    page.locator("#menu-debounce-seconds").dispatch_event("change")
    # Close menu by pressing Escape or clicking outside.
    page.keyboard.press("Escape")

    # Add a third waypoint — this is a change, so debounce timer should kick.
    _click_map_at(page, "#map", 0.7, 0.4)

    # Variant will be 'debounce' (or 'rate' if rate-limit is in effect). Both
    # show the countdown.
    page.wait_for_function(
        "() => ['debounce', 'rate'].includes(document.getElementById('generate-control').dataset.variant)",
        timeout=3000,
    )
    # The SVG countdown element is inline-block while pending.
    expect(page.locator("#gen-primary-countdown")).to_be_visible()
