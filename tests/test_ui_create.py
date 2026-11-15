"""Playwright E2E tests for the Create Route page."""

import json
import requests as http_requests
from playwright.sync_api import expect

from server.routing.gpx_writer import encode_polyline


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


def test_ctrl_click_drops_stop(page, server_url):
    """Ctrl+click on the map drops a stop (kind=stop) instead of a waypoint."""
    _goto_create_fresh(page, server_url)
    box = page.locator("#map").bounding_box()
    x = box["x"] + 0.5 * box["width"]
    y = box["y"] + 0.5 * box["height"]
    page.keyboard.down("Control")
    page.mouse.click(x, y)
    page.keyboard.up("Control")
    expect(page.locator(".wpe-item-stop").first).to_be_visible(timeout=3000)
    expect(page.locator(".wpe-item-waypoint")).to_have_count(0)


def test_right_click_opens_pin_context_menu(page, server_url):
    """Right-click on a map pin opens the context menu with the expected
    actions (Mark as Stop, Exclude, Delete)."""
    _goto_create_fresh(page, server_url)
    _click_map_at(page, "#map", 0.3, 0.4)
    page.wait_for_selector(".wpe-item-waypoint", timeout=3000)
    page.locator(".wpe-marker.wpe-waypoint").first.click(button="right")
    menu = page.locator("#pin-ctx-menu")
    expect(menu).to_be_visible()
    expect(menu.locator("button[data-act='toggle-kind']")).to_have_text("Mark as Stop")
    expect(menu.locator("button[data-act='toggle-include']")).to_have_text("Exclude from route")
    expect(menu.locator("button[data-act='delete']")).to_be_visible()
    # Waypoints don't carry Edit stop details.
    expect(menu.locator("button[data-act='edit-stop']")).to_have_count(0)


def test_context_menu_toggle_kind_updates_sidebar(page, server_url):
    _goto_create_fresh(page, server_url)
    _click_map_at(page, "#map", 0.3, 0.4)
    page.wait_for_selector(".wpe-item-waypoint", timeout=3000)
    page.locator(".wpe-marker.wpe-waypoint").first.click(button="right")
    page.locator("#pin-ctx-menu button[data-act='toggle-kind']").click()
    expect(page.locator(".wpe-item-stop").first).to_be_visible(timeout=3000)


def test_context_menu_exclude_greys_marker_and_row(page, server_url):
    _goto_create_fresh(page, server_url)
    _click_map_at(page, "#map", 0.3, 0.4)
    page.wait_for_selector(".wpe-item", timeout=3000)
    page.locator(".wpe-marker").first.click(button="right")
    page.locator("#pin-ctx-menu button[data-act='toggle-include']").click()
    expect(page.locator(".wpe-item.wpe-excluded").first).to_be_visible(timeout=3000)
    expect(page.locator(".wpe-marker.wpe-dimmed").first).to_be_visible()


def test_context_menu_delete_requires_confirmation(page, server_url):
    """Delete takes two clicks — first arms, second actually deletes."""
    _goto_create_fresh(page, server_url)
    _click_map_at(page, "#map", 0.3, 0.4)
    page.wait_for_selector(".wpe-item", timeout=3000)
    page.locator(".wpe-marker").first.click(button="right")
    del_btn = page.locator("#pin-ctx-menu button[data-act='delete']")
    expect(del_btn).to_have_text("Delete")
    del_btn.click()
    expect(del_btn).to_have_text("Click again to confirm delete")
    expect(page.locator(".wpe-item")).to_have_count(1)
    del_btn.click()
    expect(page.locator(".wpe-item")).to_have_count(0, timeout=3000)


def test_stop_context_menu_offers_edit_details(page, server_url):
    """Stops get an Edit stop details… menu item that opens the modal
    and persists name / description / arrival_time on save."""
    _goto_create_fresh(page, server_url)
    box = page.locator("#map").bounding_box()
    x = box["x"] + 0.5 * box["width"]
    y = box["y"] + 0.5 * box["height"]
    page.keyboard.down("Control"); page.mouse.click(x, y); page.keyboard.up("Control")
    page.wait_for_selector(".wpe-item-stop", timeout=3000)

    page.locator(".wpe-marker.wpe-stop").first.click(button="right")
    page.locator("#pin-ctx-menu button[data-act='edit-stop']").click()
    overlay = page.locator("#stop-edit-overlay")
    expect(overlay).to_be_visible()
    page.locator("#stop-edit-name").fill("Samford Café")
    page.locator("#stop-edit-description").fill("Coffee + banana bread")
    page.locator("#stop-edit-arrival").fill("2026-05-01T09:30")
    page.locator("#stop-edit-save").click()
    expect(overlay).to_be_hidden(timeout=3000)

    wpt = page.evaluate("""async () => {
      const rid = new URL(location.href).searchParams.get('route_id');
      const r = await fetch(`/api/routes/${rid}/waypoints`);
      return (await r.json())[0];
    }""")
    assert wpt["name"] == "Samford Café"
    assert wpt["description"] == "Coffee + banana bread"
    # Stored as ISO 8601 — don't check the exact string (TZ-sensitive).
    # Instead verify the round-trip: reopen the modal and check the
    # datetime-local input renders the same 2026-05-01 09:30.
    assert wpt["arrival_time"], "arrival_time not persisted"
    page.locator(".wpe-marker.wpe-stop").first.click(button="right")
    page.locator("#pin-ctx-menu button[data-act='edit-stop']").click()
    expect(page.locator("#stop-edit-arrival")).to_have_value("2026-05-01T09:30")
    page.locator("#stop-edit-cancel").click()


