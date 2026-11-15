# M8 — Bookmarks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A per-user library of reusable locations (bookmarks, with tags and optional photos) that can be created from a route stop, from the Library, or by map click, and dropped into any route from a picker on the Create page.

**Architecture:** New `bookmarks`, `bookmark_tags`, `bookmark_photos` tables (additive, `CREATE TABLE IF NOT EXISTS`), a `server/models/bookmarks.py` model and `server/blueprints/api_bookmarks.py` blueprint mirroring the routes/waypoints patterns (user-scoped on every query), photo files on disk under `{DATA_DIR}/bookmarks/<user_id>/<uuid>/`, Pillow thumbnails. Frontend: a Bookmarks tab on the Library page, a shared `bookmark-picker.js` popover on the Create page, and "Save as bookmark" entries in the marker context menus.

**Tech Stack:** Flask, SQLite, Pillow (already in `requirements.txt` since M7), vanilla JS bundles (esbuild), Leaflet, Playwright/pytest.

**Spec:** `docs/superpowers/specs/2026-04-17-route-creation-design.md` (section "M8 — Bookmarks").

## Global Constraints

- Bookmarks are per-user; every query is scoped by `user_id` from `get_current_user()`; another user's bookmark id returns 404 (never 403, never leaks existence).
- Scope decision (controller ruling): per the spec there are NO shared/system-wide bookmarks; "predefined system bookmarks" is a possible follow-up, not in M8.
- Schema columns exactly as in the spec (`bookmarks`: id, uuid UNIQUE, user_id, name, description, lat, lon, created_at, updated_at; `bookmark_tags`(bookmark_id, tag_id, PK both, ON DELETE CASCADE); `bookmark_photos`: id, bookmark_id, position, storage_name, mime_type, byte_size, caption, created_at, UNIQUE(bookmark_id, position)), plus indexes `idx_bookmarks_user`, `idx_bookmark_photos_bookmark`.
- Photo disk layout: `{DATA_DIR}/bookmarks/<user_id>/<bookmark_uuid>/<storage_name>`; thumbnail `<storage_name>.thumb.jpg`, 320 px longest edge, JPEG q=82.
- Photos: MIME `image/jpeg`, `image/png`, `image/webp` only (else 415); cap 10 MB, configurable via `BOOKMARK_PHOTO_MAX_BYTES` (oversize rejected with 413 before writing to disk); fall back to the full image if Pillow is unavailable (log once).
- Tag cloud: `get_tags_with_counts` gains a third COUNT term for `bookmark_tags`.
- Endpoints exactly as in the spec: `GET/POST /api/bookmarks`, `GET/PATCH/DELETE /api/bookmarks/<id>`, `PUT /api/bookmarks/<id>/tags`, `POST /api/bookmarks/<id>/photos`, `DELETE /api/bookmarks/<id>/photos/<photo_id>`, `PUT /api/bookmarks/<id>/photos/order`, `GET /api/bookmarks/<id>/photos/<photo_id>` (`?thumb=1`), `POST /api/bookmarks/from-waypoint/<wpt_id>`, `POST /api/routes/<id>/waypoints/from-bookmark`.
- `from-bookmark` position semantics match `api_waypoints.py::append_waypoint` (absent → append, integer → `wp_model.insert_waypoint_at`); kind defaults to `stop`; the route is then marked as needing regeneration the same way other recipe edits do.
- Library tab "Routes | Bookmarks"; "+ New bookmark" modal with a Leaflet map; Create toolbar button "Bookmarks"; Analysis and Create marker context menus get "Save as bookmark".
- UI text rendered with `textContent` (no `innerHTML` for user data). Submit buttons need re-entrancy guards. Pickers/dialogs must be usable at 390 px wide (M7 rules: 44 px tap targets, no horizontal scroll) and desktop layout must not change.
- Never commit to main; `server/static/dist/` is gitignored (run `npm run build` before UI tests).
- Known baseline failures unrelated to this work: `test_ui_analysis.py::test_analysis_page_loads_map` and four in `test_ui_library.py` (`test_upload_via_ui`, `test_create_category`, `test_delete_route_inline_confirm`, `test_delete_route_cancel`); drag/timing UI tests are intermittently flaky.

## Review Focus

