# M4 — Rich GPX Export / Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Repo convention: checkboxes are never ticked** — progress is tracked by commit messages plus a final `**M4 verified:**` marker at the end of this file.

**Goal:** A route's recipe (stops and waypoints) travels inside the GPX file: generated GPX carries `<wpt>` entries, uploading a GPX with `<wpt>` entries recreates the recipe, and an export endpoint serves the stored file.

**Architecture:** Extend the existing writer (`server/routing/gpx_writer.py`) and parser (`server/gpx_parser.py`) additively, hook recipe creation into the existing multipart upload in `server/blueprints/api_routes.py`, and add one read-only endpoint beside `serve_gpx` in `server/blueprints/api_gpx.py`. No schema change.

**Tech Stack:** Flask, SQLite, `xml.etree.ElementTree` (writer), `lxml` (parser), pytest.

**Spec:** `docs/superpowers/specs/2026-04-17-route-creation-design.md` §5 "M4 — Rich GPX export / import" (lines 291-301).

## Global Constraints

- `<wpt>` child order must follow GPX 1.1: `name`, `desc`, `type`. All `<wpt>` elements come after `<metadata>` and before `<trk>`.
- `<wpt type>` is `"stop"` or `"waypoint"`; on import, an absent or unrecognised `type` defaults to `waypoint`.
- Re-import must reproduce the recipe: waypoints match by lat/lon to 6 decimal places, and kinds match.
- `GET /api/routes/<id>/export.gpx` serves the stored GPX file directly (no regeneration).
- Existing analysis logic reads `<trk>` unchanged; `parse_gpx` keeps all current keys and behaviour.
- Schema changes are additive only; M4 needs none.

## Review Focus

Inputs and conditions the spec implies but does not spell out. Each has a test in the task that owns the code.

1. A `<wpt>` with an unrecognised `type` (e.g. `"Summit"` from another app) imports as `waypoint`, not an error — Task 2.
2. A `<wpt>` with no `<name>` imports with a generated name (`"Waypoint N"`), never a NOT NULL failure — Task 2.
3. A `<wpt>` with missing, non-numeric or out-of-range `lat`/`lon` is skipped; the upload still succeeds — Task 2.
4. Names and descriptions containing `& < > "` and non-ASCII text survive export then import unchanged — Tasks 1 and 4.
5. Exporting a recipe route that has never been generated returns a clear 404, not a 500 — Task 4.

Decision recorded here: the writer emits `<wpt>` only for **included** waypoints, in position order. The spec says "one per recipe row", but writing excluded rows would bring them back as included on re-import and change the route the next time it is generated. `pin_role`, `dwell_minutes`, `linked_to_previous` and `address` are not carried by the file; the spec lists only name, description and type.

---

### Task 1: Writer emits `<wpt>` entries; generate passes them

**Files:**
- Modify: `server/routing/gpx_writer.py` (`write_track_gpx`)
- Modify: `server/blueprints/api_routing.py` (the `write_track_gpx(...)` call in `generate_route`)
- Test: `tests/test_gpx_roundtrip.py` (new)

**Interfaces:**
- Produces: `write_track_gpx(path, *, title, legs, precision=6, waypoints=None)`. `waypoints` is a list of dicts with keys `name: str`, `lat: float`, `lon: float`, `kind: "stop"|"waypoint"`, and optional `description: str|None`. Each becomes `<wpt lat lon><name/><desc/><type/></wpt>`; `<desc>` is omitted when the description is empty or None. `waypoints=None` or `[]` produces exactly today's output.

