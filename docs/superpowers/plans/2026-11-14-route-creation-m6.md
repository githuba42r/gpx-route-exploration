# M6 — Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Repo convention: checkboxes are never ticked** — progress is tracked by commit messages plus a final `**M6 verified:**` marker at the end of this file.

**Goal:** Add the polish features M6 still lacks: live address search on the Create page ("Add by address…"), "Convert to recipe" for GPX-only routes, and the loading indicators and keyboard shortcuts that go with them.

**Architecture:** A search endpoint (`GET /api/geocode/search`) reuses the Nominatim client and its rate limiter from M5. A small server module extracts evenly spaced points from a stored GPX and a `convert-to-recipe` endpoint turns them into waypoint rows. Two browser modules (`address-search.js` on the Create page, `convert-recipe.js` on the Analysis page) call them.

**Tech Stack:** Flask, SQLite, `lxml`, `requests`, esbuild-bundled ES modules, Playwright.

**Spec:** `docs/superpowers/specs/2026-04-17-route-creation-design.md` §5 "M6 — Polish" (lines ~324-340).

## Global Constraints

- "Add by address" uses `GET /api/geocode/search`, which is a Nominatim passthrough shaped for autocomplete; its results are not written to `geocode_cache`.
- "Convert to recipe" extracts N evenly spaced points (default 6) from the trackpoints as waypoints and is explicitly labelled lossy in the UI.
- Acceptance: typing in "Add by address" shows live suggestions; converting a GPX-only route populates 6 waypoints and enables editing.
- Schema changes are additive only (M6 needs none).
- Server config is read from `current_app.config`; the Nominatim rate limit is `NOMINATIM_RATE_LIMIT_MS` (default 1000) and the limiter in `server/geocode_client.py` is shared.
- `server/static/dist/` is gitignored: never commit it, and run `npm run build` before UI tests.

## Review Focus

Inputs and conditions the spec implies but does not spell out. Each has a test in the task that owns the code.

1. A slow earlier autocomplete response must never overwrite the results of a newer query — Task 3.
2. Nominatim down or erroring: the search endpoint answers 502 with a message, and the input shows an inline "unavailable" note and stays usable — Tasks 1 and 3.
3. Convert with bad or edge input: `count` of 0, 1, 51 or non-integer; a track with fewer trackpoints than `count`; a GPX with a single trackpoint or none — Task 2.
4. Convert never changes the uploaded file by itself; a route that already has a recipe gets 409 and no duplicate rows; a later Generate on a converted route keeps the M4 `.orig` backup of the original track — Task 2.
5. Untrusted text (Nominatim `display_name`, GPX names) is rendered with `textContent`, never `innerHTML` — Task 3.

Decisions recorded here:
- **Already done, no work:** the marker right-click menu (mark as stop / waypoint, pin start / end, include, delete), the `clip-path` waypoint diamond (no `rotate(45deg)` remains), Enter / Esc in the stop-edit modal and Esc on the context menu. "Esc to close the edit panel" is obsolete since M2 replaced that panel with `/create?route_id=<id>`.
- **Out of scope:** polygon-based area avoidance via Overpass (the spec marks it a stretch; it needs an Overpass client, a polygon cache, a per-route option and a Valhalla `exclude_polygons` change, and deserves its own plan).
- **Search behaviour:** at least 3 characters, 5 results (clamped to 1-10), 350 ms debounce in the browser. A query under 3 characters returns `[]` without calling Nominatim.
- **Selecting a suggestion** appends a `stop` named by the first comma-separated segment of its `display_name`, with `address` set to the full `display_name`.
- **Convert:** every extracted point is kind `waypoint`, named `Point 1` to `Point N`, evenly spaced by cumulative distance and always including the first and last trackpoint; `count` is 2-50 and defaults to 6. The GPX file is left untouched; the first Generate afterwards overwrites it and M4's one-time `.orig` backup keeps the original.
- **Loading indicators:** Generate already shows a busy state and snap-to-road has a 1.5 s timeout, so the missing ones are address search (spinner on the input) and Convert (busy button).

---

### Task 1: Address search endpoint

**Files:**
- Modify: `server/geocode_client.py` (add `geocode_search`)
- Modify: `server/blueprints/api_geocode.py` (add the route)
- Test: `tests/test_geocode_search.py` (new)