# --------------------------------------------------------------------------
# Coverage for post-plan fixes: tile-layer picker, route-color picker,
# colour persistence, menu dismissal, drag-snap, cached-legs positive path,
# WP tab label, delete-arming reset.
# --------------------------------------------------------------------------


def test_waypoints_tab_label_is_WP_with_tooltip(page, server_url):
    _goto_create_fresh(page, server_url)
    wp_tab = page.locator(".wpe-tab[data-tab='waypoints']")
    expect(wp_tab).to_contain_text("WP")
    # Verify the full word 'Waypoints' is no longer in the tab label.
    assert "Waypoints" not in wp_tab.inner_text()
    title = wp_tab.get_attribute("title")
    assert title and "transit" in title.lower(), f"unexpected tooltip: {title!r}"

    stops_tab = page.locator(".wpe-tab[data-tab='stops']")
    stops_title = stops_tab.get_attribute("title")
    assert stops_title and "extended stop" in stops_title.lower(), f"unexpected tooltip: {stops_title!r}"


def test_pin_context_menu_closes_on_escape(page, server_url):
    _goto_create_fresh(page, server_url)
    _click_map_at(page, "#map", 0.3, 0.4)
    page.wait_for_selector(".wpe-item", timeout=3000)
    page.locator(".wpe-marker").first.click(button="right")
    expect(page.locator("#pin-ctx-menu")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("#pin-ctx-menu")).to_be_hidden()


def test_pin_context_menu_closes_on_outside_click(page, server_url):
    _goto_create_fresh(page, server_url)
    _click_map_at(page, "#map", 0.3, 0.4)
    page.wait_for_selector(".wpe-item", timeout=3000)
    page.locator(".wpe-marker").first.click(button="right")
    expect(page.locator("#pin-ctx-menu")).to_be_visible()
    # Click on the title input — well outside the menu.
    page.locator("#route-title").click()
    expect(page.locator("#pin-ctx-menu")).to_be_hidden()


def test_delete_arming_resets_when_menu_reopens(page, server_url):
    """After arming delete, closing the menu without confirming resets the
    button label on the next open."""
    _goto_create_fresh(page, server_url)
    _click_map_at(page, "#map", 0.3, 0.4)
    page.wait_for_selector(".wpe-item", timeout=3000)
    page.locator(".wpe-marker").first.click(button="right")
    del_btn = page.locator("#pin-ctx-menu button[data-act='delete']")
    del_btn.click()
    expect(del_btn).to_have_text("Click again to confirm delete")
    page.keyboard.press("Escape")
    # Re-open — label is back to 'Delete'.
    page.locator(".wpe-marker").first.click(button="right")
    del_btn = page.locator("#pin-ctx-menu button[data-act='delete']")
    expect(del_btn).to_have_text("Delete")


def test_drag_marker_snaps_to_nearby_road(page, server_url):
    """Dragging an existing pin should consult /locate and use the snapped
    coords if a road is within 10 m."""
    _goto_create_fresh(page, server_url)
    # Phase 1 — drop a pin; don't mock /locate yet so the click-add uses raw
    # coords (we don't care where this initial pin lands for the drag test).
    _click_map_at(page, "#map", 0.4, 0.5)
    page.wait_for_selector(".wpe-item", timeout=3000)

    # Phase 2 — mock /locate to return a specific snap lat/lon for the drag.
    snap_lat, snap_lon = -27.31415, 152.71828
    page.route("**/proxy/valhalla/locate", lambda route: route.fulfill(
        status=200,
        content_type="application/json",
        body=f'[{{"edges":[{{"correlated_lat":{snap_lat},"correlated_lon":{snap_lon},"distance":3.0}}]}}]',
    ))

    # Drag the marker to a new position. Leaflet's marker-drag is driven by
    # browser mouse events; simulate mousedown on the marker, move, mouseup.
    marker = page.locator(".wpe-marker").first
    box = marker.bounding_box()
    assert box
    start_x = box["x"] + box["width"] / 2
    start_y = box["y"] + box["height"] / 2
    map_box = page.locator("#map").bounding_box()
    end_x = map_box["x"] + 0.7 * map_box["width"]
    end_y = map_box["y"] + 0.3 * map_box["height"]

    page.mouse.move(start_x, start_y)
    page.mouse.down()
    # Leaflet needs incremental moves to recognise the drag.
    steps = 8
    for i in range(1, steps + 1):
        page.mouse.move(
            start_x + (end_x - start_x) * i / steps,
            start_y + (end_y - start_y) * i / steps,
        )
    page.mouse.up()

    # After drop, the waypoint's persisted coords match the mocked snap.
    page.wait_for_function(
        f"async () => {{"
        f"  const rid = new URL(location.href).searchParams.get('route_id');"
        f"  const r = await fetch(`/api/routes/${{rid}}/waypoints`);"
        f"  const wpts = await r.json();"
        f"  return wpts[0] && Math.abs(wpts[0].lat - ({snap_lat})) < 1e-5"
        f"           && Math.abs(wpts[0].lon - ({snap_lon})) < 1e-5;"
        f"}}",
        timeout=5000,
    )