- Cross-user access: user B must get 404 for user A's bookmark on every endpoint, including photo serving and `from-bookmark` (Tasks 1-3 tests use a second `Remote-User` header).
- Hostile uploads: a non-image file with an image MIME, a zero-byte file, an oversize file, a path-traversal filename — all rejected or neutralised, and storage names are server-generated (Task 2).
- Deleting a bookmark or photo removes files on disk and leaves no orphan rows; deleting a tag/bookmark tag association doesn't break the tag cloud counts (Tasks 1-2).
- `from-bookmark` with an out-of-range or negative `position`, an unknown `kind`, or a bookmark id belonging to another user (Task 3).
- Invalid coordinates (lat outside ±90, lon outside ±180, NaN/strings) and empty/very long names on create and patch (Task 1).
- Double-click on Save / pick in the UI must create one bookmark / one waypoint (Tasks 4-5).

---

### Task 1: Schema, model, bookmark CRUD and tags API

**Files:**
- Modify: `server/models/schema.sql`, `server/models/tags.py` (`get_tags_with_counts`, plus `set_bookmark_tags(user_id, bookmark_id, names)` / `get_bookmark_tags(user_id, bookmark_id)` mirroring the route ones, and cascade in `delete_tag` if it enumerates join tables), `server/__init__.py` (register the blueprint)
- Create: `server/models/bookmarks.py`, `server/blueprints/api_bookmarks.py`
- Test: `tests/test_api_bookmarks.py`, `tests/test_models_bookmarks.py`