**Interfaces:**
- Consumes: `_wait_for_rate_limit`, `GeocodeError` and the Nominatim request conventions already in `server/geocode_client.py` (User-Agent header, 10 s timeout, `{NOMINATIM_URL}/search`).
- Produces: `geocode_search(query: str, limit: int = 5) -> list[dict]` returning `[{"display_name": str, "lat": float, "lon": float}]` in Nominatim's order; `[]` for no results; `GeocodeError` for network error, timeout, non-200, non-JSON, a non-list body, or hits missing `lat`/`lon`/`display_name`. It uses `format=jsonv2` and `limit=<limit>`, waits on the shared rate limiter, and does not touch the cache. Must run inside an app context.
- Produces: `GET /api/geocode/search?q=<text>&limit=<n>`: `q` stripped of whitespace and shorter than 3 characters gives `200 []` with no upstream call; `limit` defaults to 5 and is clamped to 1-10 (non-integer falls back to 5); success is `200` with the list; `GeocodeError` is `502 {"error": "Address search is unavailable"}`.

- [ ] **Step 1: Write failing tests** in `tests/test_geocode_search.py` (`app` and `client` fixtures; `app.config["NOMINATIM_RATE_LIMIT_MS"] = 0`; `patch("server.geocode_client.requests.get")`):
  - `test_search_returns_normalised_results_in_order`: two mocked hits become two dicts with float `lat`/`lon`; the call used `format=jsonv2`, `limit=5` and the User-Agent header.
  - `test_search_short_query_returns_empty_without_network`: `q="ab"` and `q="  a "` give `[]`; the mock is never called.
  - `test_search_limit_is_clamped_and_defaulted`: `limit=0` sends 1, `limit=99` sends 10, `limit=abc` sends 5.
  - `test_search_does_not_write_the_cache`: after a successful search `get_cached("<query>")` is `None`.
  - `test_search_upstream_failures_give_502`: status 500, `requests.Timeout`, `requests.ConnectionError`, and a body that is not a list each produce `502` with the error message; a hit missing `lat` also gives `502`.
  - `test_search_empty_results_give_empty_list`: mock returns `[]`; response is `200 []`.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_geocode_search.py -v`. Expected: FAIL (404 on the endpoint).
- [ ] **Step 3: Implement** `geocode_search` and the route, reusing the existing request and error conventions in `server/geocode_client.py`.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_geocode_search.py tests/test_geocode.py tests/test_api_geocode.py -v`. Expected: all PASS.
- [ ] **Step 5: Commit** `git add server/geocode_client.py server/blueprints/api_geocode.py tests/test_geocode_search.py && git commit -m "feat(api): GET /api/geocode/search address autocomplete (M6)"`

---

### Task 2: Convert a GPX-only route to a recipe (backend)

**Files:**
- Create: `server/gpx_recipe.py`
- Modify: `server/blueprints/api_waypoints.py` (add the route)
- Test: `tests/test_convert_recipe.py` (new)

**Interfaces:**
- Consumes: `server.models.waypoints.append_waypoint` and `get_or_create_options`; `get_route(user_id, route_id)`; `_find_gpx_file(data_dir, user_id, storage_name)` from `server/blueprints/api_gpx.py`; the haversine helper in `server/gpx_parser.py`.
- Produces: `extract_waypoints(gpx_bytes: bytes, count: int = 6) -> list[dict]` returning `count` dicts `{"name": "Point <i>", "lat": float, "lon": float}` (1-based names) in track order, evenly spaced by cumulative distance and always including the first and last trackpoint. A track with fewer trackpoints than `count` returns every trackpoint. Raises `ValueError` with a user-readable message when the XML is invalid or the track has fewer than 2 trackpoints; requires `count >= 2`.
- Produces: `POST /api/routes/<int:route_id>/convert-to-recipe` with optional JSON `{"count": <int>}` (default 6; must be an integer 2-50, otherwise 400). Responses: `404 {"error": "Not found"}` for an unknown or other user's route; `409 {"error": "Route already has a recipe"}` when waypoints exist; `404 {"error": "Route has no GPX file"}` when the file is missing; `400 {"error": <message>}` for bad count or an unusable track; `200 {"route_id", "count", "waypoints": [<waypoint rows>]}` on success. It appends each point with `kind="waypoint"`, `included=1` and calls `get_or_create_options`. It does not modify the GPX file.