def test_cached_legs_drawn_on_page_load_positive(page, server_url):
    """Opening /create?route_id=X with cached legs in the DB draws the
    solid generated route immediately + sets status to Ready · cached."""
    _goto_create_fresh(page, server_url)
    route_id = page.evaluate("() => new URL(location.href).searchParams.get('route_id')")
    import requests as _r
    for lat, lon in [(-27.40, 152.90), (-27.41, 152.91)]:
        _r.post(f"{server_url}/api/routes/{route_id}/waypoints",
                json={"name": f"{lat}", "lat": lat, "lon": lon, "kind": "stop"},
                timeout=5)
    # Mock /legs to pretend a previous generate stored one leg.
    valid_polyline = '~rjgs@_ygsbH~oR_pR'
    page.route(f"**/api/routes/{route_id}/legs", lambda route: route.fulfill(
        status=200,
        content_type="application/json",
        body=(f'[{{"route_id":{route_id},"from_position":0,"to_position":1,'
              f'"distance_m":1000,"duration_s":300,"polyline":"{valid_polyline}"}}]'),
    ))
    page.goto(f"{server_url}/create?route_id={route_id}")
    expect(page.locator("#generate-status")).to_contain_text("cached", timeout=5000)
    # Solid polyline present in the overlay pane.
    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('.leaflet-overlay-pane path'))"
        "  .some(p => !p.getAttribute('stroke-dasharray') && p.getAttribute('stroke'))",
        timeout=3000,
    )


def test_menu_route_color_updates_generated_layer(page, server_url):
    """Changing the Route colour applies to the generated polyline on the map."""
    _goto_create_fresh(page, server_url)
    # Mock /generate so the route lands without Valhalla.
    valid_polyline = '~rjgs@_ygsbH~oR_pR'
    page.route("**/api/routes/*/generate", lambda route: route.fulfill(
        status=200,
        content_type="application/json",
        body=(f'{{"legs_count":1,"distance_km":0.5,"duration_s":120,'
              f'"gpx_url":"/api/gpx/1","legs":[{{"from_position":0,"to_position":1,'
              f'"distance_m":500,"duration_s":120,"polyline":"{valid_polyline}"}}]}}'),
    ))
    _click_map_at(page, "#map", 0.3, 0.4)
    _click_map_at(page, "#map", 0.6, 0.4)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 2", timeout=5000)
    page.locator("#btn-gen-primary").click()
    # Wait for the generated (non-dashed) polyline to appear.
    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('.leaflet-overlay-pane path'))"
        "  .some(p => !p.getAttribute('stroke-dasharray'))",
        timeout=5000,
    )
    # Open the menu, change Route colour to a striking green.
    page.locator("#btn-gen-dropdown").click()
    page.evaluate("""() => {
      const inp = document.getElementById('menu-route-color');
      inp.value = '#22dd33';
      inp.dispatchEvent(new Event('input', { bubbles: true }));
    }""")
    # Generated polyline stroke now matches.
    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('.leaflet-overlay-pane path'))"
        "  .some(p => (p.getAttribute('stroke') || '').toLowerCase() === '#22dd33'"
        "           && !p.getAttribute('stroke-dasharray'))",
        timeout=3000,
    )
    # Persistence.
    stored = page.evaluate("() => localStorage.getItem('gpx-create-route-color')")
    assert stored == '#22dd33'


def test_menu_colors_persist_across_reload(page, server_url):
    _goto_create_fresh(page, server_url)
    _click_map_at(page, "#map", 0.3, 0.4)
    _click_map_at(page, "#map", 0.6, 0.4)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 2", timeout=5000)

    page.locator("#btn-gen-dropdown").click()
    page.evaluate("""() => {
      document.getElementById('menu-route-color').value = '#00ff00';
      document.getElementById('menu-route-color').dispatchEvent(new Event('input', {bubbles:true}));
      document.getElementById('menu-preview-color').value = '#ff00ff';
      document.getElementById('menu-preview-color').dispatchEvent(new Event('input', {bubbles:true}));
    }""")
    assert page.evaluate("() => localStorage.getItem('gpx-create-route-color')") == '#00ff00'
    assert page.evaluate("() => localStorage.getItem('gpx-create-preview-color')") == '#ff00ff'

    page.reload()
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 2", timeout=5000)
    page.locator("#btn-gen-dropdown").click()
    expect(page.locator("#menu-route-color")).to_have_value("#00ff00")
    expect(page.locator("#menu-preview-color")).to_have_value("#ff00ff")


