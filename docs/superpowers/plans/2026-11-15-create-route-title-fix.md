# Create Page Route Title Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Opening `/create?route_id=N` shows the route's real title (input, nav label, tab title) and can never silently overwrite it with "Untitled Route".

**Architecture:** The Create page never loads the existing route's metadata: `ensureRouteId()` (`src/js/create/app.js:105-114`) only reads `route_id` from the URL, and `server/templates/create.html` hard-codes `value="Untitled Route"` and the nav label "New Route". The blur handler (`app.js:1341-1348`) then PATCHes whatever is in the input if it is non-empty, even when the user never edited it, so focusing and leaving the field persists "Untitled Route" over the real title. Fix on the client: fetch `GET /api/routes/<id>` when arriving with `route_id` (before the first paint of editable state), populate the three title surfaces, remember the saved title, and make the blur handler save only a changed, non-empty title and check the response.

**Tech Stack:** Vanilla JS (esbuild bundle), Flask API (unchanged), Playwright + pytest.

**Spec:** Bug fix, no spec section. Observed in M7 final review (screenshot `create.png`: `/create?route_id=N` showed "Untitled Route" and nav "New Route"; `app.js:102-111` never loads the route).

## Global Constraints

- No server/API changes: `GET /api/routes/<id>` (returns `title`, 404 for unknown/foreign ids) and `PATCH /api/routes/<id>` already exist.
- A brand-new route (`/create` with no `route_id`) behaves exactly as today: input "Untitled Route", nav "New Route", route created with that title.
- Title text is written with `.value` / `textContent` only (route titles are user data).
- Desktop and mobile layout unchanged (M7 visual baselines must still pass without regeneration).
- Never commit to `main`; `server/static/dist/` is gitignored (`npm run build` before UI tests).
- Known baseline failures unrelated to this work: `test_ui_analysis.py::test_analysis_page_loads_map` and four in `test_ui_library.py` (`test_upload_via_ui`, `test_create_category`, `test_delete_route_inline_confirm`, `test_delete_route_cancel`); drag/timing UI tests are intermittently flaky (re-run alone).

## Review Focus

- Focusing and blurring the title field without editing must send no PATCH (Task 1 test counts PATCH requests).
- A title edited to whitespace only or emptied must not be saved and the input must revert to the last saved title (today it silently keeps the blank text in the input while the server keeps the old one).
- `route_id` that does not exist, belongs to another user, or is not a number must show a clear error with a link back to the Library and must not fire any waypoint/route requests against that id (Task 2).
- A failed PATCH (500, network error) must not be reported as saved and must keep the edited text so the user can retry (Task 1).
- A route whose title contains HTML (`<img src=x onerror=window.__pwn=1>`) renders as text everywhere, including `document.title` and the nav label.
- Long titles (M7 uses an 80+60 character one) still don't widen the page at 360 px.

---

### Task 1: Load and persist the real title

**Files:**
- Modify: `src/js/create/app.js` (new `loadRouteTitle(routeId)` helper called after `ensureRouteId()` when `arrivedWithRouteId`; rewrite the title blur handler at ~1341), `server/templates/create.html` (give the nav label an id: `<span id="nav-route-title" class="nav-route-title">New Route</span>`)
- Test: `tests/test_ui_create.py` (add cases)

**Interfaces:**
- Consumes: `getRoute(routeId)` from `src/js/shared/route-api.js` (already imported as `api.getRoute` in this file — confirm the import name), existing `state.routeId`.
- Produces: `state.savedTitle: string` (the last title known to be on the server); `applyTitle(title)` that sets `#route-title.value`, `#nav-route-title.textContent` and `document.title` (`"<title> — GPX Route Exploration"`); behaviour: arriving with `route_id` populates all three from the fetched route before the user can edit; a blur with an unchanged or blank title sends nothing and (if blank) restores `state.savedTitle`; a changed title sends one `PATCH /api/routes/<id>` with `{title}`, and on a non-OK response or network error shows the existing `#generate-error` style inline message ("Could not save title") and keeps the typed text; on success updates `state.savedTitle` and the nav label and `document.title`. A fresh `/create` sets `state.savedTitle` to the title it created the route with.

