# GPX Gradient Analysis

A Flask-based web service for uploading, managing, and analysing GPX route files with gradient and elevation visualisation. Designed for evaluating route navigability for cycling, electric unicycle (EUC), and other activities.

## Features

- **Interactive map** with gradient-coloured route segments (green to red by steepness)
- **Elevation profile** with hover sync between map and chart
- **Configurable analysis** — smoothing window, gradient distance, and sampling parameters
- **Terrain gradient sampling** via Valhalla DEM (independent of GPX elevation data)
- **Multiple map layers** — OSM Standard, CyclOSM, OpenTopoMap, Satellite, plus hiking and cycling overlays
- **Route library** — upload, categorise, tag, and annotate routes with title, description, and notes
- **User isolation** via Authelia/Nginx reverse proxy authentication
- **Automated tiered backups** — 7 daily, 6 weekly, 13 monthly, unlimited yearly
- **Service proxy** for Valhalla and Nominatim — no direct client access to upstream services

## Quick Start (Docker)

```bash
git clone <repo-url>
cd gpx-gradient-analysis
docker compose up -d
```

Open [http://localhost:5000](http://localhost:5000).

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `VALHALLA_URL` | `http://10.0.1.25:8002` | Valhalla routing/elevation service URL |
| `NOMINATIM_URL` | `http://10.0.1.25:8001` | Nominatim geocoding service URL |
| `DATA_DIR` | `/app/data` | Persistent data directory (DB + GPX files + backups) |
| `FLASK_PORT` | `5000` | Port the application listens on |
| `FLASK_SECRET_KEY` | `dev-secret-change-me` | Flask session secret — **change in production** |
| `AUTH_USER_HEADER` | `Remote-User` | HTTP header that carries the authenticated username |
| `BACKUP_ENABLED` | `true` | Enable or disable the automated backup scheduler |
| `BACKUP_INTERVAL_HOURS` | `1` | How frequently (in hours) to attempt a backup |
| `BACKUP_DAILY_KEEP` | `7` | Number of daily backups to retain before promoting |
| `BACKUP_WEEKLY_KEEP` | `6` | Number of weekly backups to retain before promoting |
| `BACKUP_MONTHLY_KEEP` | `13` | Number of monthly backups to retain before promoting |

Set these in a `.env` file alongside `docker-compose.yml` — Docker Compose picks them up automatically.

## Prerequisites

The application depends on two external OpenStreetMap-based services:

| Service | Purpose | Required For |
|---------|---------|-------------|
| **Valhalla** | Routing engine + DEM elevation | Terrain gradient feature (`/proxy/valhalla/height`) |
| **Nominatim** | Geocoding (place names) | Location search |

### Local Setup (Recommended)

Run both services locally with Docker for best performance and no rate limits. A regional OSM extract (e.g. SE Queensland) can be set up in minutes with ~700 MB of disk space.

See **[docs/local-osm-services.md](docs/local-osm-services.md)** for the full guide including:
- Docker Compose setup for both services
- Creating smaller regional extracts with `osmium` for faster setup
- Bounding box examples for Australian regions
- DEM/elevation data configuration
- Disk space estimates

### Public Services

You can also point at public instances (with rate limits):

```bash
# Public Nominatim (max 1 req/sec, no bulk queries)
NOMINATIM_URL=https://nominatim.openstreetmap.org

# No public Valhalla with DEM — local instance required for terrain gradient
VALHALLA_URL=http://your-valhalla-host:8002
```

**Note:** The terrain gradient feature requires Valhalla's `/height` endpoint with DEM data, which public/hosted Valhalla services typically don't provide. A local instance with `build_elevation=True` is needed for this feature.

The application proxies all client requests to these services — clients never connect to Valhalla or Nominatim directly.

## Authentication

The application is designed to run behind an authenticating reverse proxy such as [Authelia](https://www.authelia.com/) or Nginx with auth_request. The proxy is expected to inject a header identifying the authenticated user. The `AUTH_USER_HEADER` environment variable configures which header to read (default: `Remote-User`).

Each user's routes, categories, and tags are stored and served in isolation — one user cannot access another's data.

If no authentication proxy is in place, all data is stored under the username `anonymous`.

## Development Setup

```bash
# Python environment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# JavaScript build
npm install
npm run build        # one-shot production build
# npm run watch      # watch mode for development

# Run the dev server
flask --app "server:create_app()" run

# Run tests
pytest tests/
```

For Playwright UI tests, install the browser first:

```bash
playwright install chromium
```

## Project Structure

```
.
├── server/                  # Flask application
│   ├── __init__.py          # App factory (create_app)
│   ├── auth.py              # Reverse-proxy auth header extraction
│   ├── backup.py            # Tiered backup scheduler
│   ├── config.py            # Config class (env var mapping)
│   ├── gpx_parser.py        # GPX parsing and stats extraction
│   ├── blueprints/
│   │   ├── api_routes.py    # Route upload/CRUD API
│   │   ├── api_categories.py# Category management API
│   │   ├── api_tags.py      # Tag management API
│   │   ├── api_gpx.py       # GPX file serving
│   │   ├── pages.py         # HTML page routes
│   │   └── proxy.py         # Valhalla/Nominatim proxy
│   ├── models/
│   │   ├── schema.sql       # SQLite schema
│   │   ├── routes.py        # Route model functions
│   │   ├── categories.py    # Category model functions
│   │   └── tags.py          # Tag model functions
│   ├── static/dist/         # Built JS/CSS bundles (generated)
│   └── templates/           # Jinja2 HTML templates
├── src/
│   ├── js/
│   │   ├── analysis/        # Analysis page ES modules
│   │   └── library/         # Library page ES modules
│   └── css/                 # CSS source files (per-component)
├── tests/                   # Pytest test suite
│   ├── conftest.py
│   ├── fixtures/
│   ├── test_api_routes.py
│   ├── test_api_categories.py
│   ├── test_api_tags.py
│   ├── test_api_proxy.py
│   ├── test_auth.py
│   ├── test_backup.py
│   ├── test_gpx_parser.py
│   └── test_models.py
├── Dockerfile
├── docker-compose.yml
├── build.js                 # esbuild bundler script
├── package.json
├── requirements.txt
└── requirements-dev.txt
```

## API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Route library page |
| `GET` | `/route/<id>` | GPX analysis page for a specific route |
| `GET` | `/api/routes` | List routes (optional `?category_id=`) |
| `POST` | `/api/routes` | Upload a new GPX route |
| `GET` | `/api/routes/<id>` | Get a single route record |
| `PATCH` | `/api/routes/<id>` | Update route metadata (title, description, notes) |
| `DELETE` | `/api/routes/<id>` | Delete a route and its GPX file |
| `PATCH` | `/api/routes/<id>/move` | Move route to a different category |
| `PUT` | `/api/routes/<id>/tags` | Set tags on a route |
| `GET` | `/api/gpx/<id>` | Serve the raw GPX file |
| `GET` | `/api/categories` | List categories |
| `POST` | `/api/categories` | Create a category |
| `PATCH` | `/api/categories/<id>` | Rename/update a category |
| `DELETE` | `/api/categories/<id>` | Delete a category (optional `?move_to_default=true`) |
| `PUT` | `/api/categories/<id>/tags` | Set tags on a category |
| `GET` | `/api/tags` | List all tags with usage counts |
| `DELETE` | `/api/tags/<id>` | Delete a tag |
| `GET/POST/...` | `/proxy/valhalla/<path>` | Proxied Valhalla requests |
| `GET/POST/...` | `/proxy/nominatim/<path>` | Proxied Nominatim requests |

## Running Tests

```bash
# Run all tests
pytest tests/

# Run a specific test file with verbose output
pytest tests/test_api_routes.py -v

# Run only unit tests (exclude Playwright)
pytest tests/ -k "not playwright"
```

For Playwright browser UI tests, install the Chromium browser before running:

```bash
playwright install chromium
pytest tests/
```

## Backup System

The backup scheduler starts automatically with the Flask application. At each interval (default: hourly) it:

1. Creates a consistent snapshot of `routes.db` using the SQLite backup API, along with the entire `gpx/` directory tree, and archives them as a `.tar.gz` in `<DATA_DIR>/backups/daily/`.
2. If today's backup already exists, the run is a no-op.
3. Runs promotion and purge: when a tier exceeds its retention limit, the oldest files are moved to the next tier.

**Retention tiers:**

| Tier | Location | Retention | Overflow goes to |
|---|---|---|---|
| Daily | `backups/daily/` | 7 backups | Weekly |
| Weekly | `backups/weekly/` | 6 backups | Monthly |
| Monthly | `backups/monthly/` | 13 backups | Yearly |
| Yearly | `backups/yearly/` | Unlimited | — |

Backup behaviour is controlled by the `BACKUP_*` environment variables. Set `BACKUP_ENABLED=false` to disable the scheduler entirely.