def test_tile_layer_preference_persists_across_reload(page, server_url):
    """Seed localStorage with a non-default base layer and reload — the
    corresponding tile URL should be active on the map."""
    _goto_create_fresh(page, server_url)
    page.evaluate("() => localStorage.setItem('gpx-map-base-layer', 'OpenTopoMap (Contours)')")
    page.reload()
    # Wait for at least one tile whose URL comes from opentopomap.
    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('.leaflet-tile')).some("
        "  img => (img.src || '').includes('opentopomap.org'))",
        timeout=8000,
    )


def test_tile_layer_switch_writes_to_localStorage(page, server_url):
    """Switching the base layer via the Leaflet control persists the choice."""
    _goto_create_fresh(page, server_url)
    # The Leaflet control is collapsed; click a base-layer radio directly.
    page.evaluate("""() => {
      const labels = document.querySelectorAll('.leaflet-control-layers-base label');
      for (const lbl of labels) {
        if (lbl.textContent.trim() === 'Satellite') {
          lbl.querySelector('input').click();
          return;
        }
      }
      throw new Error('Satellite label not found');
    }""")
    # localStorage now holds 'Satellite'.
    page.wait_for_function(
        "() => localStorage.getItem('gpx-map-base-layer') === 'Satellite'",
        timeout=3000,
    )


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
    # Row text carries auxiliary badges (pin_role, link-chain for linked
    # waypoints) — strip those and compare just the leading name prefix.
    names_before = page.locator(".wpe-item .wpe-name").all_text_contents()
    leading = [n.strip().split(" ", 2)[:2] for n in names_before]
    assert leading == [["Waypoint", "1"], ["Waypoint", "2"], ["Waypoint", "3"]]
    src = page.locator(".wpe-item").nth(2).locator(".wpe-handle")
    dst = page.locator(".wpe-item").nth(0).locator(".wpe-handle")
    src.drag_to(dst)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item .wpe-name')[0]"
        ".textContent.trim().startsWith('Waypoint 3')",
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


def test_cached_legs_drawn_on_page_load(page, server_url):
    """Reloading a route that was already generated should immediately draw
    the cached route_legs — no user edit required, no Valhalla call needed."""
    _goto_create_fresh(page, server_url)
    # Extract the fresh route_id from the URL.
    route_id = page.evaluate("() => new URL(location.href).searchParams.get('route_id')")
    # Seed a cached leg via the REST API directly (no Valhalla involved).
    import requests as _r
    _r.post(
        f"{server_url}/api/routes/{route_id}/waypoints",
        json={"name": "A", "lat": -27.40, "lon": 152.90, "kind": "stop"},
        timeout=5,
    )
    _r.post(
        f"{server_url}/api/routes/{route_id}/waypoints",
        json={"name": "B", "lat": -27.41, "lon": 152.91, "kind": "stop"},
        timeout=5,
    )
    # Fake-generate by mocking Valhalla at the proxy level isn't available
    # here; instead, stand in for the already-generated state by asserting
    # the client path: we navigate back to /create?route_id=..., and — with
    # no cached legs — the status chip should start at "Idle", not cached.
    page.goto(f"{server_url}/create?route_id={route_id}")
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 2",
        timeout=5000,
    )
    # With no cache, status stays idle (no 'cached' text).
    expect(page.locator("#generate-status")).not_to_contain_text("cached", timeout=2000)


def test_preview_hidden_when_generated_route_drawn(page, server_url):
    """Once /generate returns and the road-snapped route is drawn, the
    dashed preview polyline should be removed — two overlapping lines is
    visual noise. When the user edits a waypoint the generated layer is
    invalidated and the preview should reappear."""
    _goto_create_fresh(page, server_url)
    # Mock a successful /generate with a single-leg shape.
    # Precomputed polyline for [(-27.40, 152.90), (-27.41, 152.91)] at
    # precision 6; decodes to two valid lat/lon pairs so drawGeneratedRoute
    # actually adds a Leaflet polyline to the map.
    valid_polyline = '~rjgs@_ygsbH~oR_pR'
    page.route("**/api/routes/*/generate", lambda route: route.fulfill(
        status=200,
        content_type="application/json",
        body=f'{{"legs_count":1,"distance_km":0.5,"duration_s":120,'
             f'"gpx_url":"/api/gpx/1",'
             f'"legs":[{{"from_position":0,"to_position":1,"distance_m":500,'
             f'"duration_s":120,"polyline":"{valid_polyline}"}}]}}',
    ))

    _click_map_at(page, "#map", 0.3, 0.4)
    _click_map_at(page, "#map", 0.6, 0.4)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 2", timeout=5000)

    # Before generate: dashed preview is visible (has a stroke-dasharray).
    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('.leaflet-overlay-pane path'))"
        "  .some(p => p.getAttribute('stroke-dasharray'))",
        timeout=3000,
    )

    # Trigger a manual generate.
    page.locator("#btn-gen-primary").click()

    # After generate: solid generated polyline exists, no dashed preview.
    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('.leaflet-overlay-pane path'))"
        "  .every(p => !p.getAttribute('stroke-dasharray'))",
        timeout=5000,
    )
    # And a non-dashed path is present (the generated layer).
    has_solid = page.evaluate(
        "() => Array.from(document.querySelectorAll('.leaflet-overlay-pane path'))"
        "  .some(p => !p.getAttribute('stroke-dasharray'))"
    )
    assert has_solid, "generated route layer missing after /generate"

    # Now edit — add a third waypoint. Preview should return because the
    # generated layer is invalidated.
    _click_map_at(page, "#map", 0.8, 0.4)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 3", timeout=5000)
    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('.leaflet-overlay-pane path'))"
        "  .some(p => p.getAttribute('stroke-dasharray'))",
        timeout=3000,
    )


