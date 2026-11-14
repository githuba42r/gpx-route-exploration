# M5 — CSV Upload (new-route and append) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Repo convention: checkboxes are never ticked** — progress is tracked by commit messages plus a final `**M5 verified:**` marker at the end of this file.

**Goal:** Users can upload a CSV of stops (addresses and/or GPS coordinates) from the Library to create a new route, or from the Create page to append to the route being edited, with row-by-row progress.

**Architecture:** A new `api_geocode` blueprint accepts the CSV, validates and parses it, then starts a background thread that writes each row into `route_waypoints` (direct coordinates, or Nominatim lookup through a persistent `geocode_cache`) and publishes progress events that a Server-Sent-Events endpoint streams. The browser parses the CSV locally with PapaParse only to build the column-mapping dialog; the server re-parses with Python's `csv` module. The job registry is in memory, so production runs a single multi-threaded gunicorn worker.

**Tech Stack:** Flask, SQLite, `requests`, Python `csv`, PapaParse (npm), esbuild, Playwright.

**Spec:** `docs/superpowers/specs/2026-04-17-route-creation-design.md` §3 "Data flow — CSV import (M5)", "Persistent geocoding cache", and §5 "M5 — CSV upload" (lines ~112-150 and 303-322).

## Global Constraints

- Imported rows default to `kind='stop'`, `included=1`, placed at the end of the recipe in CSV row order.
- Failed rows are kept with `lat=NULL, lon=NULL, included=0` and a note in `description`.
- `geocode_cache (query TEXT PRIMARY KEY, lat REAL, lon REAL, display_name TEXT, created_at INTEGER NOT NULL)`; every Nominatim lookup consults it first, and a hit skips the network.
- Nominatim calls are rate-limited, configurable via `NOMINATIM_RATE_LIMIT_MS` (default 1000).
- `POST /api/geocode/csv` returns `202 { job_id, route_id }` (append mode adds `append: true`); `?route_id=<id>` selects append mode. `GET /api/geocode/csv/<job_id>/stream` is SSE: `event: row` per row, then `event: done`.
- Row event: `{ index, status, lat, lon, waypoint_id, name, error }` with `status` one of `"direct"`, `"geocoded"`, `"failed"`. Done event: `{ route_id, total, failed, created }` in new-route mode or `{ route_id, total, failed, appended }` in append mode.
- Schema changes are additive only (`CREATE TABLE IF NOT EXISTS`).
- Server config lives in `server/config.py` (`Config`) and is read from `current_app.config`.

## Review Focus

Inputs and conditions the spec implies but does not spell out. Each has a test in the task that owns the code.

1. A row with neither usable coordinates nor an address, or with out-of-range or non-numeric coordinates and no address, becomes a failed row (kept, `included=0`, note), never a crash — Tasks 2 and 3.
2. Nominatim unreachable or returning an error mid-import: the affected rows fail with a note and the job still ends with a `done` event instead of hanging — Task 3.
3. CSV quirks: UTF-8 BOM, `;` delimiter, quoted commas and newlines, header-only file, empty file, ragged rows — Task 2.
4. A file over the size cap, more rows than the cap, or an unusable mapping is rejected with a 400 (413 for size) before any route is created, so no empty route is left behind — Task 4.
5. An unknown job id, another user's job, or another user's route id returns 404; two rows with the same address cause a single Nominatim call — Tasks 1 and 4.

Decisions recorded here:
- **Limits:** `CSV_MAX_BYTES = 1048576` (1 MiB) and `CSV_MAX_ROWS = 200`, both in `Config`.
- **Header row:** the first row of the CSV is always a header, and the mapping refers to columns by header name.
- **Append mode:** a `route_id` query parameter means append; `append=1` is accepted but not required.
- **Misses and errors are not cached,** only successful lookups, so a transient Nominatim failure is not remembered.
- **Entry points:** two UI surfaces (Library, Create page), not the spec's three. M2 replaced the Analysis edit panel with `/create?route_id=<id>`, which is the edit surface for saved routes. New-route mode therefore lands on `/create?route_id=<id>` instead of the spec's `/route/<id>?edit=1`.
- **Not building:** `GET /api/geocode/search` (autocomplete; not in the M5 ships list), job cancel, jobs that survive a restart.

