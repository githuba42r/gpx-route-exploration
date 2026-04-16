# GPX Gradient Analysis — Flask Service Design

## Overview

Wrap the existing static GPX gradient analysis tool in a Flask web service that manages GPX route storage, metadata, categories, and proxies Valhalla/Nominatim requests. Deployed as a Docker container with a mounted volume for persistent data.

## Goals

- Upload, store, and browse GPX routes with rich metadata
- Organise routes into user-defined categories (filesystem-backed folders)
- Edit route titles, descriptions, notes; edit category names and descriptions
- Serve the existing analysis frontend per-route at bookmarkable URLs
- Proxy Valhalla and Nominatim to prevent direct network access to those services
- Regression test coverage for both the API and the UI

## Architecture

```
Browser <-> Flask (gunicorn) <-> Valhalla (height/trace)
                              <-> Nominatim (geocoding)
                              <-> SQLite + filesystem (routes)
```

Flask is the single network entry point. The browser never contacts Valhalla or Nominatim directly.

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `VALHALLA_URL` | `http://10.0.1.25:8002` | Valhalla service base URL |
| `NOMINATIM_URL` | `http://10.0.1.25:8001` | Nominatim service base URL |
| `DATA_DIR` | `/app/data` | Volume mount for GPX files and SQLite DB |
| `FLASK_PORT` | `5000` | Listen port |
| `FLASK_SECRET_KEY` | `dev-secret-change-me` | Flask session secret |

## Data Model

### SQLite Schema

**categories**

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | |
| name | TEXT | NOT NULL UNIQUE | Display name |
| slug | TEXT | NOT NULL UNIQUE | Filesystem folder name (auto-generated) |
| description | TEXT | | Optional |
| created_at | DATETIME | NOT NULL DEFAULT CURRENT_TIMESTAMP | |

Row id=1 ("Default", slug="default") is seeded on init and cannot be deleted or renamed.

**routes**

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | |
| category_id | INTEGER | NOT NULL DEFAULT 1 REFERENCES categories(id) | |
| filename | TEXT | NOT NULL | Original upload filename |
| storage_name | TEXT | NOT NULL UNIQUE | UUID-based filename on disk |
| title | TEXT | | Defaults to GPX metadata `<name>` |
| description | TEXT | | User-editable |
| notes | TEXT | | User-editable |
| created_at | DATETIME | NOT NULL DEFAULT CURRENT_TIMESTAMP | Upload time |
| last_accessed | DATETIME | | Updated on each view |
| distance_km | REAL | | Computed on upload |
| min_elevation | REAL | | Computed on upload |
| max_elevation | REAL | | Computed on upload |
| max_gradient_asc | REAL | | Steepest climb % (100m window, 7pt smooth) |
| max_gradient_desc | REAL | | Steepest descent % (100m window, 7pt smooth) |
| point_count | INTEGER | | Number of trackpoints |

### Filesystem Layout

```
$DATA_DIR/
  routes.db
  gpx/
    default/
      <uuid>.gpx
    <category-slug>/
      <uuid>.gpx
```