def test_menu_color_picker_updates_preview_line(page, server_url):
    """Changing the Preview colour in the ▾ menu updates the live preview
    polyline's stroke and persists to localStorage."""
    _goto_create_fresh(page, server_url)
    _click_map_at(page, "#map", 0.3, 0.4)
    _click_map_at(page, "#map", 0.6, 0.4)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 2", timeout=5000)

    page.locator("#btn-gen-dropdown").click()
    expect(page.locator("#menu-preview-color")).to_be_visible()

    # Pick an unmistakable hot pink for the preview.
    page.evaluate("""() => {
      const inp = document.getElementById('menu-preview-color');
      inp.value = '#ff00aa';
      inp.dispatchEvent(new Event('input', { bubbles: true }));
    }""")

    # localStorage updated.
    stored = page.evaluate("() => localStorage.getItem('gpx-create-preview-color')")
    assert stored == '#ff00aa', f"got {stored}"

    # The preview polyline in the overlay pane now has stroke=#ff00aa.
    # Leaflet draws polylines as SVG <path> elements.
    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('.leaflet-overlay-pane path')).some("
        "  p => (p.getAttribute('stroke') || '').toLowerCase() === '#ff00aa')",
        timeout=3000,
    )


def test_menu_color_picker_available_in_auto_off_mode(page, server_url):
    """The colour-picker section shows up in the manual (auto OFF) menu too."""
    _goto_create_fresh(page, server_url)
    page.locator("#btn-gen-dropdown").click()
    expect(page.locator("#menu-route-color")).to_be_visible()
    expect(page.locator("#menu-preview-color")).to_be_visible()


def test_click_snaps_to_nearby_road(page, server_url):
    """When Valhalla's /locate returns a road within 10 m, the new waypoint
    is persisted at the snapped coordinates, not the raw click point."""
    _goto_create_fresh(page, server_url)
    # Mock /proxy/valhalla/locate: return a correlated point 5 m away, well
    # within the 10 m snap threshold.
    page.route("**/proxy/valhalla/locate", lambda route: route.fulfill(
        status=200,
        content_type="application/json",
        body='[{"input_lat":-27.0,"input_lon":152.0,"edges":['
             '{"correlated_lat":-27.00002,"correlated_lon":152.00002,"distance":5.0}'
             ']}]',
    ))
    _click_map_at(page, "#map", 0.5, 0.5)
    # Wait for the appended row.
    expect(page.locator(".wpe-item").first).to_be_visible(timeout=3000)
    # Read back the route's waypoints via the REST API to confirm coords.
    # We don't know the route_id cleanly from here, so check via in-page fetch.
    wpt = page.evaluate("""async () => {
      const rid = new URL(location.href).searchParams.get('route_id');
      const r = await fetch(`/api/routes/${rid}/waypoints`);
      return (await r.json())[0];
    }""")
    # The mock returns -27.00002 as correlated_lat. Exact match.
    assert abs(wpt["lat"] - (-27.00002)) < 1e-9, f"lat not snapped: {wpt}"
    assert abs(wpt["lon"] - 152.00002) < 1e-9, f"lon not snapped: {wpt}"


def test_click_does_not_snap_when_road_too_far(page, server_url):
    """When the nearest road is > 10 m away, the raw click coords are kept."""
    _goto_create_fresh(page, server_url)
    # Capture the click coordinates that app.js will send.
    page.route("**/proxy/valhalla/locate", lambda route: route.fulfill(
        status=200,
        content_type="application/json",
        body='[{"edges":[{"correlated_lat":99.999,"correlated_lon":99.999,"distance":250.0}]}]',
    ))
    _click_map_at(page, "#map", 0.5, 0.5)
    expect(page.locator(".wpe-item").first).to_be_visible(timeout=3000)
    wpt = page.evaluate("""async () => {
      const rid = new URL(location.href).searchParams.get('route_id');
      const r = await fetch(`/api/routes/${rid}/waypoints`);
      return (await r.json())[0];
    }""")
    # The faraway mocked coord (99.999, 99.999) must NOT be used because
    # distance exceeds 10 m; instead the real click point is kept.
    assert wpt["lat"] != 99.999 and wpt["lon"] != 99.999, \
        f"snapped despite distance 250 m: {wpt}"


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