- [ ] **Step 1: Write failing tests** in `tests/test_convert_recipe.py`:
  - Unit: `test_extract_even_by_distance`: a straight 11-point north-south track with equal spacing and `count=6` returns points at trackpoint indices 0, 2, 4, 6, 8, 10; `test_extract_fewer_points_than_count_returns_all`; `test_extract_two_point_track`; `test_extract_rejects_invalid_xml_and_short_tracks` (invalid XML, no trackpoints, one trackpoint raise `ValueError`); `test_extract_uneven_spacing_uses_distance_not_index` (dense cluster at one end still yields evenly distanced points).
  - API (`client` fixture, upload `tests/fixtures/sample.gpx` via `/api/routes`): `test_convert_default_creates_six_waypoints`: 200, `count == 6`, six waypoint rows in position order, kinds all `waypoint`, first and last equal the first and last trackpoints of the fixture, `GET /api/routes/<id>` has `has_recipe` true; `test_convert_leaves_gpx_file_untouched`: the file bytes on disk equal the uploaded bytes after conversion.
  - `test_convert_custom_count_and_bad_counts`: `count=3` gives 3 rows; `count` of 0, 1, 51, `"abc"` and `2.5` each give 400 and create no rows; an empty body uses 6.
  - `test_convert_twice_is_409_and_creates_no_duplicates`.
  - `test_convert_unknown_foreign_and_fileless_routes`: unknown id 404, another user's route 404 (header pattern from `tests/test_api_routes.py::test_cross_user_route_access_denied`), a recipe-only route created via JSON with no waypoints and no file gives 404 "Route has no GPX file".
  - `test_converted_route_can_generate_and_keeps_original_backup`: convert, add the Valhalla `requests.post` mock from `tests/test_api_routing.py` with the right number of legs (5 for 6 waypoints), `POST /generate` gives 200, and the original track bytes are preserved in `<storage_name>.orig` (M4 behaviour).
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_convert_recipe.py -v`. Expected: FAIL (module not found).
- [ ] **Step 3: Implement** `server/gpx_recipe.py` (lxml; reuse the parser's haversine and namespace) and the endpoint.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_convert_recipe.py tests/test_api_waypoints.py tests/test_api_routing.py tests/test_gpx_parser.py -v`. Expected: all PASS.
- [ ] **Step 5: Commit** `git add server/gpx_recipe.py server/blueprints/api_waypoints.py tests/test_convert_recipe.py && git commit -m "feat(api): POST /api/routes/<id>/convert-to-recipe (M6)"`

---

### Task 3: "Add by address…" on the Create page

**Files:**
- Create: `src/js/create/address-search.js`
- Modify: `src/js/create/app.js` (wire it up), `server/templates/create.html` (markup)
- Modify: `src/css/` (create the styles in the Create bundle; add `.is-busy` spinner styling in a shared partial)
- Test: `tests/test_ui_address_search.py` (new)

**Interfaces:**
- Consumes: `GET /api/geocode/search` from Task 1; `api.appendWaypoint(routeId, body)`, `reloadWaypoints(state, editor)` and `state.routeId` in `src/js/create/app.js`.
- Produces: `initAddressSearch({ input, list, status, onSelect })` in `src/js/create/address-search.js`, where `onSelect({ name, address, lat, lon })` is called when the user picks a suggestion. Markup (a new row under the Create header): `#address-bar` containing `<input id="add-address" placeholder="Add by address…" autocomplete="off">`, `<ul id="address-suggestions" role="listbox">` and `<span id="address-status" aria-live="polite">`. Behaviour: 350 ms debounce; fewer than 3 characters clears the list and sends nothing; each new query aborts the previous request (`AbortController`) and a sequence number drops any response that is not the latest; `#address-bar` gets the class `is-busy` while a request is in flight; suggestions are `<li role="option">` whose text is set with `textContent`; ArrowUp/ArrowDown move the active option, Enter or click selects, Escape clears and closes the list; no results shows "No matches" in `#address-status`; a 502 or network error shows "Address search unavailable" there and the input stays usable. Selecting a suggestion calls `onSelect`; the Create page's handler appends a `stop` named by the first comma-separated segment of `display_name` with `address` set to the full `display_name`, reloads the waypoint list, pans the map to it, and clears the input.

