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
Browser <-> Authelia/Nginx (auth) <-> Flask (gunicorn) <-> Valhalla (height/trace)
                                                        <-> Nominatim (geocoding)
                                                        <-> SQLite + filesystem (routes)
```

Authentication is handled externally by Authelia or an Nginx reverse proxy in front of Flask. Flask reads the authenticated user identity from a configurable request header (e.g. `Remote-User`, `X-Forwarded-User`). If no header is present, the user defaults to `anonymous`. Each user's routes and categories are isolated — users only see their own data.

Flask is the single network entry point for the application. The browser never contacts Valhalla or Nominatim directly.

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `VALHALLA_URL` | `http://10.0.1.25:8002` | Valhalla service base URL |
| `NOMINATIM_URL` | `http://10.0.1.25:8001` | Nominatim service base URL |
| `DATA_DIR` | `/app/data` | Volume mount for GPX files and SQLite DB |
| `FLASK_PORT` | `5000` | Listen port |
| `FLASK_SECRET_KEY` | `dev-secret-change-me` | Flask session secret |
| `AUTH_USER_HEADER` | `Remote-User` | Request header containing the authenticated username (set by Authelia/Nginx) |

## Data Model

### SQLite Schema

**categories**

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | |
| user_id | TEXT | NOT NULL DEFAULT 'anonymous' | Owner identity from auth header |
| name | TEXT | NOT NULL | Display name |
| slug | TEXT | NOT NULL | Filesystem folder name (auto-generated) |
| description | TEXT | | Optional |
| created_at | DATETIME | NOT NULL DEFAULT CURRENT_TIMESTAMP | |

UNIQUE constraint on `(user_id, name)` and `(user_id, slug)`. A "Default" category is auto-created per user on their first request.

**routes**

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | |
| user_id | TEXT | NOT NULL DEFAULT 'anonymous' | Owner identity from auth header |
| category_id | INTEGER | NOT NULL REFERENCES categories(id) | Defaults to user's Default category |
| filename | TEXT | NOT NULL | Original upload filename |
| storage_name | TEXT | NOT NULL UNIQUE | UUID-based filename on disk |
| title | TEXT | NOT NULL | Mandatory. Defaults to GPX metadata `<name>` on upload, operator must provide if GPX has none |
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

**tags**

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | |
| user_id | TEXT | NOT NULL DEFAULT 'anonymous' | Tags are per-user |
| name | TEXT | NOT NULL | Tag display name (case-preserved) |
| name_lower | TEXT | NOT NULL | Lowercase for dedup/matching |

UNIQUE constraint on `(user_id, name_lower)`. Tags are created on first use and shared across routes and categories for the same user.

**route_tags** (junction table)

| Column | Type | Constraints |
|--------|------|-------------|
| route_id | INTEGER | NOT NULL REFERENCES routes(id) ON DELETE CASCADE |
| tag_id | INTEGER | NOT NULL REFERENCES tags(id) ON DELETE CASCADE |

PRIMARY KEY on `(route_id, tag_id)`.

**category_tags** (junction table)

| Column | Type | Constraints |
|--------|------|-------------|
| category_id | INTEGER | NOT NULL REFERENCES categories(id) ON DELETE CASCADE |
| tag_id | INTEGER | NOT NULL REFERENCES tags(id) ON DELETE CASCADE |

PRIMARY KEY on `(category_id, tag_id)`.

Tags appear as a tag cloud on the library page, filterable. Routes and categories can each have multiple tags. The tag input field auto-completes from existing user tags.

### Filesystem Layout

```
$DATA_DIR/
  routes.db
  gpx/
    anonymous/
      default/
        <uuid>.gpx
      touring/
        <uuid>.gpx
    philg/
      default/
        <uuid>.gpx
      commute/
        <uuid>.gpx
```