---

### Task 1: Geocode cache and Nominatim client

**Files:**
- Modify: `server/models/schema.sql` (add `geocode_cache`)
- Modify: `server/config.py` (add `NOMINATIM_RATE_LIMIT_MS`, `CSV_MAX_BYTES`, `CSV_MAX_ROWS`)
- Create: `server/models/geocode_cache.py`
- Create: `server/geocode_client.py`
- Test: `tests/test_geocode.py` (new)

**Interfaces:**
- Produces in `server/models/geocode_cache.py`: `normalise_query(q: str) -> str` (strip, collapse internal whitespace, casefold); `get_cached(query: str) -> dict | None` returning `{"lat", "lon", "display_name"}`; `put_cached(query: str, lat: float, lon: float, display_name: str | None) -> None` (insert or replace, `created_at=int(time.time())`). Both normalise the query themselves.
- Produces in `server/geocode_client.py`: `class GeocodeError(Exception)`; `geocode_address(address: str) -> dict | None` returning `{"lat": float, "lon": float, "display_name": str}` or `None` when Nominatim finds nothing. Must run inside an app context. Order: cache hit returns immediately with no network and no rate-limit wait; otherwise wait so that at least `NOMINATIM_RATE_LIMIT_MS` have passed since the previous network call (module-level monotonic timestamp guarded by a lock, shared across threads), then `GET {NOMINATIM_URL}/search` with params `q`, `format=jsonv2`, `limit=1`, header `User-Agent: GPX-Route-Exploration/1.0`, timeout 10 s. An empty list returns `None` (not cached). A network error, timeout, non-200, or non-JSON body raises `GeocodeError`. A hit is cached before returning.

- [ ] **Step 1: Write failing tests** in `tests/test_geocode.py`, using the `app` fixture (set `app.config["NOMINATIM_RATE_LIMIT_MS"] = 0`) and `unittest.mock.patch("server.geocode_client.requests.get")`:
  - `test_normalise_query_collapses_whitespace_and_case`: `"  1  Main   St "` and `"1 main st"` normalise equal.
  - `test_cache_roundtrip_and_replace`: `put_cached` then `get_cached` with a differently-spaced, differently-cased query returns the stored values; a second `put_cached` replaces them.
  - `test_geocode_hit_returns_result_and_caches`: mock returns `[{"lat": "-27.47", "lon": "153.02", "display_name": "X"}]`; result lat/lon are floats; `requests.get` called once with `params["q"]`, `format=jsonv2`, `limit=1` and the User-Agent header.
  - `test_geocode_same_address_twice_calls_network_once`: two calls with differently-cased spellings of the same address; mock call count is 1.
  - `test_geocode_no_results_returns_none_and_is_not_cached`: mock returns `[]`; result `None`; a second call hits the network again (count 2).
  - `test_geocode_http_error_and_timeout_raise_geocode_error`: status 500; then `requests.get` raising `requests.Timeout`; then a response whose `.json()` raises `ValueError`.
  - `test_geocode_rate_limit_waits_between_network_calls`: set `NOMINATIM_RATE_LIMIT_MS=200`, patch `server.geocode_client.time.sleep` and `time.monotonic` so two uncached calls in a row record one sleep of about 0.2 s and a cache hit records none.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_geocode.py -v`. Expected: FAIL (modules not found).
- [ ] **Step 3: Implement** the schema table, the config values (read with `int(os.environ.get(...))` like the existing backup settings), the cache module, and the client module as specified above.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_geocode.py tests/test_models.py -v`. Expected: all PASS (the schema change must not disturb existing tables).
- [ ] **Step 5: Commit** `git add server/models/schema.sql server/config.py server/models/geocode_cache.py server/geocode_client.py tests/test_geocode.py && git commit -m "feat(geocode): persistent geocode cache and rate-limited Nominatim client (M5)"`

---

### Task 2: CSV parsing and column mapping

**Files:**
- Create: `server/csv_import.py`
- Test: `tests/test_csv_import.py` (new)