**Interfaces:**
- Produces (`server/models/bookmarks.py`): `create_bookmark(user_id, *, name, lat, lon, description="") -> dict` (generates `uuid4().hex`), `get_bookmark(user_id, bookmark_id) -> dict | None`, `list_bookmarks(user_id) -> list[dict]` (each with `tags: list[str]`, `photo_count: int`, `thumb_url: str | None`; ordered `updated_at DESC`), `update_bookmark(user_id, bookmark_id, **fields) -> dict | None` (name/description/lat/lon; bumps `updated_at`), `delete_bookmark(user_id, bookmark_id) -> dict | None` (returns the deleted row so the caller can remove its photo folder), `validate_bookmark_fields(data, *, partial) -> (clean, error)` (name 1-120 chars after strip; lat finite in [-90, 90]; lon finite in [-180, 180]; description ≤ 2000 chars).
- Produces (API): the non-photo endpoints from Global Constraints, `PUT /api/bookmarks/<id>/tags` body `{tags: [str]}` returning the tag list, `POST /api/bookmarks/from-waypoint/<wpt_id>` (the waypoint's parent route must belong to the current user; copies name, lat, lon, description; 404 otherwise). Error shape `{"error": "..."}` with 400 for validation, 404 unknown/foreign.

- [ ] **Step 1: Write failing tests** for create/get/list/patch/delete, ordering by `updated_at`, tag set/replace and the tag-cloud count including bookmark usage, validation cases from Review Focus (lat 91, lon "x", NaN, empty name, 121-char name), cross-user 404 on every endpoint using a second `Remote-User` header, and `from-waypoint` (including foreign route's waypoint → 404).
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_api_bookmarks.py tests/test_models_bookmarks.py -q`; expect FAIL.
- [ ] **Step 3: Implement** the schema (spec SQL, `IF NOT EXISTS`), model and blueprint, extend `get_tags_with_counts`, register the blueprint.
- [ ] **Step 4: Run** the new tests plus `tests/test_api_tags.py tests/test_models.py -q`; expect PASS.
- [ ] **Step 5: Commit** `feat(bookmarks): schema, model and CRUD/tags/from-waypoint API (M8)`.

### Task 2: Photos — upload, thumbnails, serve, delete, reorder

**Files:**
- Modify: `server/models/bookmarks.py` (photo functions), `server/blueprints/api_bookmarks.py`, `server/config.py` (`BOOKMARK_PHOTO_MAX_BYTES`, default 10485760), `requirements.txt` (confirm `Pillow>=10,<14`), `server/models/bookmarks.py::list_bookmarks` `thumb_url`
- Create: `server/bookmark_photos.py` (disk layout, MIME sniffing, thumbnailing)
- Test: `tests/test_api_bookmark_photos.py`

**Interfaces:**
- Produces (`server/bookmark_photos.py`): `photo_dir(data_dir, user_id, bookmark_uuid) -> str`, `save_photo(data_dir, user_id, bookmark_uuid, file_bytes, mime) -> (storage_name, byte_size)` (generates a random `<hex>.<ext>` name; writes the file and the 320 px `.thumb.jpg`; verifies the bytes really decode as an image with Pillow, else raises `ValueError`), `remove_photo_files(...)`, `remove_bookmark_dir(...)`.
- Produces (model): `add_photo(bookmark_id, *, storage_name, mime_type, byte_size) -> dict` (tail position), `list_photos(bookmark_id)`, `get_photo(bookmark_id, photo_id)`, `delete_photo(bookmark_id, photo_id)` (re-compacts positions to 0..n-1), `reorder_photos(bookmark_id, ordered_ids)` (must be exactly the current id set, else 400).
- Produces (API): photo endpoints from Global Constraints; response for upload `{id, position, mime_type, byte_size, url, thumb_url}`; serving sets the right `Content-Type` and `Cache-Control: private, max-age=3600`. `DELETE /api/bookmarks/<id>` removes the bookmark folder on disk (rows cascade).

- [ ] **Step 1: Write failing tests**: upload jpg/png/webp OK (thumbnail ≤ 320 px longest edge, JPEG); text file with `image/jpeg` MIME → 415 or 400 and nothing on disk; unsupported MIME → 415; zero-byte → 400; oversize (set `BOOKMARK_PHOTO_MAX_BYTES` small via `create_app` override) → 413 and nothing on disk; filename `../../evil.jpg` ignored (storage name server-generated, file inside the bookmark folder); upload order preserved, reorder persists, reorder with wrong id set → 400; delete photo removes both files and re-compacts positions; delete bookmark removes the folder; serve returns correct bytes and `Content-Type`, `?thumb=1` returns the thumbnail; cross-user 404 for upload, serve, delete and reorder; no-Pillow fallback (monkeypatch import flag) serves the full image as thumbnail.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_api_bookmark_photos.py -q`; expect FAIL.
- [ ] **Step 3: Implement** per Interfaces; enforce the size cap using `request.content_length` and a bounded read.
- [ ] **Step 4: Run** the photo tests plus Task 1's tests; expect PASS.
- [ ] **Step 5: Commit** `feat(bookmarks): photo upload, thumbnails, serve, reorder, delete (M8)`.

### Task 3: Add a bookmark to a route (`from-bookmark`)

**Files:**
- Modify: `server/blueprints/api_waypoints.py`
- Test: `tests/test_api_waypoints.py` (add cases) or `tests/test_api_bookmarks_route.py`

**Interfaces:**
- Consumes: `bookmarks.get_bookmark(user_id, id)`, `wp_model.append_waypoint` / `wp_model.insert_waypoint_at` (signatures as used in this file's existing `append_waypoint` view — copy its conventions, including how the route is flagged as needing regeneration and the response shape).
- Produces: `POST /api/routes/<id>/waypoints/from-bookmark` body `{bookmark_id: int, position?: int, kind?: "stop"|"waypoint"}` → 201 with the new waypoint JSON (same shape as `POST /api/routes/<id>/waypoints`); the waypoint copies name, lat, lon, description from the bookmark (it does NOT keep a live link); 404 for a foreign/unknown route or bookmark; 400 for non-integer `bookmark_id`, unknown `kind`, or `position` that is negative or greater than the current waypoint count.

- [ ] **Step 1: Write failing tests**: append (default kind `stop`), insert at position 1 shifts downstream positions, `kind: "waypoint"`, copied fields equal the bookmark's, later bookmark edit does not alter the waypoint, position -1 / 99 → 400, bad kind → 400, foreign bookmark → 404, foreign route → 404, and the route is reported as needing regeneration exactly as after a normal waypoint add.
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement** `add_from_bookmark(route_id)` in `api_waypoints.py`.
- [ ] **Step 4: Run** `tests/test_api_waypoints.py tests/test_api_bookmarks.py -q`; expect PASS.
- [ ] **Step 5: Commit** `feat(bookmarks): add a bookmark to a route as a waypoint (M8)`.

### Task 4: Library — Bookmarks tab, cards, editor modal, "+ New bookmark"

**Files:**
- Create: `src/js/library/bookmarks-tab.js`, `src/js/library/bookmark-editor.js`, `src/js/library/bookmark-create-modal.js`, `src/css/bookmarks.css`
- Modify: `server/templates/library.html` (tab bar `Routes | Bookmarks`, `#bookmarks-container`), `src/js/library/library-app.js` (tab switching, shared search/tag-filter reuse), `src/js/library/api-client.js` (bookmark calls), `src/css/library-bundle.css`
- Test: `tests/test_ui_bookmarks_library.py`

**Interfaces:**
- Consumes: Task 1-2 API. `api.listBookmarks()`, `api.createBookmark(data)`, `api.updateBookmark(id, data)`, `api.deleteBookmark(id)`, `api.setBookmarkTags(id, tags)`, `api.uploadBookmarkPhoto(id, file)`, `api.deleteBookmarkPhoto(id, photoId)`, `api.reorderBookmarkPhotos(id, ids)` added to `api-client.js` following its existing conventions.
- Produces: tab buttons `#tab-routes`, `#tab-bookmarks` (`aria-selected`), `#bookmarks-container`, toolbar `#btn-new-bookmark`, search `#bookmark-search`; cards `.bookmark-card` (first-photo thumbnail or placeholder glyph, name, tag chips, `lat, lon` to 5 dp); editor modal `#bookmark-editor` (name, description, tags via the existing tag-input component, photo gallery with SortableJS drag-reorder and per-photo delete, Delete bookmark with the existing confirm modal); create modal `#bookmark-create` with a Leaflet map (click sets the marker and lat/lon fields; fields editable), Save disabled until name + coordinates are valid, re-entrancy guard. Tab choice persisted in `location.hash` (`#bookmarks`) so reload/back keeps it. Sort dropdown: updated (default) / name / created.

- [ ] **Step 1: Write failing tests** (Playwright, API-seeded bookmarks): tab switch shows cards and keeps hash; card shows name, tag chips, coords, placeholder when no photo and a thumbnail when one exists; search filters by name/tag text; clicking a tag in the sidebar cloud filters bookmarks; New bookmark modal — click map, fill name, Save → card appears and exactly one POST (double-click Save); editor modal — edit name/description/tags persist after reload, upload two photos (small PNG fixtures generated in the test) appear in order, drag reorder persists, delete photo, delete bookmark via confirm; user text containing `<img src=x onerror=...>` renders as text; at 390×844 (`mobile_page` style context) cards stack, modals fit, no horizontal scroll.
- [ ] **Step 2: Run** `npm run build && .venv/bin/python -m pytest tests/test_ui_bookmarks_library.py -q`; expect FAIL.
- [ ] **Step 3: Implement** the tab, cards, editor and create modal.
- [ ] **Step 4: Run** the new tests and `tests/test_ui_library.py tests/test_ui_mobile.py -q` (baseline failures only).
- [ ] **Step 5: Commit** `feat(ui): Library Bookmarks tab, editor and new-bookmark modal (M8)`.

### Task 5: Create page — Bookmarks picker

**Files:**
- Create: `src/js/shared/bookmark-picker.js`, `src/css/bookmark-picker.css`
- Modify: `server/templates/create.html` (`#btn-bookmarks` near the Generate control, `#bookmark-picker` popover container), `src/js/create/app.js` (mount the picker, forward the selected leg's insert position), `src/css/create-bundle.css`, `src/css/mobile.css` (picker as a bottom/full-width panel with 44 px rows at ≤ 900 px)
- Test: `tests/test_ui_bookmarks_picker.py`

**Interfaces:**
- Consumes: `GET /api/bookmarks`, `POST /api/routes/<id>/waypoints/from-bookmark` (Task 3); in `create/app.js`, the route id and the existing "selected leg / insert position" state used by line-drag insertion (find it where the M2 Task 6 line-drag computes its position) and the existing way the app refreshes markers/sidebar and flags regeneration after a waypoint add.
- Produces: `mountBookmarkPicker({button, container, getRouteId, getInsertPosition, onAdded})` in `bookmark-picker.js`: popover listing bookmarks (thumbnail via `loading="lazy"`, name, tag chips, distance from the current map centre via a `getMapCenter()` option, nearest first), text search, tag filter, empty state with a link to the Library Bookmarks tab; selecting a bookmark POSTs once (re-entrancy guard; row disabled while pending), calls `onAdded(waypoint)`, closes the popover; closes on Escape and outside click; errors shown inline ("Could not add bookmark"). If the route has not been saved yet (no route id), the picker first uses the same create-route-on-first-edit path the page already uses for adding a waypoint (do not invent a second path).

- [ ] **Step 1: Write failing tests**: button opens popover listing seeded bookmarks nearest-first; search/tag filter; pick → new waypoint at the tail in the sidebar and a marker on the map and the page's "needs regeneration" state; click a leg first then pick → inserted mid-route with downstream positions shifted (assert via API order); double-click a row → exactly one waypoint added; Escape and outside click close it; empty-state link; XSS text rendered as text; at 390×844 the popover fits, rows ≥ 44 px, no horizontal scroll, and it doesn't conflict with the bottom sheet or address autocomplete (both can't be open at once).
- [ ] **Step 2: Run** `npm run build && .venv/bin/python -m pytest tests/test_ui_bookmarks_picker.py -q`; expect FAIL.
- [ ] **Step 3: Implement** the picker and wire it in `create/app.js`.
- [ ] **Step 4: Run** the new tests plus `tests/test_ui_create.py tests/test_ui_mobile.py tests/test_ui_address_search.py -q` (baseline failures and known flakes only; re-run any other failure alone).
- [ ] **Step 5: Commit** `feat(ui): Create page bookmark picker (M8)`.

### Task 6: "Save as bookmark" in marker menus, verification and sign-off

**Files:**
- Modify: `src/js/analysis/context-menu.js` and `server/templates/analysis.html` (menu entry `#ctx-save-bookmark`, visible only on a waypoint marker), `src/js/create/app.js` and the Create pin-menu builder (button `data-act="save-bookmark"` in `#pin-ctx-menu`), a small shared `src/js/shared/toast.js` (`showToast(message, {href, linkText})`, `aria-live="polite"`, auto-dismiss 5 s) with CSS, `README.md` (bookmarks, photo env var, Pillow), the plan file (append `**M8 verified:**`)
- Test: `tests/test_ui_bookmarks_save.py`

**Interfaces:**
- Consumes: `POST /api/bookmarks/from-waypoint/<wpt_id>` (Task 1). Both menus need the marker's waypoint id (`marker._waypointId` exists in `waypoint-markers.js`; on Analysis use the id the existing remove-waypoint entry already uses).
- Produces: `showToast(message, {href?, linkText?})`; "Save as bookmark" entry that POSTs once (re-entrancy guard), shows toast "Saved to bookmarks" with a "View" link to `/#bookmarks`, and surfaces errors in the toast. Works via right-click on desktop and long-press on touch (existing menus), entry height ≥ 44 px at ≤ 900 px.

- [ ] **Step 1: Write failing tests**: right-click a stop in Create → "Save as bookmark" → toast with link; the bookmark exists via API with the stop's name/lat/lon/description; same on Analysis for a recipe route; double-click the entry creates one bookmark; the Library Bookmarks tab shows it (follow the toast link); entry not shown for map right-click without a marker; long-press path on a 390×844 touch context.
- [ ] **Step 2: Run** `npm run build && .venv/bin/python -m pytest tests/test_ui_bookmarks_save.py -q`; expect FAIL.
- [ ] **Step 3: Implement** the entries, toast and README section.
- [ ] **Step 4: Run the full suite** `npm run build && .venv/bin/python -m pytest tests/ -q --ignore=tests/test_probe_tmp.py --ignore=tests/test_dbg_tmp.py`; expect only the known baseline failures and intermittent flakes (re-run any other failure alone). Also do one live check against the dev server's code path with a throwaway user header (do not touch routes 3 and 7 or the existing data): create a bookmark with a PNG photo, add it to a scratch route, delete both.
- [ ] **Step 5: Append** `**M8 verified:**` to this plan (honest about baseline failures and anything not done), then commit `chore: M8 verification sign-off`.
