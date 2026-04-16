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
