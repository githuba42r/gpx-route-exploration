"""CSV parsing and column mapping for route import."""
import csv
import io
import math

_KEYS = {"name", "address", "lat", "lon", "description"}


class CsvImportError(ValueError):
    """A user-readable problem with an uploaded CSV."""


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _float(value):
    try:
        f = float(value.strip())
    except (ValueError, AttributeError):
        return None
    return f if math.isfinite(f) else None


def parse_csv(data: bytes, mapping: dict, *, max_rows: int) -> list:
    unknown = set(mapping) - _KEYS
    if unknown:
        raise CsvImportError(f"Unknown column mapping: {', '.join(sorted(unknown))}")
    if "address" not in mapping and not ("lat" in mapping and "lon" in mapping):
        raise CsvImportError("Map an address column, or both latitude and longitude columns")

    text = _decode(data)
    if not text.strip():
        raise CsvImportError("The CSV file is empty")
    header_line = text.lstrip("\r\n").split("\n", 1)[0]
    try:
        delimiter = csv.Sniffer().sniff(header_line, delimiters=",;\t").delimiter
    except csv.Error:
        delimiter = ","

    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    try:
        records = [r for r in reader if any(c.strip() for c in r)]
    except csv.Error as exc:
        raise CsvImportError("The file is not a valid CSV") from exc
    if not records:
        raise CsvImportError("The CSV file is empty")
    header = [h.strip() for h in records[0]]
    body = records[1:]
    if not body:
        raise CsvImportError("The CSV file has a header but no data rows")

    pos = {}
    for key, col in mapping.items():
        if col not in header:
            raise CsvImportError(f"Column '{col}' not found in the CSV header")
        pos[key] = header.index(col)
    if len(body) > max_rows:
        raise CsvImportError(f"Too many rows: {len(body)} (maximum {max_rows})")

    def cell(rec, key):
        i = pos.get(key)
        return rec[i].strip() if i is not None and i < len(rec) else ""

    rows = []
    for index, rec in enumerate(body):
        address = cell(rec, "address") or None
        description = cell(rec, "description") or None
        lat_s, lon_s = cell(rec, "lat"), cell(rec, "lon")
        lat, lon, error = None, None, None
        la, lo = _float(lat_s), _float(lon_s)
        if la is not None and lo is not None and abs(la) <= 90 and abs(lo) <= 180:
            lat, lon = la, lo
        elif address:
            pass
        elif lat_s or lon_s:
            error = "invalid coordinates"
        else:
            error = "no address or coordinates"
        rows.append({
            "index": index,
            "name": cell(rec, "name") or address or f"Stop {index + 1}",
            "address": address,
            "lat": lat,
            "lon": lon,
            "description": description,
            "error": error,
        })
    return rows