**Interfaces:**
- Produces: `class CsvImportError(ValueError)`; `parse_csv(data: bytes, mapping: dict[str, str], *, max_rows: int) -> list[dict]`. `mapping` keys are a subset of `name`, `address`, `lat`, `lon`, `description`; values are header names. Returns one dict per data row, in order: `{"index": int (0-based), "name": str, "address": str | None, "lat": float | None, "lon": float | None, "description": str | None, "error": str | None}`.
- Rules: decode as UTF-8 with BOM tolerated (`utf-8-sig`), falling back to `latin-1` if UTF-8 fails; detect the delimiter among `,` `;` tab with `csv.Sniffer` on the header line, defaulting to `,`; the first row is the header; blank lines are skipped and do not consume an index. `CsvImportError` (message fit for a user) is raised when: the data is empty or has a header but no data rows; a mapped header is not in the file; the mapping has neither `address` nor both `lat` and `lon`; unknown mapping keys are present; the row count exceeds `max_rows`. A row with parseable in-range `lat`/`lon` (±90/±180, finite) is direct: `error=None`, coordinates set. Otherwise a non-blank address is kept for geocoding (`lat=lon=None`, `error=None`). Otherwise the row is failed: `error` is `"no address or coordinates"` when both were blank, or `"invalid coordinates"` when coordinates were present but bad. `name` is the mapped name value, else the address, else `f"Stop {index + 1}"`. Blank strings become `None` for `address` and `description`. Ragged rows (missing trailing cells) are tolerated and treated as blank.

- [ ] **Step 1: Write failing tests** in `tests/test_csv_import.py`:
  - `test_direct_coordinates_row`, `test_address_row_needs_geocoding`, `test_name_falls_back_to_address_then_stop_number`.
  - `test_failed_rows_have_reason`: blank row cells give `"no address or coordinates"`; `lat="abc"` without address gives `"invalid coordinates"`; `lat="95"` with an address falls back to geocoding (`error=None`, coordinates `None`).
  - `test_bom_semicolon_and_quoted_cells`: a UTF-8-BOM, `;`-delimited file with a quoted cell containing a delimiter and a newline.
  - `test_ragged_row_and_blank_lines`.
  - `test_empty_header_only_and_unknown_header_raise`, `test_mapping_without_address_or_coordinates_raises`, `test_unknown_mapping_key_raises`, `test_over_max_rows_raises`.
  - `test_latin1_fallback`: a `café` name encoded in latin-1 decodes correctly.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_csv_import.py -v`. Expected: FAIL (module not found).
- [ ] **Step 3: Implement** `parse_csv` and `CsvImportError` as specified.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_csv_import.py -v`. Expected: all PASS.
- [ ] **Step 5: Commit** `git add server/csv_import.py tests/test_csv_import.py && git commit -m "feat(csv): CSV parser with column mapping and row classification (M5)"`

---

### Task 3: Import job runner and event stream

**Files:**
- Create: `server/csv_jobs.py`
- Test: `tests/test_csv_jobs.py` (new)

**Interfaces:**
- Consumes: `parse_csv` rows from Task 2; `geocode_address` / `GeocodeError` from Task 1; `server.models.waypoints.append_waypoint(route_id, *, name, lat, lon, kind, address=None, description=None, included=1, ...)`.
- Produces in `server/csv_jobs.py`:
  - `class Job` with fields `id: str`, `user_id: str`, `route_id: int`, `append: bool`, `total: int`, `events: list[tuple[str, dict]]`, `done: bool`, and a `threading.Condition`.
  - `start_job(app, *, user_id: str, route_id: int, rows: list[dict], append: bool) -> Job` — registers the job (uuid4 hex id), starts a daemon thread running `run_job`, and first discards finished jobs older than 10 minutes.
  - `run_job(app, job: Job, rows: list[dict]) -> None` — runs inside `app.app_context()`; processes rows strictly in order and always ends by appending the `done` event and setting `job.done = True` (in a `finally`).
  - `get_job(job_id: str, user_id: str) -> Job | None` — `None` for an unknown id or a different `user_id`.
  - `iter_events(job: Job, heartbeat_s: float = 15.0) -> Iterator[str]` — yields SSE-formatted strings (`event: <name>\ndata: <json>\n\n`) for every event from the start, waits on the condition for new ones, yields `: keep-alive\n\n` after `heartbeat_s` of silence, and returns after yielding the `done` event.
