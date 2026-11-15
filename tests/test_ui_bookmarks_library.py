"""M8 Task 4: Library Bookmarks tab, editor modal, new-bookmark modal."""

import io

import pytest
import requests as http_requests
from PIL import Image
from playwright.sync_api import expect


@pytest.fixture(autouse=True)
def clean_bookmarks(server_url):
    def wipe():
        for b in http_requests.get(f"{server_url}/api/bookmarks").json():
            http_requests.delete(f"{server_url}/api/bookmarks/{b['id']}")
    wipe()
    yield
    wipe()


@pytest.fixture
def mobile_page(playwright):
    browser = playwright.chromium.launch()
    context = browser.new_context(
        viewport={"width": 390, "height": 844}, device_scale_factor=3,
        is_mobile=True, has_touch=True,
    )
    page = context.new_page()
    yield page
    context.close()
    browser.close()


def png_bytes(color):
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), color).save(buf, "PNG")
    return buf.getvalue()


def seed(server_url, name="Spot", lat=-27.4705, lon=153.026, tags=None, description=""):
    r = http_requests.post(
        f"{server_url}/api/bookmarks",
        json={"name": name, "lat": lat, "lon": lon, "description": description,
              "tags": tags or []},
    )
    assert r.status_code == 201, r.text
    return r.json()


def add_photo(server_url, bid, color):
    r = http_requests.post(
        f"{server_url}/api/bookmarks/{bid}/photos",
        files={"file": ("p.png", png_bytes(color), "image/png")},
    )
    assert r.status_code == 201, r.text
    return r.json()


def photo_file(tmp_path, name, color):
    p = tmp_path / name
    p.write_bytes(png_bytes(color))
    return str(p)


def open_bookmarks(page, server_url):
    page.goto(f"{server_url}/#bookmarks")
    expect(page.locator("#tab-bookmarks")).to_have_attribute("aria-selected", "true")


def test_tab_switch_keeps_hash(page, server_url):
    seed(server_url, "Alpha")
    page.goto(server_url)
    expect(page.locator("#tab-routes")).to_have_attribute("aria-selected", "true")
    page.locator("#tab-bookmarks").click()
    expect(page.locator(".bookmark-card")).to_have_count(1)
    assert page.evaluate("location.hash") == "#bookmarks"
    expect(page.locator("#routes-container")).to_be_hidden()
    page.reload()
    expect(page.locator("#tab-bookmarks")).to_have_attribute("aria-selected", "true")
    expect(page.locator(".bookmark-card")).to_have_count(1)
    page.go_back()
    expect(page.locator("#tab-routes")).to_have_attribute("aria-selected", "true")
    expect(page.locator("#routes-container")).to_be_visible()


def test_card_content_placeholder_and_thumb(page, server_url):
    a = seed(server_url, "Plain", lat=-27.123456, lon=153.5, tags=["cafe", "view"])
    b = seed(server_url, "WithPhoto")
    add_photo(server_url, b["id"], "red")
    open_bookmarks(page, server_url)
    cards = page.locator(".bookmark-card")
    expect(cards).to_have_count(2)
    plain = cards.filter(has_text="Plain")
    expect(plain).to_contain_text("-27.12346, 153.50000")
    expect(plain.locator(".bookmark-tag")).to_have_text(["cafe", "view"])
    expect(plain.locator(".bookmark-thumb-placeholder")).to_have_count(1)
    expect(plain.locator("img")).to_have_count(0)
    photo = cards.filter(has_text="WithPhoto")
    expect(photo.locator("img")).to_have_count(1)
    expect(photo.locator(".bookmark-thumb-placeholder")).to_have_count(0)
    page.wait_for_function(
        "document.querySelector('.bookmark-card img').naturalWidth > 0")


def test_search_filters_name_and_tag(page, server_url):
    seed(server_url, "Beach hut", tags=["coast"])
    seed(server_url, "Summit", tags=["alpine"])
    open_bookmarks(page, server_url)
    expect(page.locator(".bookmark-card")).to_have_count(2)
    page.locator("#bookmark-search").fill("beach")
    expect(page.locator(".bookmark-card")).to_have_count(1)
    page.locator("#bookmark-search").fill("alpin")
    expect(page.locator(".bookmark-card")).to_have_count(1)
    expect(page.locator(".bookmark-card")).to_contain_text("Summit")
    page.locator("#bookmark-search").fill("zzz")
    expect(page.locator(".bookmark-card")).to_have_count(0)


