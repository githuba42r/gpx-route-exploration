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


def test_new_route_button_navigates_to_create(page, server_url):
    """The '+ New Route' button added in M1 Task 16 takes the user to
    /create, where the Create page auto-creates a recipe-only route and
    rewrites the URL with ?route_id=<n>."""
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(server_url)
    expect(page.locator("button.new-route-btn")).to_be_visible()
    page.locator("button.new-route-btn").click()
    # Ends up on /create?route_id=<n>.
    page.wait_for_url(lambda url: url.rstrip('/').endswith('/create') or '/create?' in url,
                       timeout=5000)
    assert '/create' in page.url


def test_new_route_button_lives_in_sidebar_above_categories(page, server_url):
    """+ New Route now sits in the sidebar above the category panel —
    not inside the main route list column."""
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(server_url)
    sidebar_btn = page.locator("#sidebar button.new-route-btn")
    expect(sidebar_btn).to_be_visible()
    # Make sure it's NOT inside #route-list anymore.
    assert page.locator("#route-list button.new-route-btn").count() == 0

    # The sidebar slot must come before #category-panel in DOM order.
    ok = page.evaluate(
        """() => {
            const btn = document.querySelector('#sidebar-new-route');
            const cats = document.querySelector('#category-panel');
            if (!btn || !cats) return false;
            return btn.compareDocumentPosition(cats) & Node.DOCUMENT_POSITION_FOLLOWING;
        }"""
    )
    assert ok, "New Route button must appear above the Category panel in the sidebar"


def test_upload_area_is_anchored_at_sidebar_bottom(page, server_url):
    """The GPX drop zone moved from the top of the route list to the
    bottom of the sidebar."""
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(server_url)
    expect(page.locator("#sidebar #upload-area")).to_be_visible()
    # It is no longer inside #route-list.
    assert page.locator("#route-list #upload-area").count() == 0

    # And it's the last child of #sidebar (the flex spacer is above it).
    is_last = page.evaluate(
        """() => {
            const side = document.querySelector('#sidebar');
            return side && side.lastElementChild
                && side.lastElementChild.id === 'upload-area';
        }"""
    )
    assert is_last, "Upload area must be the last child in the sidebar"