- Top-level folders are user identities (from auth header, slugified)
- Within each user folder, category sub-folders hold the GPX files
- Category folder names are slugified from the category name (lowercase, hyphens, no special chars)
- Renaming a category renames the folder
- Moving a route between categories moves the GPX file on disk
- Deleting a category requires it to be empty (or moves routes to Default — operator's choice via API param)
- All API queries are scoped to the current user — users cannot access other users' routes or categories

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

### Tags

| Method | Path | Request | Response | Notes |
|--------|------|---------|----------|-------|
| GET | `/api/tags` | | JSON array of tags with usage counts | All tags for the current user |
| PUT | `/api/routes/<id>/tags` | JSON: `tags` (array of tag names) | JSON route object | Set tags on a route (creates new tags as needed) |
| PUT | `/api/categories/<id>/tags` | JSON: `tags` (array of tag names) | JSON category object | Set tags on a category |
| DELETE | `/api/tags/<id>` | | 204 | Remove a tag entirely (unlinks from all routes/categories) |

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
- Per-route card showing: title, distance, elevation range, max gradient, upload date, last accessed, tags
- Click a route card to open its analysis page
- Upload area (drag-and-drop or file picker) with optional category selector; title is mandatory (pre-filled from GPX `<name>` if available, operator must confirm or edit)
- Category management: create, rename, edit description, manage tags
- Route actions: edit metadata (inline or modal), move to category, manage tags, delete
- **Tag cloud** in sidebar/header showing all user tags sized by usage count; clicking a tag filters the route list to routes/categories with that tag
- **Tag input** on routes and categories: text field with auto-complete from existing user tags, add/remove tag chips
- **Delete confirmations** use inline modals (styled to match the dark theme) — not browser `alert()` / `confirm()` dialogs. The modal shows what will be deleted and requires an explicit confirm/cancel action.
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

## Automated Backups

A background thread within the Flask process runs periodic backups of the SQLite database and all GPX files into date-stamped tarballs stored in the data volume.

### Backup Contents

Each backup is a gzipped tarball containing:
- `routes.db` (SQLite database — copied via `sqlite3` `.backup` API for consistency)
- `gpx/` directory tree (all user folders, category folders, and GPX files)

### Storage Location

```
$DATA_DIR/
  backups/
    daily/
      backup-2026-04-16.tar.gz
      backup-2026-04-15.tar.gz
      ...
    weekly/
      backup-2026-04-14.tar.gz
      ...
    monthly/
      backup-2026-04-01.tar.gz
      ...
    yearly/
      backup-2026-01-01.tar.gz
      ...
```

### Schedule and Retention

The backup process runs once per hour. On each run it:

1. Creates a new daily backup (`backup-YYYY-MM-DD.tar.gz`) if one doesn't already exist for today
2. Promotes and purges according to retention tiers:

| Tier | Retention | Promotion Rule |
|------|-----------|---------------|
| Daily | 7 backups | Created every day |
| Weekly | 6 backups | Oldest daily beyond 7 days is promoted (moved) to weekly |
| Monthly | 13 backups | Oldest weekly beyond 6 weeks is promoted to monthly |
| Yearly | Unlimited | Oldest monthly beyond 13 months is promoted to yearly |

Promotion logic: when a backup ages out of its tier, it is moved (renamed) into the next tier's folder rather than deleted. Only backups that are superseded within their tier are removed. This ensures there is always a recovery point at each granularity.

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `BACKUP_ENABLED` | `true` | Set to `false` to disable automatic backups |
| `BACKUP_INTERVAL_HOURS` | `1` | Hours between backup checks |
| `BACKUP_DAILY_KEEP` | `7` | Number of daily backups to retain |
| `BACKUP_WEEKLY_KEEP` | `6` | Number of weekly backups to retain |
| `BACKUP_MONTHLY_KEEP` | `13` | Number of monthly backups to retain |

### Implementation

- Runs as a `threading.Timer` daemon thread started on app init (not a separate process or cron)
- Uses Python `sqlite3` backup API (`connection.backup()`) for a consistent DB snapshot without locking the application
- Tarball creation uses Python `tarfile` module
- Backup and purge logic in a dedicated `backup.py` module with its own unit tests
- Logs backup/promote/purge actions at INFO level

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

User isolation:
- `test_default_user_is_anonymous` — no auth header results in user_id='anonymous'
- `test_user_from_header` — set `Remote-User` header, verify user_id used
- `test_user_routes_isolated` — user A cannot see user B's routes
- `test_user_categories_isolated` — user A cannot see user B's categories
- `test_default_category_auto_created` — first request from a new user creates their Default category
- `test_cross_user_route_access_denied` — GET/PATCH/DELETE on another user's route returns 404

Tags:
- `test_set_route_tags` — PUT tags on a route, verify tags returned in route object
- `test_set_category_tags` — PUT tags on a category
- `test_tags_auto_created` — setting a new tag name creates the tag record
- `test_tags_case_insensitive_dedup` — "Hilly" and "hilly" resolve to the same tag
- `test_list_tags_with_counts` — GET `/api/tags` returns usage counts
- `test_delete_tag` — removes tag and unlinks from all routes/categories
- `test_tags_per_user_isolated` — user A's tags not visible to user B
- `test_upload_requires_title` — upload without title and GPX has no `<name>` returns 400

Backup (`tests/test_backup.py`):
- `test_create_daily_backup` — run backup, verify tarball created in daily/ with correct contents
- `test_backup_contains_db_and_gpx` — extract tarball, verify routes.db and gpx/ tree present
- `test_skip_duplicate_daily` — run twice same day, only one tarball exists
- `test_daily_purge_promotes_to_weekly` — create 8 dailies, run purge, oldest moved to weekly/
- `test_weekly_purge_promotes_to_monthly` — create 7 weeklies, oldest promoted to monthly/
- `test_monthly_purge_promotes_to_yearly` — create 14 monthlies, oldest promoted to yearly/
- `test_yearly_never_purged` — yearly backups accumulate without deletion
- `test_backup_db_consistency` — backup taken while writes are happening still produces valid SQLite
- `test_backup_disabled` — set BACKUP_ENABLED=false, verify no backups created

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
- `test_delete_route_inline_confirm` — delete shows inline modal (not browser alert), confirm removes route
- `test_delete_route_cancel` — cancel in the inline modal leaves route in place
- `test_add_tags_to_route` — add tags via tag input, verify tag chips appear
- `test_tag_cloud_filters` — click a tag in the tag cloud, verify route list filtered
- `test_upload_requires_title` — upload with no title shows validation error

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
  backup.py               # Automated backup, promotion, and purge logic
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
    test_backup.py        # Backup, promotion, and purge tests
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

## User Identity

Flask reads the user identity from the request header specified by `AUTH_USER_HEADER` (default: `Remote-User`). This header is set by the upstream Authelia/Nginx reverse proxy after authentication.

- If the header is present: the value is used as the `user_id` (trimmed, lowercased)
- If the header is absent: `user_id` defaults to `anonymous`
- On a user's first request, their "Default" category is auto-created if it doesn't exist
- All data operations (routes, categories) are scoped to the current `user_id`
- No user management within the app — user accounts are managed externally by Authelia/Nginx

There is no same-file multi-user editing. Each user sees and manages only their own routes and categories.

## Out of Scope (Current Version)

- Authentication logic (delegated to Authelia/Nginx)
- Same-file concurrent editing across users
- Caching of proxy responses

## Planned for Future Versions

- Route comparison (side-by-side analysis of two routes)
- GPX editing and route planning
- Route optimisation and auto-generation
