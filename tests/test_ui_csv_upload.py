import re

import requests as http_requests
from playwright.sync_api import expect


def _write_csv(tmp_path, text, name="places.csv"):
    p = tmp_path / name
    p.write_text(text)
    return str(p)


def test_library_csv_import_creates_route_and_lands_on_create_page(
    page, server_url, tmp_path
):
    path = _write_csv(
        tmp_path,
        "Name,Lat,Lon\n"
        "A,51.50,-0.10\nB,51.51,-0.11\nC,51.52,-0.12\nD,51.53,-0.13\n"
        "Broken,,\n",
    )
    page.goto(server_url)
    page.locator("#btn-import-csv").click()
    page.set_input_files("#csv-file-input", path)
    expect(page.locator("#csv-map-lat")).to_have_value("Lat")
    expect(page.locator("#csv-map-lon")).to_have_value("Lon")
    expect(page.locator("#csv-map-name")).to_have_value("Name")
    expect(page.locator("#csv-preview")).to_contain_text("Broken")
    page.locator("#csv-import-start").click()
    page.wait_for_url(re.compile(r".*/create\?route_id=\d+"), timeout=20000)
    route_id = re.search(r"route_id=(\d+)", page.url).group(1)
    wps = http_requests.get(f"{server_url}/api/routes/{route_id}/waypoints").json()
    assert len(wps) == 5
    included = [w for w in wps if w["included"]]
    excluded = [w for w in wps if not w["included"]]
    assert [w["name"] for w in included] == ["A", "B", "C", "D"]
    assert len(excluded) == 1
    assert "Import failed:" in excluded[0]["description"]


def test_import_start_disabled_until_a_usable_mapping(page, server_url, tmp_path):
    path = _write_csv(tmp_path, "Name,Address\nX,1 High St\n")
    page.goto(server_url)
    page.locator("#btn-import-csv").click()
    page.set_input_files("#csv-file-input", path)
    for field in ("name", "address", "lat", "lon", "description"):
        page.select_option(f"#csv-map-{field}", "")
    expect(page.locator("#csv-import-start")).to_be_disabled()
    page.select_option("#csv-map-address", "Address")
    expect(page.locator("#csv-import-start")).to_be_enabled()


def test_server_rejection_is_shown_in_the_dialog(page, server_url, tmp_path):
    path = _write_csv(tmp_path, "Name,Lat,Lon\n")
    page.goto(server_url)
    page.locator("#btn-import-csv").click()
    page.set_input_files("#csv-file-input", path)
    page.locator("#csv-import-start").click()
    expect(page.locator("#csv-import-error")).to_have_text(
        "The CSV file has a header but no data rows"
    )
    expect(page.locator("#csv-import-overlay")).to_be_visible()


def test_stream_failure_shows_recovery_link(page, server_url, tmp_path):
    path = _write_csv(tmp_path, "Name,Lat,Lon\nA,51.50,-0.10\nB,51.51,-0.11\n")
    page.route(
        "**/api/geocode/csv/*/stream",
        lambda route: route.fulfill(status=500, body="x"),
    )
    page.goto(server_url)
    page.locator("#btn-import-csv").click()
    page.set_input_files("#csv-file-input", path)
    page.locator("#csv-import-start").click()
    expect(page.locator("#csv-import-error")).to_be_visible()
    expect(page.locator("#csv-import-error")).to_contain_text("connection")
    link = page.locator("#csv-import-open-route")
    expect(link).to_be_visible()
    assert re.search(r"/create\?route_id=\d+$", link.get_attribute("href"))
    expect(page.locator("#csv-import-start")).to_be_disabled()
    page.locator("#csv-import-close").click()
    expect(page.locator("#csv-import-overlay")).to_have_count(0)


# ---------------------------------------------------------------- Create page


def _goto_create(page, server_url, route_id=None):
    page.set_viewport_size({"width": 1280, "height": 1000})
    q = f"?route_id={route_id}" if route_id else ""
    page.goto(f"{server_url}/create{q}")
    page.wait_for_function(
        "() => new URL(location.href).searchParams.get('route_id') !== null",
        timeout=5000,
    )
    page.wait_for_function("() => window.__appReady === true", timeout=10000)


def _click_map_at(page, fx, fy):
    box = page.locator("#map").bounding_box()
    page.mouse.click(box["x"] + box["width"] * fx, box["y"] + box["height"] * fy)


def _coord_csv(n, prefix="P"):
    lines = ["Name,Lat,Lon"]
    for i in range(n):
        lines.append(f"{prefix}{i + 1},{51.50 + i * 0.01:.2f},{-0.10 - i * 0.01:.2f}")
    return "\n".join(lines) + "\n"


def _import_on_create(page, path):
    page.locator("#btn-import-csv").click()
    page.set_input_files("#csv-file-input", path)
    page.locator("#csv-import-start").click()


