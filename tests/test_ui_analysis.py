import os
import requests as http_requests
from playwright.sync_api import expect

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _upload_via_api(server_url):
    with open(os.path.join(FIXTURES, "sample.gpx"), "rb") as f:
        resp = http_requests.post(
            f"{server_url}/api/routes",
            files={"file": ("sample.gpx", f)},
            data={"title": "Analysis Test"},
        )
    return resp.json()["id"]


def test_analysis_page_loads_map(page, server_url):
    route_id = _upload_via_api(server_url)
    page.goto(f"{server_url}/route/{route_id}")
    expect(page.locator("#map")).to_be_visible()
    expect(page.locator(".leaflet-tile-container")).to_be_visible(timeout=10000)


def test_analysis_page_shows_stats(page, server_url):
    route_id = _upload_via_api(server_url)
    page.goto(f"{server_url}/route/{route_id}")
    expect(page.locator("#stats")).to_be_visible()
    expect(page.locator(".stat")).to_have_count(7)


def test_elevation_profile_renders(page, server_url):
    route_id = _upload_via_api(server_url)
    page.goto(f"{server_url}/route/{route_id}")
    expect(page.locator("#profile-canvas")).to_be_visible()


def test_gradient_legend_visible(page, server_url):
    route_id = _upload_via_api(server_url)
    page.goto(f"{server_url}/route/{route_id}")
    expect(page.locator("#legend")).to_be_visible()


def test_settings_sliders_present(page, server_url):
    route_id = _upload_via_api(server_url)
    page.goto(f"{server_url}/route/{route_id}")
    expect(page.locator("#set-smooth")).to_be_visible()
    expect(page.locator("#set-graddist")).to_be_visible()


def test_navigate_back_to_library(page, server_url):
    route_id = _upload_via_api(server_url)
    page.goto(f"{server_url}/route/{route_id}")
    page.locator("a[href='/']").first.click()
    expect(page).to_have_url(f"{server_url}/")


def test_analysis_page_no_js_errors(page, server_url):
    """Analysis page must load without any uncaught JS errors.

    Regression guard: a prior bug had createGradientMarkers reading
    points[i].gradient before it had been computed, throwing a TypeError
    that aborted main() and silently broke every downstream feature
    (legend, colored segments, profile, hover, context menu).
    """
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))

    route_id = _upload_via_api(server_url)
    page.goto(f"{server_url}/route/{route_id}")

    # Wait until the main init has had a chance to complete.
    expect(page.locator("#legend .legend-item").first).to_be_visible(timeout=10000)
    assert errors == [], f"JS errors on analysis page: {errors}"


def test_gradient_legend_has_bands(page, server_url):
    """The legend must render one item per gradient band (not just the title).

    Previously the test only asserted #legend was visible — it would pass
    even if the legend was empty because main() had thrown early.
    """
    route_id = _upload_via_api(server_url)
    page.goto(f"{server_url}/route/{route_id}")
    # Default is absolute mode, which has 6 bands.
    expect(page.locator("#legend .legend-item")).to_have_count(6, timeout=10000)


def test_stats_panel_shows_numeric_values(page, server_url):
    """Stats values must be populated numbers, not empty/NaN/undefined."""
    route_id = _upload_via_api(server_url)
    page.goto(f"{server_url}/route/{route_id}")
    expect(page.locator("#stats .stat")).to_have_count(7, timeout=10000)
    values = page.locator("#stats .stat .value").all_text_contents()
    assert len(values) == 7
    for v in values:
        assert v.strip(), f"empty stat value: {values!r}"
        assert "NaN" not in v and "undefined" not in v, f"bad stat value: {v!r}"


def _wait_for_main_ready(page):
    """Wait until main() has completed (legend items are the reliable signal)."""
    expect(page.locator("#legend .legend-item").first).to_be_visible(timeout=10000)


def _plot_bounds(page):
    """Return the canvas bounding box + the plot-area padding used by profile.js.

    Returned dict: {left, top, width, height, plot_left, plot_right, plot_top, plot_bottom}
    """
    # The app is a full-page flex layout; the default 1280x720 viewport cuts
    # the profile canvas off the bottom, so mouse events never reach it.
    # Make the viewport tall enough to fit the whole layout.
    page.set_viewport_size({"width": 1280, "height": 1000})
    canvas = page.locator("#profile-canvas")
    box = canvas.bounding_box()
    assert box, "profile canvas missing"
    # Paddings are hardcoded in profile.js (padL=50, padR=16, padT=16, padB=30).
    return {
        "left": box["x"],
        "top": box["y"],
        "width": box["width"],
        "height": box["height"],
        "plot_left": box["x"] + 50,
        "plot_right": box["x"] + box["width"] - 16,
        "plot_top": box["y"] + 16,
        "plot_bottom": box["y"] + box["height"] - 30,
    }


