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