- Row handling in `run_job`: a row with `error` set is failed; a row with coordinates is `"direct"`; otherwise `geocode_address(row["address"])` is called: a result gives `"geocoded"`, `None` fails with `f"no match for '{address}'"`, a `GeocodeError` fails with `"geocoding service unavailable"`, any other exception fails with `"unexpected error"`. A good row is appended as `kind="stop"`, `included=1`, with its address and description. A failed row is appended with `lat=lon=None`, `included=0`, and `description` set to the CSV description (if any) followed by `Import failed: <reason>` (separated by a newline). Every row emits one `row` event (`status`, `lat`, `lon`, `waypoint_id`, `name`, `error`). The `done` event carries the keys fixed in Global Constraints, `created` or `appended` counting successful rows.

- [ ] **Step 1: Write failing tests** in `tests/test_csv_jobs.py` using the `app` fixture, a route created through `client.post("/api/routes", json={"title": "T"})`, and `patch("server.csv_jobs.geocode_address")` (and `time.sleep` where needed); drive `run_job` synchronously with a `Job` built via `start_job`'s helper or a small test constructor, and read results through `wp_model.list_waypoints`:
  - `test_direct_rows_become_included_stops_in_order`: positions 0..n-1, `kind="stop"`, `included=1`, events `row` then `done` with `created == total`.
  - `test_append_mode_continues_after_existing_waypoints`: a route with 2 manual waypoints plus 3 rows gives positions 0..4 and a `done` event keyed `appended`.
  - `test_geocoded_row_uses_result_and_keeps_address`.
  - `test_failed_rows_kept_excluded_with_note`: parse-failed row, `None` geocode result, and `GeocodeError` each produce `included=0`, null coordinates, and `Import failed:` in the description; the job still emits `done` with the right `failed` count (Review Focus 2).
  - `test_unexpected_exception_in_one_row_does_not_stop_the_job`.
  - `test_iter_events_yields_sse_frames_and_stops_after_done`: assert the exact framing of the first `row` and the `done` frame, and that the generator ends.
  - `test_iter_events_heartbeat_when_idle`: with a job that has no events yet and `heartbeat_s=0.05`, the first yield is `": keep-alive\n\n"`.
  - `test_get_job_is_scoped_to_its_user`.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_csv_jobs.py -v`. Expected: FAIL (module not found).
- [ ] **Step 3: Implement** `server/csv_jobs.py` as specified. Use one module-level dict plus lock for the registry; the thread must capture `app` (not `current_app`) because it runs outside a request.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_csv_jobs.py tests/test_geocode.py tests/test_csv_import.py -v`. Expected: all PASS.
- [ ] **Step 5: Commit** `git add server/csv_jobs.py tests/test_csv_jobs.py && git commit -m "feat(csv): background import job runner with SSE event stream (M5)"`

---

### Task 4: HTTP API, route-creation helper, serving config

**Files:**
- Create: `server/blueprints/api_geocode.py`
- Modify: `server/blueprints/__init__.py` (register the blueprint)
- Modify: `server/models/routes.py` and `server/blueprints/api_routes.py` (extract the recipe-route creation)
- Modify: `Dockerfile` (gunicorn worker settings) and `README.md` (one short note)
- Test: `tests/test_api_geocode.py` (new)