- [ ] **Step 1: Write failing tests** in `tests/test_gpx_roundtrip.py`:
  - `test_writer_emits_wpt_between_metadata_and_trk`: write with two waypoints (one stop, one waypoint); parse the file with lxml; assert the root's children are `metadata`, `wpt`, `wpt`, `trk` in that order, and that the `type` texts are `["stop", "waypoint"]`.
  - `test_writer_wpt_omits_desc_when_empty`: a waypoint with `description=None` has no `desc` child; one with `"Café & <view>"` has `desc` text equal to it after parsing.
  - `test_writer_without_waypoints_has_no_wpt`: `waypoints=None` gives zero `wpt` elements and the same trkpt count as before.
  - Build legs with `encode_polyline` as in `tests/test_routing_gpx_writer.py`.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_gpx_roundtrip.py -v`. Expected: FAIL (`unexpected keyword argument 'waypoints'`).
- [ ] **Step 3: Implement** the `waypoints` parameter in `write_track_gpx`. Create the `<wpt>` elements right after `<metadata>` using `ET.SubElement`, with `lat`/`lon` formatted `f"{v:.7f}"` like trkpts. Update the module docstring (it still says M4 will extend it).
- [ ] **Step 4: Pass the recipe from `generate_route`.** The existing call becomes `write_track_gpx(gpx_path, title=route["title"], legs=parsed_legs, waypoints=wps)`; `wps` is already the included waypoints in position order. Add `test_generate_writes_wpt_for_included_waypoints_only` to `tests/test_gpx_roundtrip.py`: create a recipe route with 3 stops through the API, set the middle one to `included=0` via PATCH, mock Valhalla with the `requests.post` patch pattern from `tests/test_api_routing.py:11-60` (two legs), generate, read the stored file from disk, and assert exactly 2 `wpt` elements with the expected names.
- [ ] **Step 5: Run** `.venv/bin/python -m pytest tests/test_gpx_roundtrip.py tests/test_routing_gpx_writer.py tests/test_api_routing.py -v`. Expected: all PASS.
- [ ] **Step 6: Commit** `git add server/routing/gpx_writer.py server/blueprints/api_routing.py tests/test_gpx_roundtrip.py && git commit -m "feat(gpx): writer emits <wpt> entries for the recipe (M4)"`

---

### Task 2: Parser reads `<wpt>` entries

**Files:**
- Modify: `server/gpx_parser.py` (`parse_gpx`)
- Test: `tests/test_gpx_roundtrip.py`

**Interfaces:**
- Produces: `parse_gpx(data: bytes) -> dict` gains key `"waypoints"`: `list[{"name": str, "lat": float, "lon": float, "kind": "stop"|"waypoint", "description": str|None}]` in document order; `[]` when there are none. Rules: only direct `<wpt>` children of the root are read; `kind` is `"stop"` only when the `type` text, stripped and lower-cased, equals `"stop"`; a missing or blank `name` becomes `f"Waypoint {n}"` where `n` is the 1-based index among the kept entries; an entry whose `lat`/`lon` is missing, non-numeric, NaN or outside ±90 / ±180 is skipped; blank `desc` becomes `None`. All existing keys and error behaviour are unchanged.

- [ ] **Step 1: Write failing tests** in `tests/test_gpx_roundtrip.py`, each building a small GPX byte string with a valid 3-point `<trk>` (copy the trkpt shape from `tests/fixtures/sample.gpx`):
  - `test_parse_reads_wpt_kind_name_description`: one `type="stop"` and one `type="waypoint"` entry, asserting name, lat, lon, kind, description.
  - `test_parse_wpt_unknown_or_missing_type_is_waypoint`: types `"Summit"`, `"STOP "` (expect stop), and no type element.
  - `test_parse_wpt_missing_name_gets_generated_name`: expects `"Waypoint 1"`.
  - `test_parse_wpt_bad_coordinates_skipped`: entries with no `lat`, `lat="abc"`, `lat="91"`, `lon="181"` plus one valid; only the valid one comes back.
  - `test_parse_without_wpt_returns_empty_list`: use `tests/fixtures/sample.gpx`.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_gpx_roundtrip.py -k parse -v`. Expected: FAIL (`KeyError: 'waypoints'`).