def test_sort_by_name(page, server_url):
    seed(server_url, "Bravo")
    seed(server_url, "Alpha")
    open_bookmarks(page, server_url)
    page.locator("#bookmark-sort").select_option("name")
    expect(page.locator(".bookmark-card .bookmark-name")).to_have_text(["Alpha", "Bravo"])


def test_sidebar_tag_click_filters_bookmarks(page, server_url):
    seed(server_url, "Beach hut", tags=["coast"])
    seed(server_url, "Summit", tags=["alpine"])
    open_bookmarks(page, server_url)
    expect(page.locator(".bookmark-card")).to_have_count(2)
    page.locator("#tag-cloud-container .tag-chip", has_text="coast").click()
    expect(page.locator(".bookmark-card")).to_have_count(1)
    expect(page.locator(".bookmark-card")).to_contain_text("Beach hut")
    page.locator("#tag-cloud-container .tag-chip", has_text="coast").click()
    expect(page.locator(".bookmark-card")).to_have_count(2)


def test_new_bookmark_double_click_save_posts_once(page, server_url):
    posts = []
    page.on("request", lambda r: posts.append(r)
            if r.method == "POST" and r.url.endswith("/api/bookmarks") else None)
    open_bookmarks(page, server_url)
    page.locator("#btn-new-bookmark").click()
    modal = page.locator("#bookmark-create")
    expect(modal).to_be_visible()
    save = modal.locator(".bm-save")
    expect(save).to_be_disabled()
    modal.locator(".bm-name").fill("Clicked spot")
    expect(save).to_be_disabled()  # still no coordinates
    page.locator("#bookmark-create-map").click(position={"x": 120, "y": 100})
    lat = modal.locator(".bm-lat").input_value()
    lon = modal.locator(".bm-lon").input_value()
    assert lat and lon
    expect(save).to_be_enabled()
    save.dblclick()
    expect(page.locator(".bookmark-card")).to_have_count(1)
    expect(modal).to_be_hidden()
    page.wait_for_timeout(300)
    assert len(posts) == 1
    listed = http_requests.get(f"{server_url}/api/bookmarks").json()
    assert len(listed) == 1 and listed[0]["name"] == "Clicked spot"
    assert abs(listed[0]["lat"] - float(lat)) < 1e-4


def test_new_bookmark_typed_coords_and_validation(page, server_url):
    open_bookmarks(page, server_url)
    page.locator("#btn-new-bookmark").click()
    modal = page.locator("#bookmark-create")
    modal.locator(".bm-name").fill("Typed")
    modal.locator(".bm-lat").fill("95")
    modal.locator(".bm-lon").fill("10")
    expect(modal.locator(".bm-save")).to_be_disabled()
    modal.locator(".bm-lat").fill("-27.5")
    expect(modal.locator(".bm-save")).to_be_enabled()


def test_editor_edit_persists_after_reload(page, server_url):
    seed(server_url, "Old name", tags=["one"])
    open_bookmarks(page, server_url)
    page.locator(".bookmark-card").first.click()
    ed = page.locator("#bookmark-editor")
    expect(ed).to_be_visible()
    ed.locator(".bm-name").fill("New name")
    ed.locator(".bm-desc").fill("A description")
    ed.locator(".bm-tags input").fill("two")
    ed.locator(".bm-tags input").press("Enter")
    ed.locator(".bm-save").click()
    expect(ed).to_be_hidden()
    page.reload()
    card = page.locator(".bookmark-card")
    expect(card).to_contain_text("New name")
    expect(card.locator(".bookmark-tag")).to_have_text(["one", "two"])
    card.click()
    expect(page.locator("#bookmark-editor .bm-desc")).to_have_value("A description")