**Interfaces:**
- Consumes: `parse_csv`, `CsvImportError`, `start_job`, `get_job`, `iter_events`; `get_route(user_id, route_id)`; `Config.CSV_MAX_BYTES`, `Config.CSV_MAX_ROWS`.
- Produces: `create_recipe_route(user_id: str, category: dict, title: str, profile: str = "bicycle") -> dict` in `server/models/routes.py` — the body of `_create_recipe_only` from the `storage_name` line through `update_options` (the route dict is returned). `_create_recipe_only` keeps its validation and responses and calls it; `tests/test_api_routes.py` must stay green unchanged.
- Endpoints (blueprint prefix `/api/geocode`):
  - `POST /api/geocode/csv`, multipart: `file`, `mapping` (JSON object string), optional `title` and `category_id` (new-route mode only). Optional query `route_id` selects append mode (`append=1` accepted, not required). Validation order, all before any route is created: no file or bad `mapping` JSON → 400; file over `CSV_MAX_BYTES` → 413; `CsvImportError` → 400 with its message; in append mode the route must exist for the user, otherwise 404. New-route mode creates the route (title from the form, else the filename stem, else `"Imported stops"`; category from `category_id` with 404 if unknown, else the default category). Starts the job and returns `202 {"job_id", "route_id", "append"}`.
  - `GET /api/geocode/csv/<job_id>/stream` returns `text/event-stream` built from `iter_events`, with headers `Cache-Control: no-cache` and `X-Accel-Buffering: no`; an unknown or other-user job gives 404.
- `Dockerfile` CMD becomes `gunicorn --worker-class gthread --workers 1 --threads 8 --timeout 120 -b 0.0.0.0:${FLASK_PORT:-5000} "server:create_app()"`; the README note says CSV import needs exactly one worker because job state is in memory.

- [ ] **Step 1: Write failing tests** in `tests/test_api_geocode.py` using the `client` and `app` fixtures (`app.config["NOMINATIM_RATE_LIMIT_MS"] = 0`; `patch("server.geocode_client.requests.get")` for address rows). Helper: post a CSV, then `client.get(stream_url)` and parse the SSE text into `(event, data)` pairs (the stream is finite, so `get_data(as_text=True)` returns once the job is done):
  - `test_new_route_import_returns_202_and_streams_rows_then_done`: a 3-row coordinates CSV with header `Name,Lat,Lon` and mapping; response has `job_id` and `route_id`, `append` false; the stream has 3 `row` events then `done` with `created == 3`; the new route's waypoints are 3 included stops; the route title defaults to the filename stem.
  - `test_mixed_addresses_and_coordinates_with_cache`: two rows with the same address (different case) and one coordinates row; mocked Nominatim called once; all three waypoints included.
  - `test_failed_rows_are_visible_not_dropped`: one blank row; waypoint exists with `included=0`, null coordinates and an `Import failed:` description; `done` has `failed == 1`.
  - `test_append_mode_adds_after_existing_waypoints_without_creating_a_route`: a route with 2 waypoints created via the API, then `POST /api/geocode/csv?route_id=<id>` with 5 rows; `route_id` in the response is unchanged, `append` true, the list shows 7, and `GET /api/routes` shows no extra route.
  - `test_validation_errors_create_no_route`: missing file (400), invalid mapping JSON (400), mapping with neither address nor lat+lon (400), header-only file (400), over `CSV_MAX_ROWS` rows (400), over `CSV_MAX_BYTES` (413; set `app.config["CSV_MAX_BYTES"]` small); after each, `GET /api/routes` is empty.
  - `test_append_to_unknown_or_foreign_route_404_and_stream_404`: unknown `route_id` → 404; a route owned by another user (use the header pattern from `tests/test_api_routes.py::test_cross_user_route_access_denied`) → 404; unknown `job_id` and another user's `job_id` on the stream → 404.
  - `test_nominatim_down_mid_import_job_still_completes`: mocked `requests.get` raises `requests.ConnectionError`; the stream still ends with `done` and `failed` counts every address row.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_api_geocode.py -v`. Expected: FAIL (404 on the endpoint).
- [ ] **Step 3: Implement** the helper extraction, the blueprint, its registration, the Dockerfile and README changes.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_api_geocode.py tests/test_api_routes.py tests/test_csv_jobs.py tests/test_geocode.py tests/test_csv_import.py -v`. Expected: all PASS.
- [ ] **Step 5: Commit** `git add server/blueprints/api_geocode.py server/blueprints/__init__.py server/models/routes.py server/blueprints/api_routes.py Dockerfile README.md tests/test_api_geocode.py && git commit -m "feat(api): POST /api/geocode/csv + SSE progress stream (M5)"`

---

### Task 5: Shared import dialog and Library entry point

