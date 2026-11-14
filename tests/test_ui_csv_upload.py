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
    expect(page.locator("#csv-import-error")).not_to_be_empty()
    expect(page.locator("#csv-import-overlay")).to_be_visible()