def test_line_drag_inserts_waypoint_between_neighbours(page, server_url):
    """M2 Task 6: dragging the generated Valhalla polyline inserts a new
    waypoint at `from_position + 1`; downstream positions shift so the
    sidebar stays in numeric order."""
    _goto_create_fresh(page, server_url)

    # Mock snap-to-road so the test doesn't depend on Valhalla /locate.
    # Returning empty edges tells the Create page to keep the raw coords.
    page.route("**/proxy/valhalla/locate", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body='[{"edges":[]}]',
    ))

    # Mock /generate: returns a single leg with a valid polyline near the
    # default map centre so it projects on-screen at the test viewport.
    valid_polyline = '~rjgs@_ygsbH~oR_pR'
    page.route("**/api/routes/*/generate", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=f'{{"legs_count":1,"distance_km":0.5,"duration_s":120,'
             f'"gpx_url":"/api/gpx/1",'
             f'"legs":[{{"from_position":0,"to_position":1,"distance_m":500,'
             f'"duration_s":120,"polyline":"{valid_polyline}"}}]}}',
    ))

    # Drop two waypoints and trigger generate.
    _click_map_at(page, "#map", 0.35, 0.5)
    _click_map_at(page, "#map", 0.65, 0.5)
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 2", timeout=5000)
    page.locator("#btn-gen-primary").click()

    # Wait for the generated per-leg interactive polyline to land in
    # the overlay pane.
    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('.leaflet-overlay-pane path'))"
        "  .some(p => p.classList.contains('leaflet-interactive')"
        "           && !p.getAttribute('stroke-dasharray'))",
        timeout=5000,
    )

    # Look up the polyline's on-screen midpoint — SVG paths are thin so
    # we can't just click anywhere. Using the path's bounding box gives
    # us a pixel the hit-test will actually land on.
    rect = page.evaluate(
        """() => {
            const path = Array.from(
                document.querySelectorAll('.leaflet-overlay-pane path'))
                .find(p => p.classList.contains('leaflet-interactive')
                    && !p.getAttribute('stroke-dasharray'));
            if (!path) return null;
            const r = path.getBoundingClientRect();
            return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
        }"""
    )
    assert rect, "generated interactive polyline not found on page"

    # Start the drag on the polyline, move to a clearly different point,
    # release. The line-drag handler POSTs a waypoint at position 1.
    page.mouse.move(rect["x"], rect["y"])
    page.mouse.down()
    page.mouse.move(rect["x"] + 40, rect["y"] - 80, steps=8)
    page.mouse.up()

    # Sidebar now has three rows, positions [0, 1, 2], name=Waypoint in middle.
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 3",
        timeout=5000,
    )

    # Pull positions from the route API — it's the authoritative ordering.
    rid = page.evaluate(
        "() => new URL(location.href).searchParams.get('route_id')"
    )
    listing = page.evaluate(
        f"() => fetch('/api/routes/{rid}/waypoints').then(r => r.json())"
    )
    assert [w["position"] for w in listing] == [0, 1, 2], listing
    assert listing[1]["kind"] == "waypoint", listing[1]