**Files:**
- Modify: `package.json`, `package-lock.json` (add `papaparse` `^5.4`; run `npm install papaparse`)
- Create: `src/js/shared/csv-import.js`
- Create: `src/css/csv-import.css`; import it from `src/css/library-bundle.css` and `src/css/create-bundle.css`
- Modify: `src/js/library/library-app.js` (add the button beside `+ New Route`)
- Test: `tests/test_ui_csv_upload.py` (new)

**Interfaces:**
- Produces in `src/js/shared/csv-import.js`: `guessMapping(headers: string[]) -> {name?, address?, lat?, lon?, description?}` (case-insensitive header-name matching, e.g. `lat`/`latitude`, `lon`/`lng`/`longitude`, `address`/`addr`/`location`, `name`/`title`, `description`/`notes`) and `openCsvImport({ routeId = null, defaultTitle = '', onStart = () => {}, onDone }) -> void` where `onDone({ route_id, total, failed, created, appended })` runs after the `done` event. Dialog flow: choose file (`#csv-file-input`) → PapaParse header-row parse and a preview of the first 5 rows (`#csv-preview`) → one `<select>` per field (`#csv-map-name`, `#csv-map-address`, `#csv-map-lat`, `#csv-map-lon`, `#csv-map-description`) pre-filled from `guessMapping`, each with a "(none)" choice → in new-route mode a title input (`#csv-title`, default `defaultTitle` or the filename stem) → `#csv-import-start` posts multipart (`file`, `mapping` JSON, `title`) to `/api/geocode/csv` (with `?route_id=` when `routeId` is set), calls `onStart`, then opens an `EventSource` on the stream and updates `#csv-progress` (`<progress>` value/max) and `#csv-progress-text` ("n of total") per `row` event. Server error responses show their `error` text in `#csv-import-error` and leave the dialog open. On `done`, close the EventSource and call `onDone`. The overlay is `#csv-import-overlay`; `#csv-import-close` cancels. The Start button stays disabled until at least `address` or both `lat` and `lon` are mapped.
- Library: a `+ Import CSV` button (`#btn-import-csv`) under `+ New Route` in the sidebar; `onDone` navigates to `/create?route_id=<route_id>`.

- [ ] **Step 1: Write failing tests** in `tests/test_ui_csv_upload.py` (Playwright, `server_url` fixture, style of `tests/test_ui_library.py`); write CSVs to `tmp_path` and use `page.set_input_files("#csv-file-input", path)`. Use coordinates-only rows, because the live test server cannot mock Nominatim:
  - `test_library_csv_import_creates_route_and_lands_on_create_page`: CSV `Name,Lat,Lon` with 4 coordinate rows plus 1 row with blank coordinates; assert the mapping selects are pre-filled (`#csv-map-lat` value is `Lat`), click start, wait for navigation to `/create?route_id=<n>`, then via `GET /api/routes/<n>/waypoints` assert 5 rows, 4 included stops in CSV order and 1 excluded row whose description contains `Import failed:`.
  - `test_import_start_disabled_until_a_usable_mapping`: set every select to "(none)" and assert `#csv-import-start` is disabled; choosing `address` enables it.
  - `test_server_rejection_is_shown_in_the_dialog`: a header-only CSV shows the server's message in `#csv-import-error` and the dialog stays open.
- [ ] **Step 2: Run** `npm run build && .venv/bin/python -m pytest tests/test_ui_csv_upload.py -v`. Expected: FAIL (no `#btn-import-csv`).
- [ ] **Step 3: Implement** the module, CSS, dependency and Library button. `server/static/dist/` is gitignored, so do not commit it; always run `npm run build` before running UI tests.
- [ ] **Step 4: Run** `npm run build && .venv/bin/python -m pytest tests/test_ui_csv_upload.py tests/test_ui_library.py -v`. Expected: the new tests PASS; `test_ui_library.py` shows only its 4 known environmental failures (`test_upload_via_ui`, `test_create_category`, `test_delete_route_inline_confirm`, `test_delete_route_cancel`).
- [ ] **Step 5: Commit** `git add package.json package-lock.json src/js/shared/csv-import.js src/css/csv-import.css src/css/library-bundle.css src/css/create-bundle.css src/js/library/library-app.js tests/test_ui_csv_upload.py && git commit -m "feat(ui): CSV import dialog and Library entry point (M5)"`