- [ ] **Step 1: Write failing tests** in `tests/test_ui_address_search.py` (Playwright, `server_url` fixture; mock the search API in the browser with `page.route("**/api/geocode/search*", handler)` because the live test server cannot mock Nominatim):
  - `test_typing_shows_live_suggestions`: typing `Queen Street` shows the mocked suggestions as `#address-suggestions li` with the mocked text; fewer than 3 characters sends no request (count requests).
  - `test_selecting_a_suggestion_appends_a_stop`: pick a suggestion; the editor gains one row, the API returns a waypoint with `kind="stop"`, the first-segment name, the full `address`, and the mocked `lat`/`lon`; the input is cleared.
  - `test_keyboard_navigation`: ArrowDown twice then Enter selects the second option; Escape closes the list.
  - `test_stale_response_does_not_overwrite_newer_results` (Review Focus 1): hold the first request's `route` object without fulfilling it, type a second query that fulfils immediately, then fulfil the first; the list still shows the second query's results.
  - `test_search_failure_shows_inline_message_and_stays_usable` (Review Focus 2): fulfil with status 502; `#address-status` shows "Address search unavailable"; a later successful query still works.
  - `test_suggestion_text_is_not_interpreted_as_html` (Review Focus 5): a suggestion `display_name` of `<img src=x onerror="window.__xss=1">` renders as literal text and `window.__xss` stays undefined.
  - `test_busy_class_while_request_in_flight`: `#address-bar` has `is-busy` while a held request is pending and loses it once fulfilled.
- [ ] **Step 2: Run** `npm run build && .venv/bin/python -m pytest tests/test_ui_address_search.py -v`. Expected: FAIL (no `#add-address`).
- [ ] **Step 3: Implement** the module, markup, styles and wiring. Reuse the existing modal and input styling conventions in `src/css/`.
- [ ] **Step 4: Run** `npm run build && .venv/bin/python -m pytest tests/test_ui_address_search.py tests/test_ui_create.py tests/test_ui_options.py tests/test_ui_csv_upload.py -q`. Expected: the new tests PASS. Known intermittent flakes (not regressions): `test_ui_options.py::test_optimise_button_reorders_waypoints` and `test_ui_create.py::test_line_drag_inserts_waypoint_between_neighbours`; re-run any other failure alone before calling it a flake.
- [ ] **Step 5: Commit** `git add src/js/create/address-search.js src/js/create/app.js server/templates/create.html src/css tests/test_ui_address_search.py && git commit -m "feat(ui): Add by address with live suggestions (M6)"`

---

### Task 4: "Convert to recipe" on the Analysis page

**Files:**
- Create: `src/js/analysis/convert-recipe.js`
- Modify: `src/js/analysis/app.js` (wire it up), `server/templates/analysis.html`
- Modify: `src/css/` (analysis bundle styles for the dialog; reuse the shared `.is-busy` partial from Task 3)
- Modify: any existing test that asserts the old disabled-button tooltip (search `tests/` for `ships in M6` and `btn-open-edit`)
- Test: `tests/test_ui_convert_recipe.py` (new)

**Interfaces:**
- Consumes: `POST /api/routes/<id>/convert-to-recipe` from Task 2; `data-route-id` and `data-has-recipe` on `<body>` (already in `analysis.html`).
- Produces: on a GPX-only route the nav keeps the disabled `#btn-open-edit` (tooltip changed to "Convert to a recipe first to edit this route") and adds `#btn-convert-recipe` ("Convert to recipe…"). Clicking it opens `#convert-overlay` with an explanation that the conversion is lossy and what it does ("Creates N editable waypoints from this track. The track itself is not changed until you regenerate it; the original file is kept as a backup."), a number input `#convert-count` (default 6, min 2, max 50), `#convert-confirm`, `#convert-cancel` and an error area `#convert-error`. Confirm POSTs `{count}`; while the request runs the button is disabled and has the class `is-busy`; success navigates to `/create?route_id=<id>`; an error response shows its `error` text in `#convert-error` and keeps the dialog open; Escape and Cancel close the dialog. Routes with a recipe render exactly as before and have no convert button.

- [ ] **Step 1: Write failing tests** in `tests/test_ui_convert_recipe.py` (Playwright; upload `tests/fixtures/sample.gpx` through `POST /api/routes` to create a GPX-only route):
  - `test_gpx_only_route_offers_convert_and_disabled_edit`: `#btn-convert-recipe` is visible, `#btn-open-edit` is disabled.
  - `test_convert_default_lands_on_create_with_six_rows`: open the dialog, `#convert-count` has value 6, the dialog text mentions "lossy", confirm; the URL becomes `/create?route_id=<id>` and the editor shows 6 `.wpe-item` rows; reopening `/route/<id>` shows `#btn-open-edit` as an enabled link and no `#btn-convert-recipe`.
  - `test_convert_custom_count`: set 4, confirm; 4 rows.
  - `test_convert_error_is_shown_and_dialog_stays_open`: `page.route("**/api/routes/*/convert-to-recipe", ...)` fulfils with status 400 and `{"error": "bad"}`; `#convert-error` shows "bad"; the dialog is still open.
  - `test_escape_and_cancel_close_the_dialog`.
  - `test_recipe_route_has_no_convert_button`: a route created with waypoints shows `#btn-open-edit` as a link and no convert button.