def test_editor_photos_upload_reorder_delete(page, server_url, tmp_path):
    b = seed(server_url, "Gallery")
    open_bookmarks(page, server_url)
    page.locator(".bookmark-card").first.click()
    ed = page.locator("#bookmark-editor")
    f1 = photo_file(tmp_path, "a.png", "red")
    f2 = photo_file(tmp_path, "b.png", "blue")
    ed.locator("input[type=file]").set_input_files([f1, f2])
    items = ed.locator(".bm-photo")
    expect(items).to_have_count(2)
    ids = lambda: [p["id"] for p in http_requests.get(
        f"{server_url}/api/bookmarks/{b['id']}").json()["photos"]]
    first_ids = ids()
    assert len(first_ids) == 2
    assert [int(x) for x in items.evaluate_all(
        "els => els.map(e => e.dataset.photoId)")] == first_ids
    # drag second before first
    items.nth(1).locator(".bm-photo-handle").drag_to(items.nth(0).locator(".bm-photo-handle"))
    page.wait_for_function(
        "ids => document.querySelectorAll('#bookmark-editor .bm-photo')[0].dataset.photoId == ids[1]",
        arg=[str(i) for i in first_ids])
    page.wait_for_timeout(400)
    assert ids() == list(reversed(first_ids))
    # delete one
    items.nth(0).locator(".bm-photo-delete").click()
    expect(items).to_have_count(1)
    page.wait_for_timeout(300)
    assert len(ids()) == 1


def test_editor_delete_bookmark_via_confirm(page, server_url):
    seed(server_url, "Doomed")
    open_bookmarks(page, server_url)
    page.locator(".bookmark-card").first.click()
    page.locator("#bookmark-editor .bm-delete").click()
    expect(page.locator("#confirm-modal-overlay")).to_be_visible()
    page.locator("#confirm-modal-overlay .btn-danger").click()
    expect(page.locator(".bookmark-card")).to_have_count(0)
    assert http_requests.get(f"{server_url}/api/bookmarks").json() == []


def test_user_text_rendered_as_text(page, server_url):
    evil = "<img src=x onerror=window.__pwned=1>"
    seed(server_url, evil, tags=["<b>x</b>"], description=evil)
    open_bookmarks(page, server_url)
    expect(page.locator(".bookmark-card .bookmark-name")).to_have_text(evil)
    expect(page.locator(".bookmark-card .bookmark-tag")).to_have_text("<b>x</b>")
    page.locator(".bookmark-card").first.click()
    expect(page.locator("#bookmark-editor .bm-name")).to_have_value(evil)
    page.wait_for_timeout(300)
    assert page.evaluate("window.__pwned") is None
    assert page.locator("#bookmarks-container img[src='x']").count() == 0


def test_mobile_layout(mobile_page, server_url):
    for i in range(3):
        seed(server_url, f"Mobile {i}", tags=["a", "b", "c"])
    page = mobile_page
    page.goto(f"{server_url}/#bookmarks")
    cards = page.locator(".bookmark-card")
    expect(cards).to_have_count(3)
    boxes = [cards.nth(i).bounding_box() for i in range(3)]
    assert boxes[0]["x"] == boxes[1]["x"] == boxes[2]["x"]
    assert boxes[0]["y"] < boxes[1]["y"] < boxes[2]["y"]
    sw, cw = page.evaluate(
        "[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
    assert sw <= cw
    for sel in ("#tab-routes", "#tab-bookmarks", "#btn-new-bookmark"):
        bb = page.locator(sel).bounding_box()
        assert bb["height"] >= 44, sel
    cards.first.click()
    ed = page.locator("#bookmark-editor")
    expect(ed).to_be_visible()
    bb = ed.bounding_box()
    assert bb["x"] >= 0 and bb["x"] + bb["width"] <= 390
    assert bb["y"] >= 0 and bb["y"] + bb["height"] <= 844
    ed.locator(".bm-close").click()
    page.locator("#btn-new-bookmark").click()
    cr = page.locator("#bookmark-create")
    expect(cr).to_be_visible()
    bb = cr.bounding_box()
    assert bb["x"] >= 0 and bb["x"] + bb["width"] <= 390
    assert bb["y"] >= 0 and bb["y"] + bb["height"] <= 844