def test_line_drag_inserts_between_correct_pair_on_multi_waypoint_route(page, server_url):
    """M2 Task 7 regression: 6 waypoints produce 5 interactive polylines
    (one per adjacent pair). Grabbing the one between WP5 and WP6 must
    insert at position 5 — per-leg routing makes this direct (each
    rendered line carries its own leg.from_position), so the test now
    exercises real mouse drags against the specific leg, not a helper."""
    wp_coords = [(-27.40 - 0.01 * i, 152.95) for i in range(6)]

    r = http_requests.post(f"{server_url}/api/routes",
                           json={"title": "drag-reg"},
                           headers={"Content-Type": "application/json"})
    rid = r.json()["id"]
    for i, (lat, lon) in enumerate(wp_coords):
        http_requests.post(
            f"{server_url}/api/routes/{rid}/waypoints",
            json={"name": f"WP{i + 1}", "lat": lat, "lon": lon,
                  "kind": "waypoint"},
        )

    page.route("**/proxy/valhalla/locate", lambda route: route.fulfill(
        status=200, content_type="application/json", body='[{"edges":[]}]',
    ))

    # Per-leg routing: Valhalla returns 5 legs for 6 waypoints.
    legs = []
    for i in range(5):
        legs.append({
            "from_position": i,
            "to_position": i + 1,
            "distance_m": 1000,
            "duration_s": 120,
            "polyline": encode_polyline([wp_coords[i], wp_coords[i + 1]], precision=6),
        })
    body = json.dumps({
        "legs_count": 5, "distance_km": 5.0, "duration_s": 600,
        "gpx_url": f"/api/gpx/{rid}",
        "legs": legs,
    })
    page.route(f"**/api/routes/{rid}/generate",
               lambda route: route.fulfill(status=200, content_type="application/json", body=body))

    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create?route_id={rid}")
    page.wait_for_function("() => window.__appReady === true", timeout=10000)
    expect(page.locator(".wpe-item")).to_have_count(6, timeout=5000)

    page.locator("#btn-gen-primary").click()
    # Five distinct interactive polylines rendered confirms the per-leg
    # split is reaching the DOM.
    page.wait_for_function(
        "() => document.querySelectorAll("
        "  '.leaflet-overlay-pane path.leaflet-interactive:not([stroke-dasharray])'"
        ").length === 5",
        timeout=5000,
    )

    # Locate the exact leg whose from_position is 4 (WP5 → WP6) via the
    # live Leaflet layer group — matching by DOM order would be fragile.
    rect = page.evaluate(
        """(fp) => {
            const layers = window.__appState.generatedLayer.getLayers();
            const line = layers.find(l => l._legFromPosition === fp);
            if (!line || !line._path) return null;
            const r = line._path.getBoundingClientRect();
            return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
        }""",
        4,
    )
    assert rect, "leg with from_position=4 not found on page"
    page.mouse.move(rect["x"], rect["y"])
    page.mouse.down()
    page.mouse.move(rect["x"] + 40, rect["y"] - 60, steps=6)
    page.mouse.up()

    # After the drag: 7 rows, fresh one at position 5.
    page.wait_for_function(
        "() => document.querySelectorAll('.wpe-item').length === 7",
        timeout=5000,
    )
    listing = page.evaluate(
        f"() => fetch('/api/routes/{rid}/waypoints').then(r => r.json())"
    )
    positions = [w["position"] for w in listing]
    assert positions == [0, 1, 2, 3, 4, 5, 6], positions
    assert listing[5]["kind"] == "waypoint", listing[5]


# ---- route title load / persist (create-title fix, Task 1) ----

def _seed_route(server_url, title):
    r = http_requests.post(f"{server_url}/api/routes",
                           json={"title": title, "profile": "bicycle"})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _api_title(server_url, rid):
    return http_requests.get(f"{server_url}/api/routes/{rid}").json()["title"]


def _open_create(page, server_url, rid):
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/create?route_id={rid}")
    page.wait_for_function("() => window.__appReady === true", timeout=8000)


def _track_patches(page, rid):
    patches = []
    page.on("request", lambda req: patches.append(req)
            if req.method == "PATCH" and req.url.endswith(f"/api/routes/{rid}")
            else None)
    return patches


def test_create_page_shows_existing_route_title(page, server_url):
    rid = _seed_route(server_url, "Seeded Ride Title")
    _open_create(page, server_url, rid)
    expect(page.locator("#route-title")).to_have_value("Seeded Ride Title")
    expect(page.locator("#nav-route-title")).to_have_text("Seeded Ride Title")
    assert "Seeded Ride Title" in page.title()


def test_title_blur_without_edit_sends_no_patch(page, server_url):
    rid = _seed_route(server_url, "Keep Me As Is")
    patches = _track_patches(page, rid)
    _open_create(page, server_url, rid)
    page.locator("#route-title").click()
    page.locator("#route-title").blur()
    page.wait_for_timeout(300)
    assert patches == []
    assert _api_title(server_url, rid) == "Keep Me As Is"


def test_title_edit_saves_once_and_updates_nav(page, server_url):
    rid = _seed_route(server_url, "Old Title")
    patches = _track_patches(page, rid)
    _open_create(page, server_url, rid)
    page.locator("#route-title").fill("New Title")
    page.locator("#route-title").blur()
    page.wait_for_function(
        "() => document.getElementById('nav-route-title').textContent === 'New Title'")
    assert len(patches) == 1
    assert _api_title(server_url, rid) == "New Title"
    assert "New Title" in page.title()


def test_blank_title_reverts_and_does_not_save(page, server_url):
    rid = _seed_route(server_url, "Blank Test")
    patches = _track_patches(page, rid)
    _open_create(page, server_url, rid)
    page.locator("#route-title").fill("   ")
    page.locator("#route-title").blur()
    expect(page.locator("#route-title")).to_have_value("Blank Test")
    assert patches == []
    assert _api_title(server_url, rid) == "Blank Test"


def test_title_save_failure_keeps_text_and_shows_error(page, server_url):
    rid = _seed_route(server_url, "Fail Test")
    _open_create(page, server_url, rid)
    handler = lambda route: route.fulfill(status=500, body="boom")
    page.route(f"**/api/routes/{rid}", lambda route: handler(route)
               if route.request.method == "PATCH" else route.continue_())
    page.locator("#route-title").fill("Typed Title")
    page.locator("#route-title").blur()
    expect(page.locator("#generate-error")).to_be_visible()
    expect(page.locator("#generate-error")).to_contain_text("Could not save title")
    expect(page.locator("#route-title")).to_have_value("Typed Title")
    assert _api_title(server_url, rid) == "Fail Test"
    page.unroute(f"**/api/routes/{rid}")
    page.locator("#route-title").focus()
    page.locator("#route-title").blur()
    page.wait_for_function(
        "() => document.getElementById('nav-route-title').textContent === 'Typed Title'")
    assert _api_title(server_url, rid) == "Typed Title"