def test_create_page_append_adds_rows_after_manual_waypoints(
    page, server_url, tmp_path
):
    _goto_create(page, server_url)
    _click_map_at(page, 0.3, 0.4)
    expect(page.locator(".wpe-item")).to_have_count(1)
    _click_map_at(page, 0.6, 0.4)
    expect(page.locator(".wpe-item")).to_have_count(2)
    _import_on_create(page, _write_csv(tmp_path, _coord_csv(5)))
    expect(page.locator("#csv-import-overlay")).to_have_count(0, timeout=20000)
    expect(page.locator(".wpe-item")).to_have_count(7)
    assert re.search(r"route_id=\d+", page.url)
    expect(page.locator("#btn-gen-primary")).to_be_enabled()


def test_append_to_saved_route_via_edit_url(page, server_url, tmp_path):
    rid = http_requests.post(
        f"{server_url}/api/routes", json={"title": "append-saved"}
    ).json()["id"]
    for i in range(4):
        http_requests.post(
            f"{server_url}/api/routes/{rid}/waypoints",
            json={"name": f"Orig{i + 1}", "lat": 40.0 + i * 0.01,
                  "lon": 10.0, "kind": "waypoint"},
        )
    _goto_create(page, server_url, rid)
    expect(page.locator(".wpe-item")).to_have_count(4)
    _import_on_create(page, _write_csv(tmp_path, _coord_csv(3, "New")))
    expect(page.locator("#csv-import-overlay")).to_have_count(0, timeout=20000)
    expect(page.locator(".wpe-item")).to_have_count(7)
    wps = http_requests.get(f"{server_url}/api/routes/{rid}/waypoints").json()
    assert len(wps) == 7
    assert [w["name"] for w in wps] == [
        "Orig1", "Orig2", "Orig3", "Orig4", "New1", "New2", "New3"
    ]


def test_import_button_works_before_any_waypoint_exists(
    page, server_url, tmp_path
):
    _goto_create(page, server_url)
    expect(page.locator(".wpe-item")).to_have_count(0)
    _import_on_create(page, _write_csv(tmp_path, _coord_csv(3)))
    expect(page.locator("#csv-import-overlay")).to_have_count(0, timeout=20000)
    expect(page.locator(".wpe-item")).to_have_count(3)
    rid = re.search(r"route_id=(\d+)", page.url).group(1)
    wps = http_requests.get(f"{server_url}/api/routes/{rid}/waypoints").json()
    assert len(wps) == 3


def test_append_stream_failure_refresh_reloads_editor(page, server_url, tmp_path):
    _goto_create(page, server_url)
    page.route(
        "**/api/geocode/csv/*/stream",
        lambda route: route.fulfill(status=500, body="x"),
    )
    _import_on_create(page, _write_csv(tmp_path, _coord_csv(3)))
    refresh = page.locator("#csv-import-refresh")
    expect(refresh).to_be_visible(timeout=20000)
    expect(page.locator("#btn-gen-primary")).to_be_disabled()
    refresh.click()
    expect(page.locator("#csv-import-overlay")).to_have_count(0)
    expect(page.locator(".wpe-item")).to_have_count(3, timeout=20000)
    expect(page.locator("#btn-gen-primary")).to_be_enabled()


def test_escape_closes_the_import_dialog(page, server_url):
    page.goto(server_url)
    page.locator("#btn-import-csv").click()
    expect(page.locator("#csv-import-overlay")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("#csv-import-overlay")).to_have_count(0)


_COUNT_KEYDOWN_JS = """
(() => {
  const live = new Set();
  const key = (t, l, c) => t + '|' + (c === true || (c && c.capture) ? 1 : 0);
  const handlers = new Map();
  const add = document.addEventListener.bind(document);
  const rem = document.removeEventListener.bind(document);
  document.addEventListener = (t, l, c) => {
    if (t === 'keydown' && l) {
      const k = key(t, l, c);
      if (!handlers.has(l)) handlers.set(l, new Set());
      handlers.get(l).add(k);
      live.add(l);
    }
    return add(t, l, c);
  };
  document.removeEventListener = (t, l, c) => {
    if (t === 'keydown' && l) live.delete(l);
    return rem(t, l, c);
  };
  window.__keydownCount = () => live.size;
})();
"""


def test_escape_listener_does_not_stack(page, server_url):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.add_init_script(_COUNT_KEYDOWN_JS)
    page.goto(server_url)
    count = lambda: page.evaluate("window.__keydownCount()")  # noqa: E731
    base = count()

    page.locator("#btn-import-csv").click()
    assert count() == base + 1

    # three open/close cycles, alternating Cancel and Escape, return to baseline
    page.locator("#csv-import-close").click()
    assert count() == base
    for closer in ("escape", "cancel", "escape"):
        page.locator("#btn-import-csv").click()
        assert count() == base + 1
        if closer == "escape":
            page.keyboard.press("Escape")
        else:
            page.locator("#csv-import-close").click()
        expect(page.locator("#csv-import-overlay")).to_have_count(0)
        assert count() == base

    # a real re-open while the dialog is open replaces it without leaking
    page.locator("#btn-import-csv").click()
    page.evaluate("document.getElementById('btn-import-csv').click()")
    assert count() == base + 1
    expect(page.locator("#csv-import-overlay")).to_have_count(1)
    page.keyboard.press("Escape")
    expect(page.locator("#csv-import-overlay")).to_have_count(0)
    assert count() == base
    page.keyboard.press("Escape")
    assert errors == []
