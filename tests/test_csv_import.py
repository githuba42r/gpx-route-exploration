import pytest

from server.csv_import import CsvImportError, parse_csv

M = {"name": "name", "address": "address", "lat": "lat", "lon": "lon", "description": "desc"}


def p(text, mapping=M, max_rows=100, enc="utf-8"):
    return parse_csv(text.encode(enc), mapping, max_rows=max_rows)


def test_direct_coordinates_row():
    rows = p("name,address,lat,lon,desc\nA,,51.5,-0.12,hello\n")
    assert rows == [{"index": 0, "name": "A", "address": None, "lat": 51.5,
                     "lon": -0.12, "description": "hello", "error": None}]


def test_address_row_needs_geocoding():
    r = p("name,address,lat,lon,desc\nA,1 Main St,,,\n")[0]
    assert r["address"] == "1 Main St"
    assert r["lat"] is None and r["lon"] is None and r["error"] is None
    assert r["description"] is None


def test_name_falls_back_to_address_then_stop_number():
    rows = p("name,address,lat,lon,desc\n,1 Main St,,,\n,,1,2,\n")
    assert rows[0]["name"] == "1 Main St"
    assert rows[1]["name"] == "Stop 2"


def test_failed_rows_have_reason():
    rows = p("name,address,lat,lon,desc\nA,,,,\nB,,abc,1,\nC,1 Main St,95,1,\n")
    assert rows[0]["error"] == "no address or coordinates"
    assert rows[1]["error"] == "invalid coordinates"
    assert rows[2]["error"] is None
    assert rows[2]["lat"] is None and rows[2]["lon"] is None


def test_bom_semicolon_and_quoted_cells():
    text = 'name;address;lat;lon;desc\n"A; B";"1 Main\nSt";;;x\n'
    rows = p(text, enc="utf-8-sig")
    assert len(rows) == 1
    assert rows[0]["name"] == "A; B"
    assert rows[0]["address"] == "1 Main\nSt"
    assert rows[0]["description"] == "x"


def test_ragged_row_and_blank_lines():
    rows = p("name,address,lat,lon,desc\n\nA,1 Main St\n\n\nB,,1,2\n")
    assert [r["index"] for r in rows] == [0, 1]
    assert rows[0]["address"] == "1 Main St" and rows[0]["error"] is None
    assert rows[1]["lat"] == 1.0


def test_empty_header_only_and_unknown_header_raise():
    with pytest.raises(CsvImportError):
        parse_csv(b"", M, max_rows=10)
    with pytest.raises(CsvImportError):
        p("name,address,lat,lon,desc\n")
    with pytest.raises(CsvImportError, match="nope"):
        p("name,address\nA,b\n", {"address": "nope"})


def test_mapping_without_address_or_coordinates_raises():
    with pytest.raises(CsvImportError):
        p("name,lat\nA,1\n", {"name": "name", "lat": "lat"})


def test_unknown_mapping_key_raises():
    with pytest.raises(CsvImportError):
        p("name,address\nA,b\n", {"address": "address", "bogus": "name"})


def test_over_max_rows_raises():
    with pytest.raises(CsvImportError):
        p("address\na\nb\nc\n", {"address": "address"}, max_rows=2)


def test_latin1_fallback():
    rows = p("name,address\ncafé,x\n", {"name": "name", "address": "address"}, enc="latin-1")
    assert rows[0]["name"] == "café"