- [ ] **Step 3: Implement** a private helper `_parse_waypoints(root) -> list[dict]` in `server/gpx_parser.py` and add its result to the returned dict. Update the `parse_gpx` docstring's return-keys list.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_gpx_roundtrip.py tests/test_gpx_parser.py -v`. Expected: all PASS.
- [ ] **Step 5: Commit** `git add server/gpx_parser.py tests/test_gpx_roundtrip.py && git commit -m "feat(gpx): parser reads <wpt> entries (M4)"`

---

### Task 3: Upload creates a recipe from `<wpt>` entries

**Files:**
- Modify: `server/blueprints/api_routes.py` (`upload_route`, multipart path)
- Test: `tests/test_gpx_roundtrip.py`

**Interfaces:**
- Consumes: `stats["waypoints"]` from Task 2; `wp_model.append_waypoint(route_id, *, name, lat, lon, kind, description=None, ...)` and `wp_model.get_or_create_options(route_id)` from `server/models/waypoints.py`.
- Produces: after a successful multipart upload whose GPX has at least one `<wpt>`, the new route has one `route_waypoints` row per entry (positions 0..n-1, document order) and a `route_options` row. The response and the stored file are unchanged. A GPX with no `<wpt>` creates no rows, so `has_recipe` stays false.

- [ ] **Step 1: Write failing tests** in `tests/test_gpx_roundtrip.py` using the `client` fixture:
  - `test_upload_with_wpt_creates_recipe`: upload a GPX with 3 `<wpt>` (stop, waypoint, no type) via `client.post("/api/routes", data={"file": (io.BytesIO(...), "r.gpx"), "title": "T"}, content_type="multipart/form-data")`; then `GET /api/routes/<id>/waypoints` returns 3 rows with kinds `["stop", "waypoint", "waypoint"]` and positions `[0, 1, 2]`; `GET /api/routes/<id>` has `has_recipe` true.
  - `test_upload_without_wpt_has_no_recipe`: upload `tests/fixtures/sample.gpx`; waypoints list is empty and `has_recipe` is false.
  - `test_upload_with_only_bad_wpt_still_succeeds`: all `<wpt>` have bad coordinates; response 201, no recipe.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_gpx_roundtrip.py -k upload -v`. Expected: FAIL (first test returns zero waypoints).
- [ ] **Step 3: Implement** in `upload_route`: after `create_route(...)`, loop over `stats["waypoints"]` calling `append_waypoint`, then call `get_or_create_options`. Import `waypoints as wp_model` at module level if the file does not already (the JSON path imports it inline today; follow whichever is cleaner there).
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_gpx_roundtrip.py tests/test_api_routes.py -v`. Expected: all PASS.
- [ ] **Step 5: Commit** `git add server/blueprints/api_routes.py tests/test_gpx_roundtrip.py && git commit -m "feat(api): GPX upload creates a recipe from <wpt> entries (M4)"`

---

### Task 4: Export endpoint and round-trip acceptance

**Files:**
- Modify: `server/blueprints/api_gpx.py`
- Test: `tests/test_gpx_roundtrip.py`

**Interfaces:**
- Consumes: `_find_gpx_file(data_dir, user_id, storage_name)` already in `api_gpx.py`.
- Produces: `GET /api/routes/<int:route_id>/export.gpx` returns the stored file with mimetype `application/gpx+xml` and `Content-Disposition: attachment`, download name taken from `route["filename"]` (append `.gpx` if missing). Unknown route returns 404 `{"error": "Not found"}`. Known route whose file does not exist returns 404 `{"error": "Route has no GPX file yet — generate it first"}`. It does not update `last_accessed`.

