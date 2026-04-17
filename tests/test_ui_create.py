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
    # Reuse the fresh-localStorage helper to sidestep the view-state
    # pollution that was making this test flaky when run alongside others.
    _goto_create_fresh(page, server_url)
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


# test_pin_first_as_start removed: the manual "Pin first as start" checkbox
# was redundant in M1 (no optimiser yet — first waypoint is the start by
# definition). The pin_role column on route_waypoints is still there for
# when M3 ships optimisation and needs to lock pre-optimisation ordering.


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


def test_primary_label_stays_generate_now_across_auto_states(page, server_url):
    """The primary button label is always 'Generate Now' outside of busy
    state — manual, ready, and (with countdown) debounce all read the same."""
    _goto_create_fresh(page, server_url)

    # Manual.
    expect(page.locator("#gen-primary-label")).to_have_text("Generate Now")

    # Enable auto (with 2 waypoints so auto has something to schedule).
    _click_map_at(page, "#map", 0.3, 0.4)
    _click_map_at(page, "#map", 0.6, 0.4)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 2", timeout=5000)
    page.locator("#btn-gen-dropdown").click()
    page.locator("#menu-enable-auto").click()

    # Still 'Generate Now' after auto-on — variant changes, label doesn't.
    expect(page.locator("#gen-primary-label")).to_have_text("Generate Now", timeout=3000)
    # And the variant is no longer manual.
    page.wait_for_function(
        "() => document.getElementById('generate-control').dataset.variant !== 'manual'",
        timeout=3000,
    )


def test_auto_on_with_single_waypoint_does_not_start_countdown(page, server_url):
    """Auto mode should not fire for a route with fewer than two waypoints —
    Valhalla requires ≥ 2 and firing a debounce timer just to error out is
    noise the user shouldn't see."""
    _goto_create_fresh(page, server_url)
    # Add ONE waypoint.
    _click_map_at(page, "#map", 0.3, 0.4)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 1", timeout=5000)

    # Enable auto.
    page.locator("#btn-gen-dropdown").click()
    page.locator("#menu-enable-auto").click()

    # Variant becomes 'ready' (not debounce) and stays there — no timer.
    expect(page.locator("#generate-control")).to_have_attribute("data-variant", "ready", timeout=2000)
    # Countdown SVG is hidden.
    expect(page.locator("#gen-primary-countdown")).to_be_hidden()

    # Drop a second waypoint — leading-edge fires right away, so we should
    # see either 'busy' (request in flight) or 'cooldown' (post-response wait).
    _click_map_at(page, "#map", 0.6, 0.4)
    page.wait_for_function(
        "() => ['busy', 'cooldown'].includes(document.getElementById('generate-control').dataset.variant)",
        timeout=5000,
    )


def test_leading_edge_fires_then_cooldown(page, server_url):
    """With auto ON, adding the second waypoint should fire /generate
    immediately (button briefly 'busy') and the cooldown timer should start
    AFTER the generate completes (not before). We verify that the variant
    progresses through either 'busy' → 'cooldown' or straight to 'cooldown'
    depending on how fast the backend responds."""
    _goto_create_fresh(page, server_url)
    # Enable auto BEFORE dropping pins, so the second pin is the trigger.
    page.locator("#btn-gen-dropdown").click()
    page.locator("#menu-enable-auto").click()
    # Drop the first pin — auto should NOT fire (< 2 waypoints).
    _click_map_at(page, "#map", 0.3, 0.4)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 1",
        timeout=5000,
    )
    expect(page.locator("#generate-control")).to_have_attribute("data-variant", "ready")

    # Drop the second pin — this should fire /generate immediately. The
    # variant transitions to busy or cooldown. Valhalla may error out on
    # map-grid coords, but the cooldown starts regardless — that's the
    # critical contract the test guards.
    _click_map_at(page, "#map", 0.6, 0.4)
    page.wait_for_function(
        "() => ['busy', 'cooldown'].includes(document.getElementById('generate-control').dataset.variant)",
        timeout=5000,
    )
    # Within the cooldown, the countdown SVG is visible.
    page.wait_for_function(
        "() => document.getElementById('generate-control').dataset.variant === 'cooldown'",
        timeout=10000,
    )
    expect(page.locator("#gen-primary-countdown")).to_be_visible()


def test_pin_offroad_triggers_actionable_guidance(page, server_url):
    """A Valhalla 499 error surfaces guidance text in the error panel, not
    just the raw upstream body."""
    _goto_create_fresh(page, server_url)
    # Drop two pins in the middle of the default Brisbane map view — likely
    # cycleable roads, but the point of the test is the error rendering path.
    # Inject a fake /generate error via a route handler so the test is
    # deterministic regardless of the real Valhalla.
    page.route("**/api/routes/*/generate", lambda route: route.fulfill(
        status=502,
        content_type="application/json",
        body='{"error":"Upstream routing service failed","detail":"Valhalla at '
             'http://test/route returned HTTP 400","upstream_url":'
             '"http://test/route","upstream_body":"{\\"error_code\\":499,\\"error\\":'
             '\\"Unknown: Could not find candidate edge used for destination label\\"}"}',
    ))
    _click_map_at(page, "#map", 0.3, 0.4)
    _click_map_at(page, "#map", 0.6, 0.4)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 2",
        timeout=5000,
    )
    # Trigger manual generate.
    page.locator("#btn-gen-primary").click()
    # Error panel should appear with a guidance line explaining snapping.
    expect(page.locator("#generate-error .err-guidance")).to_be_visible(timeout=5000)
    expect(page.locator("#generate-error .err-guidance")).to_contain_text("snap")
    # Raw upstream body still shown below the guidance.
    expect(page.locator("#generate-error .err-upstream")).to_contain_text("error_code")
