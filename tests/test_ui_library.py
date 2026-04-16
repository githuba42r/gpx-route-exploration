import os
import requests as http_requests
from playwright.sync_api import expect

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _upload_via_api(server_url, title="Test Route"):
    with open(os.path.join(FIXTURES, "sample.gpx"), "rb") as f:
        resp = http_requests.post(
            f"{server_url}/api/routes",
            files={"file": ("sample.gpx", f)},
            data={"title": title},
        )
    return resp.json()


def test_library_loads(page, server_url):
    page.goto(server_url)
    expect(page.locator("#library-container")).to_be_visible()


def test_upload_via_ui(page, server_url):
    page.goto(server_url)
    page.locator("#upload-area input[type=file]").set_input_files(
        os.path.join(FIXTURES, "sample.gpx")
    )
    title_input = page.locator("#upload-area input[name=title]")
    title_input.fill("UI Upload Test")
    page.locator("#upload-area button[type=submit]").click()
    expect(page.locator(".route-card")).to_be_visible(timeout=5000)


def test_click_route_opens_analysis(page, server_url):
    route = _upload_via_api(server_url, "Click Test")
    page.goto(server_url)
    page.locator(".route-card").first.click()
    expect(page).to_have_url(f"{server_url}/route/{route['id']}")


def test_create_category(page, server_url):
    page.goto(server_url)
    page.locator("#category-panel input[name=cat-name]").fill("New Category")
    page.locator("#category-panel button[type=submit]").click()
    expect(page.locator("#category-panel")).to_contain_text("New Category")


def test_delete_route_inline_confirm(page, server_url):
    _upload_via_api(server_url, "Delete Me")
    page.goto(server_url)
    page.locator(".route-card .delete-btn").first.click()
    expect(page.locator("#confirm-modal-overlay")).to_be_visible()
    page.locator("#confirm-modal-overlay .confirm-yes").click()
    page.wait_for_timeout(500)
    expect(page.locator(".route-card")).to_have_count(0)


def test_delete_route_cancel(page, server_url):
    _upload_via_api(server_url, "Keep Me")
    page.goto(server_url)
    page.locator(".route-card .delete-btn").first.click()
    page.locator("#confirm-modal-overlay .confirm-no").click()
    expect(page.locator(".route-card")).to_have_count(1)