- [ ] **Step 2: Run** `npm run build && .venv/bin/python -m pytest tests/test_ui_convert_recipe.py -v`. Expected: FAIL (no `#btn-convert-recipe`).
- [ ] **Step 3: Implement** the module, template change and styles; update any existing test that asserted the old tooltip text.
- [ ] **Step 4: Run** `npm run build && .venv/bin/python -m pytest tests/test_ui_convert_recipe.py tests/test_ui_edit_panel.py tests/test_ui_analysis.py -q`. Expected: the new tests PASS; `test_ui_analysis.py::test_analysis_page_loads_map` is the one known environmental failure there.
- [ ] **Step 5: Commit** `git add src/js/analysis/convert-recipe.js src/js/analysis/app.js server/templates/analysis.html src/css tests && git commit -m "feat(ui): Convert to recipe for GPX-only routes (M6)"`

---

### Task 5: Keyboard polish for the CSV dialog

**Files:**
- Modify: `src/js/shared/csv-import.js`
- Test: `tests/test_ui_csv_upload.py`

**Interfaces:**
- Consumes: the existing `close()` in `openCsvImport` (it closes the EventSource and removes the overlay).
- Produces: pressing Escape while `#csv-import-overlay` is open closes it exactly as the Cancel button does; the listener is removed when the dialog closes so repeated open/close cycles do not stack handlers.

- [ ] **Step 1: Write failing tests** in `tests/test_ui_csv_upload.py`: `test_escape_closes_the_import_dialog` (open from the Library, press Escape, overlay gone) and `test_escape_listener_does_not_stack` (open and close the dialog three times, then open once more and press Escape once; the dialog closes and no error is raised on later key presses).
- [ ] **Step 2: Run** `npm run build && .venv/bin/python -m pytest tests/test_ui_csv_upload.py -k escape -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the document-level `keydown` listener inside `openCsvImport`, registered on open and removed in `close()`.
- [ ] **Step 4: Run** `npm run build && .venv/bin/python -m pytest tests/test_ui_csv_upload.py -q`. Expected: all PASS.
- [ ] **Step 5: Commit** `git add src/js/shared/csv-import.js tests/test_ui_csv_upload.py && git commit -m "feat(ui): Escape closes the CSV import dialog (M6)"`

---

### Task 6: Regression, live check, sign-off

**Files:**
- Modify: `docs/superpowers/plans/2026-11-14-route-creation-m6.md` (append the marker)

- [ ] **Step 1: Full regression.** `npm run build && .venv/bin/python -m pytest tests/ -q`. Expected: only the 5 known environmental failures (`test_ui_analysis.py::test_analysis_page_loads_map` and four in `test_ui_library.py`) plus the known intermittent flakes (`test_ui_options.py::test_optimise_button_reorders_waypoints`, `test_ui_create.py::test_line_drag_inserts_waypoint_between_neighbours`); re-run any other failure alone before calling it a flake.
- [ ] **Step 2: Live check** on `http://localhost:5050` with the configured Nominatim: on the Create page type a real Brisbane address in "Add by address" and confirm suggestions appear and picking one adds a stop; upload a real GPX (not the test fixture), convert it with the default 6, confirm the editor shows 6 waypoints, Generate, and confirm the analysis page still works and the original file is kept as `.orig` in the data directory. Delete every test route afterwards and leave routes 3 and 7 alone.
- [ ] **Step 3: Sign off.** Append `**M6 verified:** <date> by <name>. ...` stating what was run, the actual test totals and the out-of-scope polygon-avoidance item, then commit `git add docs/superpowers/plans/2026-11-14-route-creation-m6.md && git commit -m "chore: M6 verification sign-off"`.

---

## Out of scope (noted, not planned)

- **Polygon-based area avoidance** (Overpass fetch, polygon cache, per-route enable, Valhalla `exclude_polygons`): a self-contained stretch feature that needs its own plan.
- Autocomplete results are not cached; a cache for them would need a different table shape than `geocode_cache`.
- Renaming the context-menu entry "Delete" to "Remove from route" (the spec's wording): cosmetic and the existing tests assert the current label.
