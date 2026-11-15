"""M7 mobile visual regression (iPhone 13 emulation, 390x844).

Baselines live in tests/fixtures/mobile-screenshots/. Regenerate with
UPDATE_MOBILE_SNAPSHOTS=1. The map is masked (tiles are not deterministic
offline). Uses its own isolated server so the library contents are fixed.
"""

import os
import socket
import subprocess
import time

import pytest
import requests as http_requests

Image = pytest.importorskip("PIL.Image")
ImageChops = pytest.importorskip("PIL.ImageChops")

from test_ui_mobile import make_route

SNAP_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "mobile-screenshots")
THRESHOLD = 0.002  # fraction of differing pixels
FREEZE_CSS = (
    "*,*::before,*::after{transition:none!important;animation:none!important;"
    "caret-color:transparent!important}"
)


@pytest.fixture(scope="module")
def vis_server(tmp_path_factory):
    with socket.socket() as s:
        s.bind(("", 0))
        port = s.getsockname()[1]
    data_dir = str(tmp_path_factory.mktemp("visual_data"))
    proc = subprocess.Popen(
        [".venv/bin/python", "-c",
         f"from server import create_app; create_app({{'DATA_DIR': '{data_dir}', "
         f"'BACKUP_ENABLED': False}}).run(port={port})"],
        env={**os.environ, "DATA_DIR": data_dir, "BACKUP_ENABLED": "false"},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://localhost:{port}"
    for _ in range(40):
        try:
            http_requests.get(url, timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    yield url
    proc.terminate()
    proc.wait()


@pytest.fixture
def vpage(playwright, vis_server):
    device = playwright.devices["iPhone 13"]
    browser = playwright.chromium.launch()
    context = browser.new_context(**device, locale="en-GB", timezone_id="Australia/Brisbane")
    # Never depend on the network: tiles (masked anyway) can stall "networkidle".
    context.route(lambda u: "tile" in u.split("/")[2], lambda r: r.abort())
    # Never depend on live geocoding/routing.
    context.route("**/api/geocode*", lambda r: r.abort())
    context.route("**/api/route/**", lambda r: r.abort())
    page = context.new_page()
    page.set_viewport_size({"width": 390, "height": 844})
    yield page
    context.close()
    browser.close()


def _shot(page, extra_masks=()):
    try:  # best effort; a stalled external request must not fail the shot
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass
    page.add_style_tag(content=FREEZE_CSS)
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(600)
    masks = [page.locator(s) for s in ("#map", ".meta-val", *extra_masks)]
    return page.screenshot(mask=masks, mask_color="#808080", animations="disabled")


def _compare(png_bytes, name, tmp_path):
    os.makedirs(SNAP_DIR, exist_ok=True)
    base = os.path.join(SNAP_DIR, f"{name}.png")
    new = tmp_path / f"{name}.new.png"
    new.write_bytes(png_bytes)
    if os.environ.get("UPDATE_MOBILE_SNAPSHOTS"):
        with open(base, "wb") as f:
            f.write(png_bytes)
        return
    if not os.path.exists(base):
        with open(base, "wb") as f:
            f.write(png_bytes)
        if os.environ.get("CI"):
            pytest.fail(f"Missing baseline {base}; created it - commit it and re-run.")
        return
    a = Image.open(base).convert("RGB")
    b = Image.open(new).convert("RGB")
    assert a.size == b.size, f"{name}: size {b.size} != baseline {a.size}"
    diff = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > 16 else 0)
    changed = diff.histogram()[255]
    frac = changed / (a.size[0] * a.size[1])
    assert frac <= THRESHOLD, (
        f"{name}: {frac:.2%} pixels differ (> {THRESHOLD:.0%}); new shot at {new}"
    )


def test_visual_library(vpage, vis_server, tmp_path):
    for t in ("Alpha loop", "Bravo ridge", "Charlie coast"):
        make_route(vis_server, title=t)
        time.sleep(1.1)  # uploaded_at has 1s resolution; keep the card order fixed
    vpage.goto(f"{vis_server}/")
    vpage.wait_for_timeout(800)
    _compare(_shot(vpage), "library", tmp_path)


def test_visual_analysis(vpage, vis_server, tmp_path):
    rid = make_route(vis_server, title="Analysis route")
    vpage.goto(f"{vis_server}/route/{rid}")
    vpage.wait_for_timeout(1500)
    _compare(_shot(vpage), "analysis", tmp_path)


def test_visual_create(vpage, vis_server, tmp_path):
    rid = make_route(vis_server, n_waypoints=3, title="Create route")
    vpage.goto(f"{vis_server}/create?route_id={rid}")
    vpage.wait_for_function("() => window.__appState && window.__appState.map")
    vpage.wait_for_selector(".sheet-handle", state="attached")
    vpage.wait_for_timeout(800)
    _compare(_shot(vpage), "create", tmp_path)
