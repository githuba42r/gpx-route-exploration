# M7 — Mobile Responsive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Library, Analysis and Create pages usable at phone widths (≥ 360 px) with touch gestures, without a separate mobile app.

**Architecture:** One new `src/css/mobile.css` (all rules inside `@media (max-width: 900px)`) imported last in each of the three bundles, plus small JS modules for the touch behaviours that CSS cannot do (Library filter drawer, Create bottom sheet, long-press, profile tap-pin). Desktop behaviour must not change. Touch Playwright tests use a shared `mobile_page` fixture (iPhone 13 device descriptor: 390×844, `has_touch`, `is_mobile`).

**Tech Stack:** CSS media queries, vanilla JS (esbuild bundles), Leaflet (already handles pinch / two-finger pan / tap), SortableJS (already handles touch), Playwright (pytest).

**Spec:** `docs/superpowers/specs/2026-04-17-route-creation-design.md` (section "M7 — Mobile responsive design").

## Global Constraints

- Breakpoint: `max-width: 900px`; minimum supported width 360 px.
- Viewport meta tag already present in `server/templates/_base.html`; keep it.
- Tap targets at least 44 × 44 px for all interactive elements on mobile (buttons, icons, waypoint markers).
- No horizontal scrolling on any page at 360 px width (`document.documentElement.scrollWidth <= innerWidth`).
- Long-press on a map marker (~500 ms) replaces right-click for the context menu.
- Create page: map takes the top two-thirds of the viewport, editor is a bottom sheet (swipe up expands to full-screen, down collapses); the All/Stops/Waypoints tab row is sticky at the top of the sheet.
- Analysis page: profile stacks below the map at about 160 px height; legend scrolls horizontally with snap points.
- Library page: single-column cards; the sidebar (tag cloud etc.) becomes a drawer opened from a filter button.
- Desktop (> 900 px) layouts and all existing tests must remain unchanged.
- `server/static/dist/` is gitignored: run `npm run build` before UI tests.
- Known baseline failures unrelated to this work: `test_ui_analysis.py::test_analysis_page_loads_map` and four in `test_ui_library.py` (`test_upload_via_ui`, `test_create_category`, `test_delete_route_inline_confirm`, `test_delete_route_cancel`); drag tests in `test_ui_create.py` / `test_ui_options.py` are intermittently flaky.

## Review Focus

- A long route title, long stop names or long addresses at 360 px must wrap or truncate, never widen the page (Task 1 test iterates all three pages at 360 px).
- Opening an overlay or dialog (stop edit, CSV import, Convert, metadata editor) at 390 px must fit the viewport and keep its action buttons reachable (Task 1 test opens the stop-edit and CSV dialogs).
- Mobile browser chrome: `body` is `height: 100vh; overflow: hidden`, which hides content behind the iOS URL bar; use `100dvh` with a `100vh` fallback (Task 1).
- A touch drag on the map must pan it, not trigger the bottom sheet swipe, and a sheet swipe must not pan the map (Task 3 test).
- A long-press must not also fire the tap-to-add-waypoint click that follows the touch end (Task 4 test: waypoint count unchanged after long-press).
- Rotating or resizing across 900 px must not leave the sheet / drawer in a stuck state (Tasks 2 and 3 tests resize the viewport back to 1280 and assert desktop layout).

---

### Task 1: Foundation — `mobile.css`, fixture, overflow guard