- [ ] **Step 1: Write failing tests** (Playwright, API-seeded route via `POST /api/routes` with a known title):
  - `test_create_page_shows_existing_route_title`: open `/create?route_id=<id>`; `#route-title` value, `#nav-route-title` text and `document.title` contain the seeded title.
  - `test_title_blur_without_edit_sends_no_patch`: count PATCH requests to `/api/routes/<id>` (via `page.on("request")`); click into `#route-title` and out; assert 0 PATCHes and the server title unchanged (also covers the original bug: re-fetch via API equals the seeded title, not "Untitled Route").
  - `test_title_edit_saves_once_and_updates_nav`: change the title, blur; exactly one PATCH; API title updated; nav label and `document.title` updated.
  - `test_blank_title_reverts_and_does_not_save`: clear the input, blur; zero PATCHes; input shows the saved title again.
  - `test_title_save_failure_keeps_text_and_shows_error`: `page.route` the PATCH to return 500; edit and blur; error message visible, input keeps the typed text, server title unchanged; a second blur with the route un-mocked saves.
  - `test_hostile_title_renders_as_text`: seed title `<img src=x onerror=window.__pwn=1>`; open the page; `window.__pwn` undefined and the input value equals the raw string.
  - `test_new_route_unchanged`: open `/create`; input "Untitled Route", nav "New Route"; blur without edit sends no PATCH.
- [ ] **Step 2: Run** `npm run build && .venv/bin/python -m pytest tests/test_ui_create.py -q -k "title"`; expect the first four and the failure test to FAIL.
- [ ] **Step 3: Implement** `loadRouteTitle`, `applyTitle`, `state.savedTitle` and the new blur handler per Interfaces. Call `loadRouteTitle` immediately after `state.routeId = await ensureRouteId()` and before wiring the blur handler; do not delay map init.
- [ ] **Step 4: Run** the title tests, then `tests/test_ui_create.py tests/test_ui_mobile.py tests/test_ui_edit_panel.py tests/test_ui_mobile_visual.py -q` (baseline failures and known flakes only; re-run any other failure alone). Expected: visual baselines pass unchanged.
- [ ] **Step 5: Commit** `fix(create): load the route's real title and stop blur overwriting it`.

### Task 2: Unknown or invalid `route_id`

**Files:**
- Modify: `src/js/create/app.js` (`ensureRouteId`/bootstrap: validate the id and handle a 404), `server/templates/create.html` (hidden error panel `#route-load-error` with a Library link), `src/css/create.css` (small rule for the panel)
- Test: `tests/test_ui_create.py`

**Interfaces:**
- Consumes: `loadRouteTitle` from Task 1 (it already calls `GET /api/routes/<id>`; extend it to return `null` on 404 and throw on other failures).
- Produces: when `route_id` is not a positive integer, or the route fetch returns 404, the page shows `#route-load-error` ("Route not found" plus a link `← Back to Library` to `/`), hides the editor panel, and issues no waypoint/route-mutating requests; no console errors from NaN ids. Other failures (500/network) show the same panel with "Could not load route" and a Retry button that reloads the page.

- [ ] **Step 1: Write failing tests**: `test_create_unknown_route_shows_not_found` (`/create?route_id=999999`), `test_create_foreign_route_shows_not_found` (route created by another `Remote-User`; follow how `tests/test_api_bookmarks.py` sends a second user header via a Playwright `extra_http_headers` context), `test_create_non_numeric_route_id` (`?route_id=abc`), each asserting the panel is visible, the Library link present, and that the page made no POST/PATCH/PUT/DELETE request (collect via `page.on("request")`); `test_create_route_load_500_shows_retry` (mock the GET to 500; Retry reloads and succeeds when un-mocked).
- [ ] **Step 2: Run** `npm run build && .venv/bin/python -m pytest tests/test_ui_create.py -q -k "route_load or unknown_route or foreign_route or non_numeric"`; expect FAIL.
- [ ] **Step 3: Implement** the validation, panel and 404/500 handling; keep a valid id and a fresh `/create` on the existing path.
- [ ] **Step 4: Run** the new tests plus `tests/test_ui_create.py tests/test_ui_mobile.py tests/test_ui_bookmarks_picker.py tests/test_ui_address_search.py -q`, then the full suite `npm run build && .venv/bin/python -m pytest tests/ -q`; expect only the known baseline failures and flakes.
- [ ] **Step 5: Commit** `fix(create): handle unknown or invalid route_id gracefully`, then append a `**Fix verified:**` marker to this plan (honest about baseline failures) and commit `chore: create-title fix verification sign-off`.
