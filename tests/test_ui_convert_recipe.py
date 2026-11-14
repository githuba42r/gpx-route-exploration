"""Playwright E2E for 'Convert to recipe' on the Analysis page."""

import os
import requests as http_requests
from playwright.sync_api import expect

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _upload_sample(server_url, title="convert-me"):
    with open(os.path.join(FIXTURES, "sample.gpx"), "rb") as f:
        r = http_requests.post(
            f"{server_url}/api/routes",
            files={"file": ("sample.gpx", f.read())},
            data={"title": title},
        )
    return r.json()["id"]


def _open(page, server_url, rid):
    page.set_viewport_size({"width": 1280, "height": 1000})
    page.goto(f"{server_url}/route/{rid}")
    expect(page.locator("#btn-open-edit")).to_be_visible(timeout=10000)


def test_gpx_only_route_offers_convert_and_disabled_edit(page, server_url):
    rid = _upload_sample(server_url)
    _open(page, server_url, rid)
    expect(page.locator("#btn-convert-recipe")).to_be_visible()
    expect(page.locator("#btn-open-edit")).to_be_disabled()
    assert page.locator("#btn-open-edit").get_attribute("title") == \
        "Convert to a recipe first to edit this route"


def test_convert_default_lands_on_create_with_six_rows(page, server_url):
    rid = _upload_sample(server_url)
    _open(page, server_url, rid)
    page.locator("#btn-convert-recipe").click()
    expect(page.locator("#convert-overlay")).to_be_visible()
    expect(page.locator("#convert-count")).to_have_value("6")
    assert "lossy" in page.locator("#convert-overlay").inner_text().lower()
    page.locator("#convert-confirm").click()
    page.wait_for_url(f"**/create?route_id={rid}*", timeout=10000)
    expect(page.locator(".wpe-item")).to_have_count(6, timeout=10000)
    page.goto(f"{server_url}/route/{rid}")
    expect(page.locator("a#btn-open-edit")).to_be_visible(timeout=10000)
    expect(page.locator("#btn-convert-recipe")).to_have_count(0)


def test_convert_custom_count(page, server_url):
    rid = _upload_sample(server_url)
    _open(page, server_url, rid)
    page.locator("#btn-convert-recipe").click()
    page.locator("#convert-count").fill("4")
    page.locator("#convert-confirm").click()
    page.wait_for_url(f"**/create?route_id={rid}*", timeout=10000)
    expect(page.locator(".wpe-item")).to_have_count(4, timeout=10000)


def test_convert_error_is_shown_and_dialog_stays_open(page, server_url):
    rid = _upload_sample(server_url)
    _open(page, server_url, rid)
    page.route(
        "**/api/routes/*/convert-to-recipe",
        lambda route: route.fulfill(
            status=400, content_type="application/json", body='{"error": "bad"}'),
    )
    page.locator("#btn-convert-recipe").click()
    page.locator("#convert-confirm").click()
    expect(page.locator("#convert-error")).to_have_text("bad")
    expect(page.locator("#convert-overlay")).to_be_visible()
    expect(page.locator("#convert-confirm")).to_be_enabled()


def test_escape_and_cancel_close_the_dialog(page, server_url):
    rid = _upload_sample(server_url)
    _open(page, server_url, rid)
    page.locator("#btn-convert-recipe").click()
    expect(page.locator("#convert-overlay")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("#convert-overlay")).to_have_count(0)
    page.locator("#btn-convert-recipe").click()
    page.locator("#convert-cancel").click()
    expect(page.locator("#convert-overlay")).to_have_count(0)


def test_recipe_route_has_no_convert_button(page, server_url):
    from tests.test_ui_edit_panel import _create_recipe_route
    rid = _create_recipe_route(server_url)
    _open(page, server_url, rid)
    expect(page.locator("a#btn-open-edit")).to_be_visible()
    expect(page.locator("#btn-convert-recipe")).to_have_count(0)


def test_double_activation_posts_once(page, server_url):
    rid = _upload_sample(server_url)
    _open(page, server_url, rid)
    posts = []
    held = []

    def handler(route):
        posts.append(1)
        held.append(route)

    page.route("**/api/routes/*/convert-to-recipe", handler)
    page.locator("#btn-convert-recipe").click()
    page.locator("#convert-confirm").click()
    expect(page.locator("#convert-confirm")).to_have_class("convert-btn convert-btn-primary is-busy")
    page.locator("#convert-confirm").dispatch_event("click")
    page.locator("#convert-count").press("Enter")
    page.wait_for_timeout(300)
    assert len(posts) == 1
    held[0].continue_()
    page.wait_for_url(f"**/create?route_id={rid}*", timeout=10000)
    assert len(posts) == 1


AUTO_ON = "localStorage.setItem('gpx-create-auto-generate', '1')"


def _count_generate(page):
    calls = []

    def handler(route):
        calls.append(1)
        route.fulfill(status=500, content_type="application/json", body='{"error": "x"}')

    page.route("**/api/routes/*/generate", handler)
    return calls


def test_convert_does_not_auto_generate_on_arrival(page, server_url):
    rid = _upload_sample(server_url)
    original = http_requests.get(f"{server_url}/api/gpx/{rid}").content
    page.add_init_script(AUTO_ON)
    calls = _count_generate(page)
    _open(page, server_url, rid)
    page.locator("#btn-convert-recipe").click()
    page.locator("#convert-confirm").click()
    page.wait_for_url(f"**/create?route_id={rid}*", timeout=10000)
    expect(page.locator(".wpe-item")).to_have_count(6, timeout=10000)
    page.wait_for_timeout(1500)
    assert calls == []
    assert http_requests.get(f"{server_url}/api/gpx/{rid}").content == original
    assert "converted" not in page.url


def test_auto_generate_still_fires_on_a_normal_create_load(page, server_url):
    rid = _upload_sample(server_url, title="normal")
    http_requests.post(f"{server_url}/api/routes/{rid}/convert-to-recipe", json={"count": 4})
    page.add_init_script(AUTO_ON)
    calls = _count_generate(page)
    page.goto(f"{server_url}/create?route_id={rid}")
    expect(page.locator(".wpe-item")).to_have_count(4, timeout=10000)
    page.wait_for_timeout(1500)
    assert len(calls) >= 1


# The pageshow/bfcache reload guard is not covered by a test: headless
# Chromium under Playwright does not reliably enable bfcache.