---

### Task 6: Create-page append entry point

**Files:**
- Modify: `server/templates/create.html` (add `#btn-import-csv` to the toolbar)
- Modify: `src/js/create/app.js`
- Test: `tests/test_ui_csv_upload.py`

**Interfaces:**
- Consumes: `openCsvImport` from Task 5; `ensureRouteId()` (creates the draft route on demand) and `reloadWaypoints(state, editor)` in `src/js/create/app.js`.
- Produces: an `Import CSV` toolbar button on the Create page. Clicking it calls `ensureRouteId()`, then `openCsvImport({ routeId, onStart, onDone })`. `onStart` sets `state.importing = true` and disables `#btn-gen-primary`; `onDone` clears the flag, re-enables the button as the existing generate-button logic would, calls `reloadWaypoints(state, editor)`, and fits the map to the included waypoints. The editor must show the appended rows without a page reload.

- [ ] **Step 1: Write failing tests** in `tests/test_ui_csv_upload.py`:
  - `test_create_page_append_adds_rows_after_manual_waypoints`: open `/create`, drop 2 waypoints by clicking the map (technique in `tests/test_ui_options.py`), import a 5-row coordinates CSV, wait for the dialog to close; assert 7 `.wpe-item` rows, and that the URL has a `route_id`.
  - `test_append_to_saved_route_via_edit_url`: create a route with 4 waypoints through the API, open `/create?route_id=<id>`, import 3 rows; assert 7 rows in the editor and via the API, with the original 4 first in unchanged order.
  - `test_import_button_works_before_any_waypoint_exists`: open a fresh `/create`, import 3 rows; assert the route was created and 3 rows show.
- [ ] **Step 2: Run** `npm run build && .venv/bin/python -m pytest tests/test_ui_csv_upload.py -k "create_page or saved_route or before_any" -v`. Expected: FAIL (no `#btn-import-csv` on the Create page).
- [ ] **Step 3: Implement** the button and handler.
- [ ] **Step 4: Run** `npm run build && .venv/bin/python -m pytest tests/test_ui_csv_upload.py tests/test_ui_create.py tests/test_ui_options.py -v`. Expected: all PASS, apart from the known flakes under load (`test_ui_create.py` and `test_ui_options.py` drag/menu tests that pass in isolation).
- [ ] **Step 5: Commit** `git add server/templates/create.html src/js/create/app.js tests/test_ui_csv_upload.py && git commit -m "feat(ui): append CSV rows from the Create page (M5)"`

---

### Task 7: Regression, live check, sign-off

**Files:**
- Modify: `docs/superpowers/plans/2026-11-14-route-creation-m5.md` (append the marker)

- [ ] **Step 1: Full regression.** `npm run build && .venv/bin/python -m pytest tests/ -q`. Expected: only the 5 known environmental failures (`test_ui_analysis.py::test_analysis_page_loads_map` and the four in `test_ui_library.py`) plus any UI flake that passes in isolation; re-run each other failure alone before calling it a flake.
- [ ] **Step 2: Live check** against the dev server on `http://localhost:5050` with the live Nominatim configured in `.env.development`: import a 10-row CSV mixing street addresses and coordinates from the Library (progress updates row by row, lands on the Create page with 10 rows); append a 5-row CSV on the Create page to a route with 2 manual waypoints (7 rows, Generate usable afterwards); import a CSV with one unresolvable address (row kept, excluded, with the failure note); confirm a repeat import of the same addresses is much faster (cache). Delete every test route afterwards and leave routes 3 and 7 alone.
- [ ] **Step 3: Sign off.** Append `**M5 verified:** <date> by <name>. ...` stating what was run and the actual test totals, then commit `git add docs/superpowers/plans/2026-11-14-route-creation-m5.md && git commit -m "chore: M5 verification sign-off"`.

---

## Out of scope (noted, not planned)

- `GET /api/geocode/search` autocomplete, a job cancel button, and job state that survives a server restart.
- An import entry point on the Analysis page: the Create page is the edit surface for saved routes since M2.
- The in-memory job registry means more than one gunicorn worker would break progress streaming; Task 4 pins the Dockerfile to one worker and documents it.