def _drag_on_profile(page, x1_frac, x2_frac):
    """Drag across the plot area of the profile canvas, from fraction x1 to x2."""
    b = _plot_bounds(page)
    plot_w = b["plot_right"] - b["plot_left"]
    mid_y = (b["plot_top"] + b["plot_bottom"]) / 2
    x_start = b["plot_left"] + x1_frac * plot_w
    x_end = b["plot_left"] + x2_frac * plot_w
    page.mouse.move(x_start, mid_y)
    page.mouse.down()
    # Playwright needs intermediate moves for the page to register a drag.
    steps = 10
    for i in range(1, steps + 1):
        t = i / steps
        page.mouse.move(x_start + (x_end - x_start) * t, mid_y)
    page.mouse.up()


def test_profile_drag_selection_zooms_and_highlights(page, server_url):
    """Drag-selecting a range on the profile must (a) zoom the chart,
    (b) show a reset button, (c) add a highlight polyline to the map."""
    route_id = _upload_via_api(server_url)
    page.goto(f"{server_url}/route/{route_id}")
    _wait_for_main_ready(page)

    # Baseline: no reset button, no highlight polyline.
    expect(page.locator(".profile-reset-zoom")).to_be_hidden()
    initial_highlight_count = page.evaluate(
        "() => Array.from(document.querySelectorAll("
        "  '.leaflet-overlay-pane path[stroke]'"
        ")).filter(p => p.getAttribute('stroke').toLowerCase() === '#00e5ff').length"
    )
    assert initial_highlight_count == 0

    # Drag from 25% to 75% of the plot width.
    _drag_on_profile(page, 0.25, 0.75)

    # Reset button appears.
    expect(page.locator(".profile-reset-zoom")).to_be_visible(timeout=2000)

    # Highlight polyline was added to the map.
    page.wait_for_function(
        "() => Array.from(document.querySelectorAll("
        "  '.leaflet-overlay-pane path[stroke]'"
        ")).some(p => p.getAttribute('stroke').toLowerCase() === '#00e5ff')",
        timeout=2000,
    )


def test_profile_reset_zoom_clears_selection(page, server_url):
    """Clicking Reset Zoom must restore the full view and remove the highlight."""
    route_id = _upload_via_api(server_url)
    page.goto(f"{server_url}/route/{route_id}")
    _wait_for_main_ready(page)

    _drag_on_profile(page, 0.2, 0.8)
    expect(page.locator(".profile-reset-zoom")).to_be_visible(timeout=2000)

    page.locator(".profile-reset-zoom").click()

    expect(page.locator(".profile-reset-zoom")).to_be_hidden()
    # Highlight polyline should be removed.
    page.wait_for_function(
        "() => Array.from(document.querySelectorAll("
        "  '.leaflet-overlay-pane path[stroke]'"
        ")).every(p => p.getAttribute('stroke').toLowerCase() !== '#00e5ff')",
        timeout=2000,
    )


def test_profile_short_click_does_not_zoom(page, server_url):
    """A simple click (no drag) must keep the existing pan-to-point behavior
    and NOT engage the zoom/highlight feature."""
    route_id = _upload_via_api(server_url)
    page.goto(f"{server_url}/route/{route_id}")
    _wait_for_main_ready(page)

    b = _plot_bounds(page)
    mid_y = (b["plot_top"] + b["plot_bottom"]) / 2
    mid_x = (b["plot_left"] + b["plot_right"]) / 2
    page.mouse.click(mid_x, mid_y)

    # Reset button must stay hidden.
    expect(page.locator(".profile-reset-zoom")).to_be_hidden()


def test_legend_gradient_distribution_populated(page, server_url):
    """Each legend band must show a non-empty distance percentage.

    The legend label format is '<range> / <angles> (<pct>%)'. Computing <pct>
    reads points[i].gradient; if gradients weren't set, the percentages would
    all be '0.0%' (computeGradDist would miss every point and return {}).
    """
    import re
    route_id = _upload_via_api(server_url)
    page.goto(f"{server_url}/route/{route_id}")
    expect(page.locator("#legend .legend-item").first).to_be_visible(timeout=10000)
    labels = page.locator("#legend .legend-item").all_text_contents()
    pct_re = re.compile(r"\(([-\d.]+)%\)")
    pcts = []
    for lbl in labels:
        m = pct_re.search(lbl)
        assert m, f"legend item missing percentage: {lbl!r}"
        pcts.append(float(m.group(1)))
    # The percentages across all bands must sum to ~100% of the track distance.
    assert abs(sum(pcts) - 100.0) < 1.0, f"legend band percentages don't total 100%: {pcts}"