**Files:**
- Create: `src/css/mobile.css`, `tests/test_ui_mobile.py`
- Modify: `src/css/create-bundle.css`, `src/css/analysis-bundle.css`, `src/css/library-bundle.css` (add `@import "./mobile.css";` as the LAST line), `src/css/base.css` (`body` height `100vh` → add `height: 100dvh` after it)
- Test: `tests/test_ui_mobile.py` (also holds later tasks' tests)

**Interfaces:**
- Produces: `mobile_page` pytest fixture in `tests/test_ui_mobile.py` (`pytest-playwright` `playwright` + `server_url` fixtures; new context from `playwright.devices["iPhone 13"]`; yields a page; closes the context). Helper `make_route(server_url, n_waypoints=3) -> int` creating a route with GPX + recipe (copy the pattern from `tests/test_ui_edit_panel.py::_create_recipe_route`) and `assert_no_hscroll(page)`.
- Produces: in `mobile.css`, a shared rule giving `button, select, input, .legend-item, .legend-btn, a.nav-brand, #btn-open-edit` a `min-height: 44px` (and `min-width: 44px` for icon-only buttons), a `#main-nav` that wraps, and header bars (`#create-header`, `#settings-bar`, `#header`, `#stats`) that wrap (`flex-wrap: wrap`) with inputs `max-width: 100%`. All inside `@media (max-width: 900px)`.

- [ ] **Step 1: Write failing tests** `test_no_horizontal_scroll_library`, `test_no_horizontal_scroll_analysis`, `test_no_horizontal_scroll_create` (each: `mobile_page` set to 360×740 via `set_viewport_size`, load the page, `assert_no_hscroll`), and `test_tap_targets_min_44` (Create page: every visible `button` and `select` in `#create-header` has bounding box height ≥ 44).
- [ ] **Step 2: Run** `npm run build && .venv/bin/python -m pytest tests/test_ui_mobile.py -q` — expect FAIL on overflow/tap targets.
- [ ] **Step 3: Implement** `mobile.css` per Interfaces; fix any remaining overflow source the tests reveal (long `#route-title` min-width 260 px must become `min-width: 0; width: 100%`).
- [ ] **Step 4: Run** the tests, then the full non-mobile UI suites touching layout (`test_ui_create.py test_ui_edit_panel.py test_ui_options.py -q`) to confirm desktop unchanged. Expected: only known baseline failures/flakes.
- [ ] **Step 5: Commit** `feat(ui): mobile.css foundation, tap targets, no h-scroll (M7)`.

### Task 2: Library — single column and filter drawer

**Files:**
- Create: `src/js/library/filter-drawer.js`
- Modify: `src/js/library/library-app.js` (call `initFilterDrawer()`), `server/templates/library.html` (add `<button id="btn-filters" type="button">Filters</button>` at the top of `#route-list`, hidden on desktop), `src/css/library.css` or `mobile.css`
- Test: `tests/test_ui_mobile.py`

**Interfaces:**
- Produces: `initFilterDrawer()` in `filter-drawer.js`: on ≤ 900 px `#sidebar` is an off-canvas drawer (fixed, full height, translateX(-100%)) toggled by `#btn-filters`, closed by a `#drawer-scrim` click or Escape; adds/removes class `is-open` on `#sidebar`. Above 900 px the button is hidden and the sidebar is the normal column regardless of state (a `matchMedia` change listener clears `is-open`).

- [ ] **Step 1: Failing tests:** `test_library_cards_single_column` (3 routes created via API; at 390 px all `.route-card` share the same left x), `test_library_filter_drawer_opens_and_closes` (sidebar hidden off-screen; tap `#btn-filters` → `#sidebar` inside viewport and tag cloud visible; tap `#drawer-scrim` → off-screen), `test_library_drawer_resets_on_resize` (open drawer, resize to 1280×800 → sidebar in normal flow, `#btn-filters` hidden).
- [ ] **Step 2: Run** them; expect FAIL.
- [ ] **Step 3: Implement** the drawer, CSS (`.route-grid` one column, drawer transition) and button.
- [ ] **Step 4: Run** `tests/test_ui_mobile.py` and `tests/test_ui_library.py` (baseline failures only).
- [ ] **Step 5: Commit** `feat(ui): Library mobile layout with filter drawer (M7)`.

### Task 3: Create page — stacked layout and bottom sheet

**Files:**
- Create: `src/js/create/bottom-sheet.js`
- Modify: `src/js/create/app.js` (call `initBottomSheet({panel: #editor-panel, map})` once; call `map.invalidateSize()` after state changes), `src/css/mobile.css`, `src/css/waypoint-editor.css` only if tab row needs `position: sticky`
- Test: `tests/test_ui_mobile.py`

**Interfaces:**
- Produces: `initBottomSheet({panel, map, handleSelector})` — only active while `matchMedia('(max-width: 900px)')` matches. Sheet states via `data-sheet="peek|half|full"` on `#editor-panel`: default `half` (editor occupies the bottom third, map the top two-thirds), swipe up → `full` (panel covers the map), swipe down → `half`/`peek`. A visible drag handle `.sheet-handle` (≥ 44 px tall hit area) is the only swipe origin, so map panning is unaffected. Uses Pointer Events with `touch-action: none` on the handle. Calls `map.invalidateSize()` on every state change. The All/Stops/Waypoints tab row is `position: sticky; top: 0` inside the sheet. On a media-query change back to desktop the `data-sheet` attribute is removed and desktop styles apply.

- [ ] **Step 1: Failing tests:** `test_create_stacked_layout` (390×844: `#map` height ≥ 0.6 × viewport height, `#editor-panel` top ≥ `#map` bottom − 2, both full width), `test_sheet_swipe_expands_and_collapses` (drag `.sheet-handle` upward via `page.mouse`/`touchscreen` pointer events → `data-sheet="full"` and panel height ≈ viewport; drag down → `half`), `test_map_drag_does_not_move_sheet` (drag on `#map` leaves `data-sheet` unchanged), `test_sheet_resets_on_desktop_resize`.
- [ ] **Step 2: Run** them; expect FAIL.
- [ ] **Step 3: Implement** the sheet and the stacked layout (`#create-main` column; header controls wrap or collapse the secondary options behind the existing ⚙ toggle; `#create-hint` replaced on touch by "Tap = drop waypoint · long-press a pin for more").
- [ ] **Step 4: Run** `tests/test_ui_mobile.py tests/test_ui_create.py tests/test_ui_edit_panel.py -q` (desktop unchanged).
- [ ] **Step 5: Commit** `feat(ui): Create page stacked layout with swipeable editor sheet (M7)`.

### Task 4: Touch interactions — tap-to-add and long-press context menu

**Files:**
- Create: `src/js/shared/long-press.js`
- Modify: `src/js/shared/waypoint-markers.js` (marker `contextmenu` source), `src/js/analysis/context-menu.js` (marker + map long-press), `src/js/create/app.js` as needed
- Test: `tests/test_ui_mobile.py`

**Interfaces:**
- Produces: `onLongPress(leafletLayerOrMap, handler, {ms = 500, moveTolerance = 10})` — registers touchstart/touchmove/touchend (or pointer events with `pointerType === 'touch'`) on the Leaflet object's DOM element, calls `handler({latlng, originalEvent})` after `ms` if the finger has not moved more than `moveTolerance` px, and suppresses the click that follows (sets a short-lived flag the map click handler consults). Returns an unsubscribe function. Existing right-click (`contextmenu`) behaviour is unchanged; the context menu itself is reused.

- [ ] **Step 1: Failing tests:** `test_tap_adds_waypoint` (touch tap on `#map` → one more marker / `/waypoints` POST), `test_long_press_marker_opens_context_menu` (press-and-hold 600 ms on a marker → `#pin-ctx-menu` visible; waypoint count unchanged — i.e. no tap-to-add fired), `test_short_tap_marker_does_not_open_menu`, `test_long_press_cancelled_by_move`. Use CDP `Input.dispatchTouchEvent` or `page.touchscreen` plus `wait_for_timeout` for the hold; menu items must be ≥ 44 px tall.
- [ ] **Step 2: Run** them; expect FAIL on long-press tests (tap-to-add may already pass; keep it as regression).
- [ ] **Step 3: Implement** `long-press.js` and wire Create markers and the Analysis map/markers to it.
- [ ] **Step 4: Run** `tests/test_ui_mobile.py tests/test_ui_create.py tests/test_ui_options.py -q`.
- [ ] **Step 5: Commit** `feat(ui): long-press context menu and tap-to-add on touch (M7)`.

### Task 5: Analysis page — layout, legend, profile touch

**Files:**
- Modify: `src/js/analysis/profile.js` (touch handling), `src/css/mobile.css`
- Test: `tests/test_ui_mobile.py`

**Interfaces:**
- Consumes: `onLongPress` from Task 4 only if Analysis marker menu was not already covered there.
- Produces: in `profile.js`, Pointer-Event (or touch) handlers parallel to the existing mouse handlers: a tap pins the hover info (`#hover-info` shown at that x) and a tap elsewhere dismisses it; a one-finger horizontal drag selects a zoom range exactly as mouse drag-zoom does. `#profile-canvas { touch-action: none; }` on mobile. The mouse path is unchanged.

- [ ] **Step 1: Failing tests:** `test_analysis_mobile_layout` (390 px: `#map` full width, `#profile-container` height between 150 and 170 and below the map), `test_legend_scrolls_horizontally` (`#legend` has `overflow-x: auto`, `scroll-snap-type` set, `scrollWidth > clientWidth` with all items still reachable; page itself has no h-scroll), `test_profile_tap_pins_hover_info` (tap canvas → `#hover-info` visible; tap `#map` → hidden), `test_profile_touch_drag_zoom` (drag across canvas → `.profile-reset-zoom` appears). Fixtures: a GPX with elevation from `make_route` or `tests/fixtures` as other analysis tests do.
- [ ] **Step 2: Run** them; expect FAIL.
- [ ] **Step 3: Implement** the CSS and profile touch handlers.
- [ ] **Step 4: Run** `tests/test_ui_mobile.py tests/test_ui_analysis.py -q` (baseline failure only).
- [ ] **Step 5: Commit** `feat(ui): Analysis page mobile layout and profile touch (M7)`.

### Task 6: Visual regression, mobile suite pass, sign-off

**Files:**
- Create: `tests/test_ui_mobile_visual.py`, `tests/fixtures/mobile-screenshots/` (committed PNGs), `docs/mobile-manual-checklist.md`
- Modify: `.gitignore` only if `tests/fixtures/*.png` is ignored (add a negation for `mobile-screenshots/`); the plan file (append `**M7 verified:** Tasks 1-6 complete on `feature/mobile-responsive`, followed by a final whole-branch review whose findings were fixed in a fix wave: Leaflet controls painting over the full sheet (`#map { isolation: isolate }`); landscape/short viewports (Create map was ~33px at 844x390; now side-by-side layout, and half sheet `max(28dvh, 252px)` so >=1.5 list rows show at 390x664); tapping the map to dismiss the pin context menu also dropped a waypoint (now guarded); broken-looking Library/Analysis header (nav centring, styled Filters button, hidden idle status); sub-44px tap targets (nav links, markers via 44px hit area, tabs, reorder handle, zoom, round-trip label, category headers); Sortable touch reorder now has a test. Visual baselines were tightened (0.2% threshold, fixed locale/timezone, dates masked, tile requests blocked) and regenerated. Full suite (`npm run build` then pytest, scratch probe files excluded): the 5 known pre-existing baseline failures (`test_ui_analysis.py::test_analysis_page_loads_map`; `test_ui_library.py::test_upload_via_ui`, `test_create_category`, `test_delete_route_inline_confirm`, `test_delete_route_cancel`) plus intermittent timing flakes that pass when re-run alone. 3 visual tests / 3 baselines. NOT done: the original spec item "run the existing suites against an iPhone 13 viewport" was DESCOPED. Outstanding: the real-phone pass in `docs/mobile-manual-checklist.md` is unticked and must be done by the user. Ruling noted: Create map is about 0.43 of the viewport height at 390x844 (half sheet), about 0.28 at 390x664. Parked (not in M7): analysis scroll trap, header auto-close, sidebar-row long-press/iOS selection, pre-existing Create title bug, suggestion row 43px.