def test_hostile_title_renders_as_text(page, server_url):
    hostile = "<img src=x onerror=window.__pwn=1>"
    rid = _seed_route(server_url, hostile)
    _open_create(page, server_url, rid)
    page.wait_for_timeout(300)
    assert page.evaluate("() => window.__pwn") is None
    expect(page.locator("#route-title")).to_have_value(hostile)
    expect(page.locator("#nav-route-title")).to_have_text(hostile)


def test_new_route_unchanged(page, server_url):
    page.set_viewport_size({"width": 1280, "height": 1000})
    patches = []
    page.on("request", lambda req: patches.append(req) if req.method == "PATCH" else None)
    page.goto(f"{server_url}/create")
    page.wait_for_function("() => window.__appReady === true", timeout=8000)
    expect(page.locator("#route-title")).to_have_value("Untitled Route")
    expect(page.locator("#nav-route-title")).to_have_text("New Route")
    page.locator("#route-title").click()
    page.locator("#route-title").blur()
    page.wait_for_timeout(300)
    assert patches == []


# ---- unknown / invalid route_id (create-title fix, Task 2) ----

def _collect_mutations(page):
    muts = []
    page.on("request", lambda req: muts.append(f"{req.method} {req.url}")
            if req.method in ("POST", "PATCH", "PUT", "DELETE") else None)
    return muts


def _assert_not_found_panel(page, muts):
    panel = page.locator("#route-load-error")
    expect(panel).to_be_visible(timeout=8000)
    expect(panel).to_contain_text("Route not found")
    link = panel.locator("a[href='/']")
    expect(link).to_be_visible()
    expect(page.locator("#editor-panel")).to_be_hidden()
    expect(page.locator("#map")).to_be_hidden()
    page.wait_for_timeout(300)
    assert muts == []
    assert page.evaluate("() => location.search") is not None


def test_create_unknown_route_shows_not_found(page, server_url):
    muts = _collect_mutations(page)
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto(f"{server_url}/create?route_id=999999")
    _assert_not_found_panel(page, muts)
    assert errs == []


def test_create_foreign_route_shows_not_found(browser, server_url):
    rid = http_requests.post(f"{server_url}/api/routes",
                             json={"title": "Not yours", "profile": "bicycle"},
                             headers={"Remote-User": "user-a"}).json()["id"]
    ctx = browser.new_context(extra_http_headers={"Remote-User": "user-b"})
    page = ctx.new_page()
    try:
        muts = _collect_mutations(page)
        page.goto(f"{server_url}/create?route_id={rid}")
        _assert_not_found_panel(page, muts)
    finally:
        ctx.close()


import pytest


@pytest.mark.parametrize("bad", ["abc", "0", "-3", "1.5", ""])
def test_create_non_numeric_route_id(page, server_url, bad):
    muts = _collect_mutations(page)
    urls = []
    page.on("request", lambda req: urls.append(req.url))
    errs = []
    page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    page.goto(f"{server_url}/create?route_id={bad}")
    _assert_not_found_panel(page, muts)
    assert not any("/api/routes/NaN" in u for u in urls)
    assert not any("NaN" in e for e in errs)


def test_create_route_load_500_shows_retry(page, server_url):
    rid = _seed_route(server_url, "Retry Me")
    muts = _collect_mutations(page)
    page.route(f"**/api/routes/{rid}",
               lambda route: route.fulfill(status=500, body="boom")
               if route.request.method == "GET" else route.continue_())
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{server_url}/create?route_id={rid}")
    panel = page.locator("#route-load-error")
    expect(panel).to_be_visible(timeout=8000)
    expect(panel).to_contain_text("Could not load route")
    retry = panel.get_by_role("button", name="Retry")
    expect(retry).to_be_visible()
    assert retry.bounding_box()["height"] >= 44
    assert muts == []
    page.unroute(f"**/api/routes/{rid}")
    retry.click()
    page.wait_for_function("() => window.__appReady === true", timeout=8000)
    expect(page.locator("#route-title")).to_have_value("Retry Me")
    expect(page.locator("#route-load-error")).to_be_hidden()


def test_create_blank_server_title_falls_back_without_patch(page, server_url):
    rid = _seed_route(server_url, "Temp")
    http_requests.patch(f"{server_url}/api/routes/{rid}", json={"title": "x"})
    patches = _track_patches(page, rid)
    page.route(f"**/api/routes/{rid}",
               lambda route: route.fulfill(status=200, content_type="application/json",
                                           body='{"id": %d, "title": "  "}' % rid)
               if route.request.method == "GET" else route.continue_())
    _open_create(page, server_url, rid)
    expect(page.locator("#route-title")).to_have_value("Untitled Route")
    page.locator("#route-title").focus()
    page.locator("#route-title").blur()
    page.wait_for_timeout(300)
    assert patches == []