- [ ] **Step 1: Write failing tests** in `tests/test_gpx_roundtrip.py`:
  - `test_export_serves_stored_file_as_attachment`: upload `sample.gpx`, request export; status 200, body equals the uploaded bytes, `Content-Disposition` contains `attachment`.
  - `test_export_unknown_route_404`.
  - `test_export_never_generated_recipe_route_404`: create a recipe-only route (JSON POST), request export; 404 with the "generate it first" message.
  - `test_roundtrip_recipe_survives_export_and_reimport` (the spec's acceptance test): create a recipe route, add 5 waypoints (3 stops, 2 waypoints, mixed order) via the waypoints API, including one name `"Café & <Bar>"` and one description with a double quote and an emoji; generate with Valhalla mocked (build the fake response so it has 4 legs, each leg's polyline running between consecutive waypoint coordinates, using the patch pattern from `tests/test_api_routing.py`); export; upload the exported bytes as a new route; assert the new route's waypoints, mapped to `(name, round(lat, 6), round(lon, 6), kind, description)`, equal the original's.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_gpx_roundtrip.py -k "export or roundtrip" -v`. Expected: FAIL (404 on the missing route).
- [ ] **Step 3: Implement** the endpoint in `server/blueprints/api_gpx.py`, mirroring `serve_gpx` with `as_attachment=True`.
- [ ] **Step 4: Run the full suite** `.venv/bin/python -m pytest tests/ -q`. Expected: only the 5 known environmental failures (`test_ui_analysis.py::test_analysis_page_loads_map` and four in `test_ui_library.py`) and possibly the 2 known `test_ui_create.py` flakes; anything else is a regression to fix.
- [ ] **Step 5: Manual check** against the dev server (`http://localhost:5050`): create and generate a route through `/create`, `curl -s -o /tmp/export.gpx -D - http://localhost:5050/api/routes/<id>/export.gpx`, confirm the file has both `<wpt>` and `<trk>`, re-upload it with `curl -F file=@/tmp/export.gpx -F title=reimport http://localhost:5050/api/routes`, and compare the two waypoint lists. Delete both test routes afterwards.
- [ ] **Step 6: Sign off.** Append to the end of this file `**M4 verified:** <date> by <name>. ...` stating what was run and the actual test totals. Commit `git add docs/superpowers/plans/2026-11-14-route-creation-m4.md tests/test_gpx_roundtrip.py server/blueprints/api_gpx.py && git commit -m "feat(api): GET /api/routes/<id>/export.gpx + M4 round-trip test"`.

---

## Out of scope (noted, not planned)

- No UI for export (the spec lists only the endpoint). A link on the Analysis nav is a natural follow-up.
- Exported trackpoints still carry `<ele>0</ele>` because `write_track_gpx` ignores the elevation samples that `parse_legs` now returns. Other apps will see a flat profile. Worth a separate small fix.
- The export serves the file as last generated, so saved-but-not-regenerated edits are not in it. This follows the spec ("serves the stored GPX file directly").

---

**M4 verified:** 2026-11-14 by Claude Code (subagent-driven, each task independently reviewed plus a whole-branch review), for review by Phil Gersekowski. Writer, parser, upload-creates-recipe and `GET /api/routes/<id>/export.gpx` landed (`149c8ca`..`2779bf6`). Manual check on `http://localhost:5050/` against the live Valhalla: a 5-waypoint route exported with 5 `<wpt>` and a full `<trk>`, served as an attachment, re-imported to an identical recipe (name, lat/lon to 6 dp, kind, description, including `&`, quotes and an emoji); export before generate returns a 404 with a clear message. Full `pytest tests/` on the final head: 264 passed, 7 failed. 5 are the known pre-existing environmental failures (`test_ui_analysis.py::test_analysis_page_loads_map` and four in `test_ui_library.py`); 2 are drag-timing flakes under full-suite load (`test_ui_create.py::test_drag_reorder_waypoints`, `::test_line_drag_inserts_waypoint_between_neighbours`) that pass in isolation. Deviations from the spec: only included waypoints are exported, and the first generate on an uploaded GPX keeps a one-time `<storage_name>.orig` backup of the original file, because importing a foreign GPX with `<wpt>` entries creates a recipe whose first generate would otherwise overwrite the original track. Known limitations: no export UI; exported trackpoints carry `<ele>0</ele>`; the export is the file as last generated; `pin_role`, `dwell_minutes`, `linked_to_previous` and `address` are not carried by the file. Merge to `main` is left to the user.