- Category folder names are slugified from the category name (lowercase, hyphens, no special chars)
- Renaming a category renames the folder
- Moving a route between categories moves the GPX file on disk
- Deleting a category requires it to be empty (or moves routes to Default — operator's choice via API param)

## API Endpoints

### Routes

| Method | Path | Request | Response | Notes |
|--------|------|---------|----------|-------|
| GET | `/api/routes` | `?category_id=N` (optional) | JSON array of route objects | List routes, optionally filtered |
| POST | `/api/routes` | Multipart: `file` (GPX), `category_id` (optional), `title`, `description`, `notes` (all optional) | JSON route object | Upload and parse. Title defaults to GPX `<name>`. |
| GET | `/api/routes/<id>` | | JSON route object | Single route metadata |
| PATCH | `/api/routes/<id>` | JSON: `title`, `description`, `notes` (all optional) | JSON route object | Update metadata |
| DELETE | `/api/routes/<id>` | | 204 | Delete route and GPX file |
| PATCH | `/api/routes/<id>/move` | JSON: `category_id` | JSON route object | Move to different category |

### Categories

| Method | Path | Request | Response | Notes |
|--------|------|---------|----------|-------|
| GET | `/api/categories` | | JSON array with `route_count` per category | |
| POST | `/api/categories` | JSON: `name`, `description` (optional) | JSON category object | Creates folder |
| PATCH | `/api/categories/<id>` | JSON: `name`, `description` (optional) | JSON category object | Rename renames folder. Cannot rename id=1. |
| DELETE | `/api/categories/<id>` | `?move_to_default=true` (optional) | 204 | Cannot delete id=1. Fails if non-empty unless `move_to_default=true`. |

### GPX File Proxy

| Method | Path | Response | Notes |
|--------|------|----------|-------|
| GET | `/api/gpx/<id>` | GPX file content (`application/gpx+xml`) | Updates `last_accessed`. |

### Service Proxies

| Method | Path | Proxied To | Notes |
|--------|------|-----------|-------|
| ANY | `/proxy/valhalla/<path>` | `$VALHALLA_URL/<path>` | Passes body, query params, headers |
| ANY | `/proxy/nominatim/<path>` | `$NOMINATIM_URL/<path>` | Passes body, query params, headers |

### Pages

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Route library page (list, upload, categories, metadata editing) |
| GET | `/route/<id>` | Analysis page for a specific route |

## Frontend Changes

### Analysis Page (`index.html` served at `/route/<id>`)

- Server sets `data-gpx-file` to `/api/gpx/<id>` via template variable
- Valhalla URL in `context-menu.js` changes from hardcoded `http://10.0.1.25:8002/height` to `/proxy/valhalla/height`
- Add a navigation bar at top: link back to library, current route title, edit metadata button
- localStorage keys should be scoped per route (e.g. `gpx-<id>-map-view`) to avoid settings bleeding between routes

### Library Page (`library.html` at `/`)

- Route listing grouped by category, each category collapsible
- Per-route card showing: title, distance, elevation range, max gradient, upload date, last accessed
- Click a route card to open its analysis page
- Upload area (drag-and-drop or file picker) with optional category selector
- Category management: create, rename, edit description
- Route actions: edit metadata (inline or modal), move to category, delete with confirmation
- Responsive layout, same dark theme as the analysis page

## Service Proxy Implementation

The proxy endpoints forward requests to Valhalla/Nominatim transparently:

- Forward the request method, path, query string, and body
- Forward `Content-Type` header from the client
- Return the upstream response status, headers (`Content-Type`), and body
- Timeout: 30 seconds
- On upstream failure: return 502 with JSON error message
- No caching — requests pass through directly

## GPX Processing on Upload

When a GPX file is uploaded, the server parses it to extract metadata:

1. Parse XML, extract trackpoints (`<trkpt>` with `<ele>`)
2. Extract `<name>` from `<metadata>` as default title
3. Compute cumulative distance (haversine)
4. Smooth elevations (7-point moving average)
5. Compute gradient with 100m minimum distance window
6. Store: distance_km, min/max elevation, max gradient ascent/descent, point_count

This reuses the same algorithms as the frontend (ported to Python) for consistency.

## Docker

### Dockerfile

- Base: `python:3.12-slim`
- Install: Flask, gunicorn, requests
- Copy application code and static assets
- Volume: `/app/data`
- Expose: `$FLASK_PORT` (default 5000)
- Entrypoint: `gunicorn -b 0.0.0.0:$FLASK_PORT app:app`

### docker-compose.yml (example)

```yaml
services:
  gpx-analysis:
    build: .
    ports:
      - "5000:5000"
    environment:
      - VALHALLA_URL=http://10.0.1.25:8002
      - NOMINATIM_URL=http://10.0.1.25:8001
    volumes:
      - ./data:/app/data
```

## Testing

### API Tests (pytest)

Test the Flask API using pytest with the Flask test client. No external services required — Valhalla/Nominatim proxies are either mocked or skipped.

**Test structure:** `tests/test_api.py`

**Fixtures:**
- `app` — Flask app configured with a temporary `DATA_DIR` (using `tmp_path`)
- `client` — Flask test client
- `sample_gpx` — minimal valid GPX file bytes for upload tests
- `seeded_db` — database with the Default category and a couple of test routes

**Test cases:**

Routes:
- `test_upload_gpx` — POST a GPX file, verify 201, returned metadata has parsed stats
- `test_upload_gpx_with_metadata` — upload with title, description, notes, category_id
- `test_upload_invalid_file` — non-GPX file returns 400
- `test_upload_empty_gpx` — GPX with no trackpoints returns 400
- `test_list_routes` — GET returns all routes with correct fields
- `test_list_routes_by_category` — filter by category_id
- `test_get_route` — GET single route by id
- `test_get_route_not_found` — 404 for missing id
- `test_update_route_metadata` — PATCH title/description/notes
- `test_delete_route` — DELETE removes DB row and file
- `test_move_route` — PATCH move to different category, file moves on disk
- `test_serve_gpx` — GET `/api/gpx/<id>` returns GPX content and updates last_accessed

Categories:
- `test_default_category_exists` — Default category seeded on init
- `test_create_category` — POST with name, verify folder created
- `test_create_duplicate_category` — 409 conflict
- `test_rename_category` — PATCH name, folder renamed
- `test_rename_default_category_fails` — 400 for id=1
- `test_delete_empty_category` — DELETE succeeds, folder removed
- `test_delete_nonempty_category_fails` — 400 when routes exist
- `test_delete_nonempty_with_move_to_default` — routes moved, category deleted
- `test_delete_default_category_fails` — 400 for id=1
- `test_update_category_description` — PATCH description

Proxy:
- `test_valhalla_proxy` — mock upstream, verify request forwarded and response returned
- `test_nominatim_proxy` — mock upstream, verify request forwarded
- `test_proxy_upstream_failure` — upstream timeout returns 502

### UI Tests (Playwright)

End-to-end browser tests using Playwright (Python). These run against a live Flask instance (started as a fixture) with a temporary data directory.

**Test structure:** `tests/test_ui.py`

**Fixtures:**
- `server` — start Flask in a subprocess on a random port with temp `DATA_DIR`, yield the base URL, kill on teardown
- `page` — Playwright browser page
- `uploaded_route` — upload a sample GPX via the API before the test, return the route id

**Test cases:**

Library page:
- `test_library_loads` — page loads, shows "Default" category, upload area visible
- `test_upload_via_ui` — drag/select a GPX file, verify route appears in list with parsed stats
- `test_route_card_shows_metadata` — verify distance, elevation, gradient displayed
- `test_click_route_opens_analysis` — click a route card, verify navigation to `/route/<id>`
- `test_create_category` — create a new category, verify it appears
- `test_rename_category` — rename a category, verify updated
- `test_move_route_between_categories` — move a route, verify it appears under new category
- `test_edit_route_metadata` — edit title/description/notes, verify saved
- `test_delete_route` — delete with confirmation, verify removed from list

Analysis page:
- `test_analysis_page_loads_map` — map renders with route visible
- `test_analysis_page_shows_stats` — stats bar shows distance, elevation, gradient
- `test_elevation_profile_renders` — profile canvas is present and has content
- `test_gradient_legend_visible` — legend items present with gradient ranges
- `test_layer_switcher_present` — layer control is in the map
- `test_settings_sliders_present` — smoothing and gradient window sliders render
- `test_right_click_context_menu` — right-click on map shows context menu
- `test_navigate_back_to_library` — navigation link returns to library page

## Project Structure

```
/
  app.py                  # Flask application
  gpx_parser.py           # GPX parsing and stats computation (Python port)
  models.py               # SQLite schema init, query helpers
  proxy.py                # Valhalla/Nominatim proxy blueprint
  templates/
    library.html          # Route library page
    analysis.html         # Analysis page (wraps existing index.html)
    _base.html            # Shared layout (nav, dark theme)
  static/
    js/                   # Existing JS files (gradient, gpx, map, profile, context-menu, app)
    css/
      style.css           # Extracted from inline styles in index.html
  tests/
    conftest.py           # Shared fixtures (app, client, sample GPX, server)
    test_api.py           # API tests
    test_ui.py            # Playwright UI tests
    fixtures/
      sample.gpx          # Minimal valid GPX for testing
  Dockerfile
  docker-compose.yml
  requirements.txt        # Flask, gunicorn, requests, lxml
  requirements-dev.txt    # pytest, playwright
  README.md
  docs/
    superpowers/specs/    # This spec
```

## Out of Scope

- Authentication/authorisation (single-operator tool)
- Multi-user concurrent access
- Route comparison (side-by-side analysis of two routes)
- GPX editing or route planning
- Caching of proxy responses
