# Flask Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the GPX gradient analysis tool in a Flask service with route management, categories, tags, user isolation, service proxying, automated backups, and Docker deployment.

**Architecture:** Flask app with SQLite + filesystem storage, Jinja2 templates, modular Python backend (blueprints), modular frontend JS (small focused files), esbuild for minification, gunicorn in Docker.

**Tech Stack:** Python 3.12, Flask, SQLite, gunicorn, requests, lxml, esbuild (JS/CSS minification), Playwright (UI tests), pytest (API tests)

---

## File Structure

### Backend (Python — modular with blueprints)

```
server/
  __init__.py             # Flask app factory, config, middleware
  config.py               # Environment-based configuration
  auth.py                 # User identity extraction from headers
  models/
    __init__.py            # DB init, get_db(), close_db()
    schema.sql             # Full DDL (all tables)
    categories.py          # Category CRUD queries
    routes.py              # Route CRUD queries
    tags.py                # Tag CRUD queries
  blueprints/
    __init__.py
    pages.py               # GET / and GET /route/<id>
    api_routes.py           # /api/routes endpoints
    api_categories.py       # /api/categories endpoints
    api_tags.py             # /api/tags endpoints
    api_gpx.py              # /api/gpx/<id> file serving
    proxy.py                # /proxy/valhalla, /proxy/nominatim
  gpx_parser.py            # GPX XML parsing and stats extraction
  backup.py                # Backup, promotion, purge logic + scheduler
```

### Frontend (JS — split by responsibility, <200 lines each)

```
src/
  js/
    analysis/              # Analysis page JS (served at /route/<id>)
      gradient.js           # Gradient ranges, colors, angle helpers (existing)
      gpx-loader.js         # GPX fetch + parse (existing gpx.js, loadGPX only)
      track-processor.js    # Smoothing, distance, gradient calc (existing gpx.js, processTrackData etc)
      map-init.js           # Leaflet map setup, tile layers, layer persistence (existing map.js)
      map-segments.js       # Gradient segments, visibility, recoloring (split from map.js)
      map-markers.js        # Start/end/max/min markers, position marker (split from map.js)
      map-hover.js          # Hover panel init + events (existing initMapHoverPanel from map.js)
      profile.js            # Elevation profile canvas (existing)
      context-menu.js       # Right-click menu, waypoint CRUD (split from context-menu.js)
      terrain-gradient.js   # DEM terrain sampling via proxy (split from context-menu.js)
      gradient-modal.js     # Route gradient info modal (split from context-menu.js)
      settings.js           # Analysis settings sliders + presets (new, extracted from app.js)
      nav.js                # Navigation bar, back-to-library link
      app.js                # Main orchestration (slimmed down)
    library/               # Library page JS
      api-client.js         # Shared fetch wrapper for /api/* endpoints
      library-app.js        # Library page orchestration
      route-cards.js        # Route card rendering and interactions
      category-panel.js     # Category listing, create/rename/delete
      upload.js             # File upload (drag-drop + picker), title validation
      metadata-editor.js    # Inline metadata edit modal
      tag-input.js          # Tag auto-complete chip input widget
      tag-cloud.js          # Tag cloud rendering and filtering
      confirm-modal.js      # Reusable inline confirmation modal
    shared/
      theme.js              # Shared constants (colors, etc)
  css/
    base.css                # Reset, body, dark theme variables
    nav.css                 # Navigation bar
    stats.css               # Stats bar
    legend.css              # Gradient legend
    map.css                 # Map, hover panel, context menu
    profile.css             # Elevation profile
    modals.css              # All modals (gradient, terrain, confirm)
    settings.css            # Settings bar
    library.css             # Library page (cards, upload, categories)
    tags.css                # Tag cloud, tag chips, tag input
```

### Build

```
package.json              # esbuild scripts
build.js                  # esbuild config — bundles + minifies
```

Output goes to `server/static/dist/`:
- `analysis.min.js` — all analysis page JS bundled
- `library.min.js` — all library page JS bundled
- `analysis.min.css` — all analysis page CSS
- `library.min.css` — all library page CSS

Source files remain in `src/` for development; templates reference the minified bundles.

### Templates

```
server/templates/
  _base.html              # Shared: doctype, nav, CSS links, dark theme
  library.html            # Route library page
  analysis.html           # Analysis page (wraps existing frontend)
```

### Tests

```
tests/
  conftest.py             # App fixture, client, sample GPX, server for Playwright
  fixtures/
    sample.gpx            # Minimal valid GPX (10 trackpoints with elevation)
    sample_no_name.gpx    # GPX without <name> metadata
    invalid.txt           # Non-GPX file
  test_gpx_parser.py      # GPX parsing unit tests
  test_models.py          # DB model unit tests
  test_api_routes.py      # Route API endpoint tests
  test_api_categories.py  # Category API endpoint tests
  test_api_tags.py        # Tag API endpoint tests
  test_api_proxy.py       # Proxy endpoint tests
  test_auth.py            # User identity extraction tests
  test_backup.py          # Backup/promote/purge tests
  test_ui_library.py      # Playwright: library page
  test_ui_analysis.py     # Playwright: analysis page
```

### Root

```
Dockerfile
docker-compose.yml
requirements.txt
requirements-dev.txt
README.md
```

---

## Phase 1: Project Scaffolding + Build Pipeline

### Task 1: Initialise project structure and dependencies

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `package.json`
- Create: `build.js`
- Create: `.gitignore` (update existing)

- [ ] **Step 1: Create requirements.txt**

```
flask>=3.1,<4
gunicorn>=23,<24
requests>=2.32,<3
lxml>=5.3,<6
```

- [ ] **Step 2: Create requirements-dev.txt**

```
-r requirements.txt
pytest>=8,<9
playwright>=1.49,<2
pytest-playwright>=0.6,<1
```

- [ ] **Step 3: Create package.json**

```json
{
  "name": "gpx-gradient-analysis",
  "private": true,
  "scripts": {
    "build": "node build.js",
    "watch": "node build.js --watch",
    "dev": "node build.js --watch & python -m server --debug"
  },
  "devDependencies": {
    "esbuild": "^0.25"
  }
}
```

- [ ] **Step 4: Create build.js**

```js
const esbuild = require('esbuild');
const path = require('path');

const isWatch = process.argv.includes('--watch');

const shared = {
  bundle: true,
  minify: !isWatch,
  sourcemap: isWatch,
  target: ['es2020'],
  outdir: path.join(__dirname, 'server', 'static', 'dist'),
};

async function build() {
  const contexts = [
    // Analysis page JS
    await esbuild.context({
      ...shared,
      entryPoints: ['src/js/analysis/app.js'],
      outfile: path.join(shared.outdir, 'analysis.min.js'),
      format: 'iife',
      outdir: undefined,
    }),
    // Library page JS
    await esbuild.context({
      ...shared,
      entryPoints: ['src/js/library/library-app.js'],
      outfile: path.join(shared.outdir, 'library.min.js'),
      format: 'iife',
      outdir: undefined,
    }),
    // Analysis page CSS
    await esbuild.context({
      ...shared,
      entryPoints: ['src/css/analysis-bundle.css'],
      outfile: path.join(shared.outdir, 'analysis.min.css'),
      outdir: undefined,
    }),
    // Library page CSS
    await esbuild.context({
      ...shared,
      entryPoints: ['src/css/library-bundle.css'],
      outfile: path.join(shared.outdir, 'library.min.css'),
      outdir: undefined,
    }),
  ];

  if (isWatch) {
    await Promise.all(contexts.map(ctx => ctx.watch()));
    console.log('Watching for changes...');
  } else {
    await Promise.all(contexts.map(ctx => ctx.rebuild()));
    await Promise.all(contexts.map(ctx => ctx.dispose()));
    console.log('Build complete.');
  }
}

build().catch(() => process.exit(1));
```

- [ ] **Step 5: Create CSS bundle entry points**

Create `src/css/analysis-bundle.css`:
```css
@import "./base.css";
@import "./nav.css";
@import "./stats.css";
@import "./settings.css";
@import "./legend.css";
@import "./map.css";
@import "./profile.css";
@import "./modals.css";
@import "./tags.css";
```

Create `src/css/library-bundle.css`:
```css
@import "./base.css";
@import "./nav.css";
@import "./library.css";
@import "./modals.css";
@import "./tags.css";
```

- [ ] **Step 6: Update .gitignore**

```
*.gpx
node_modules/
server/static/dist/
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
data/
```

- [ ] **Step 7: Install dependencies and verify build**

Run:
```bash
npm install
mkdir -p server/static/dist src/css src/js/analysis src/js/library src/js/shared
touch src/css/base.css src/css/nav.css src/css/stats.css src/css/settings.css src/css/legend.css src/css/map.css src/css/profile.css src/css/modals.css src/css/tags.css src/css/library.css
touch src/js/analysis/app.js src/js/library/library-app.js
npm run build
```
Expected: `Build complete.` with files in `server/static/dist/`.

- [ ] **Step 8: Commit**

```bash
git add package.json build.js requirements.txt requirements-dev.txt .gitignore src/ server/static/dist/
git commit -m "feat: scaffold project structure and build pipeline"
```

---

## Phase 2: Backend Foundation

### Task 2: Flask app factory and configuration

**Files:**
- Create: `server/__init__.py`
- Create: `server/config.py`
- Create: `server/auth.py`

- [ ] **Step 1: Write auth tests**

Create `tests/test_auth.py`:
```python
from server.auth import get_current_user


def test_user_from_header(app):
    with app.test_request_context(headers={"Remote-User": "PhilG"}):
        assert get_current_user() == "philg"


def test_default_user_anonymous(app):
    with app.test_request_context():
        assert get_current_user() == "anonymous"


def test_custom_header(app):
    app.config["AUTH_USER_HEADER"] = "X-Forwarded-User"
    with app.test_request_context(headers={"X-Forwarded-User": "Alice"}):
        assert get_current_user() == "alice"


def test_whitespace_stripped(app):
    with app.test_request_context(headers={"Remote-User": "  Bob  "}):
        assert get_current_user() == "bob"
```

- [ ] **Step 2: Create config.py**

```python
import os


class Config:
    VALHALLA_URL = os.environ.get("VALHALLA_URL", "http://10.0.1.25:8002")
    NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "http://10.0.1.25:8001")
    DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")
    AUTH_USER_HEADER = os.environ.get("AUTH_USER_HEADER", "Remote-User")
    BACKUP_ENABLED = os.environ.get("BACKUP_ENABLED", "true").lower() == "true"
    BACKUP_INTERVAL_HOURS = int(os.environ.get("BACKUP_INTERVAL_HOURS", "1"))
    BACKUP_DAILY_KEEP = int(os.environ.get("BACKUP_DAILY_KEEP", "7"))
    BACKUP_WEEKLY_KEEP = int(os.environ.get("BACKUP_WEEKLY_KEEP", "6"))
    BACKUP_MONTHLY_KEEP = int(os.environ.get("BACKUP_MONTHLY_KEEP", "13"))
```

- [ ] **Step 3: Create auth.py**

```python
from flask import current_app, request


def get_current_user() -> str:
    header = current_app.config["AUTH_USER_HEADER"]
    value = request.headers.get(header, "").strip()
    if not value:
        return "anonymous"
    return value.lower()
```

- [ ] **Step 4: Create app factory**

Create `server/__init__.py`:
```python
import os
from flask import Flask
from server.config import Config


def create_app(config_override=None):
    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates",
    )
    app.config.from_object(Config)
    if config_override:
        app.config.update(config_override)

    # Ensure data directories exist
    data_dir = app.config["DATA_DIR"]
    os.makedirs(os.path.join(data_dir, "gpx"), exist_ok=True)

    # Init database
    from server.models import init_app as init_db
    init_db(app)

    # Register blueprints
    from server.blueprints import register_blueprints
    register_blueprints(app)

    return app
```

- [ ] **Step 5: Create blueprint registry stub**

Create `server/blueprints/__init__.py`:
```python
def register_blueprints(app):
    # Blueprints will be registered here as they are created
    pass
```

- [ ] **Step 6: Create conftest.py with app fixture**

Create `tests/conftest.py`:
```python
import os
import pytest
from server import create_app


@pytest.fixture
def app(tmp_path):
    config = {
        "DATA_DIR": str(tmp_path / "data"),
        "TESTING": True,
        "BACKUP_ENABLED": False,
    }
    os.makedirs(config["DATA_DIR"], exist_ok=True)
    app = create_app(config_override=config)
    with app.app_context():
        yield app


@pytest.fixture
def client(app):
    return app.test_client()
```

- [ ] **Step 7: Run auth tests**

Run: `pytest tests/test_auth.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 8: Commit**

```bash
git add server/ tests/
git commit -m "feat: Flask app factory, config, and user auth"
```

### Task 3: Database schema and model layer

**Files:**
- Create: `server/models/__init__.py`
- Create: `server/models/schema.sql`
- Create: `server/models/categories.py`
- Create: `server/models/routes.py`
- Create: `server/models/tags.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write model tests**

Create `tests/test_models.py`:
```python
from server.models.categories import (
    ensure_default_category,
    create_category,
    get_categories,
    get_category,
    rename_category,
    delete_category,
)
from server.models.routes import create_route, get_routes, get_route, delete_route, move_route
from server.models.tags import set_route_tags, set_category_tags, get_tags_with_counts


def test_ensure_default_category(app):
    with app.app_context():
        cat = ensure_default_category("testuser")
        assert cat["name"] == "Default"
        assert cat["slug"] == "default"
        # Idempotent
        cat2 = ensure_default_category("testuser")
        assert cat2["id"] == cat["id"]


def test_create_category(app):
    with app.app_context():
        ensure_default_category("testuser")
        cat = create_category("testuser", "Touring", "Long rides")
        assert cat["name"] == "Touring"
        assert cat["slug"] == "touring"


def test_create_duplicate_category_fails(app):
    with app.app_context():
        ensure_default_category("testuser")
        create_category("testuser", "Touring")
        import sqlite3
        with pytest.raises(sqlite3.IntegrityError):
            create_category("testuser", "Touring")


def test_categories_isolated_by_user(app):
    with app.app_context():
        ensure_default_category("user_a")
        ensure_default_category("user_b")
        create_category("user_a", "Private")
        cats_b = get_categories("user_b")
        assert all(c["name"] != "Private" for c in cats_b)


def test_create_route(app):
    with app.app_context():
        cat = ensure_default_category("testuser")
        route = create_route(
            user_id="testuser",
            category_id=cat["id"],
            filename="test.gpx",
            storage_name="abc-123.gpx",
            title="Test Route",
            distance_km=10.5,
            min_elevation=50.0,
            max_elevation=200.0,
            max_gradient_asc=15.2,
            max_gradient_desc=-12.3,
            point_count=500,
        )
        assert route["title"] == "Test Route"
        assert route["distance_km"] == 10.5


def test_routes_isolated_by_user(app):
    with app.app_context():
        cat_a = ensure_default_category("user_a")
        cat_b = ensure_default_category("user_b")
        create_route("user_a", cat_a["id"], "a.gpx", "a-1.gpx", "Route A",
                      10, 0, 100, 5, -5, 100)
        routes_b = get_routes("user_b")
        assert len(routes_b) == 0


def test_move_route(app):
    with app.app_context():
        cat1 = ensure_default_category("testuser")
        cat2 = create_category("testuser", "Other")
        route = create_route("testuser", cat1["id"], "t.gpx", "t-1.gpx", "R",
                              1, 0, 10, 1, -1, 10)
        moved = move_route("testuser", route["id"], cat2["id"])
        assert moved["category_id"] == cat2["id"]


def test_set_route_tags(app):
    with app.app_context():
        cat = ensure_default_category("testuser")
        route = create_route("testuser", cat["id"], "t.gpx", "t-1.gpx", "R",
                              1, 0, 10, 1, -1, 10)
        tags = set_route_tags("testuser", route["id"], ["Hilly", "Scenic"])
        assert sorted(t["name"] for t in tags) == ["Hilly", "Scenic"]


def test_tags_case_insensitive_dedup(app):
    with app.app_context():
        cat = ensure_default_category("testuser")
        route = create_route("testuser", cat["id"], "t.gpx", "t-1.gpx", "R",
                              1, 0, 10, 1, -1, 10)
        set_route_tags("testuser", route["id"], ["Hilly", "hilly", "HILLY"])
        counts = get_tags_with_counts("testuser")
        hilly_tags = [t for t in counts if t["name_lower"] == "hilly"]
        assert len(hilly_tags) == 1


def test_tags_isolated_by_user(app):
    with app.app_context():
        cat_a = ensure_default_category("user_a")
        cat_b = ensure_default_category("user_b")
        route_a = create_route("user_a", cat_a["id"], "a.gpx", "a-1.gpx", "A",
                                1, 0, 10, 1, -1, 10)
        set_route_tags("user_a", route_a["id"], ["Private"])
        tags_b = get_tags_with_counts("user_b")
        assert len(tags_b) == 0


import pytest
```

- [ ] **Step 2: Create schema.sql**

Create `server/models/schema.sql`:
```sql
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'anonymous',
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, name),
    UNIQUE(user_id, slug)
);

CREATE TABLE IF NOT EXISTS routes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'anonymous',
    category_id INTEGER NOT NULL REFERENCES categories(id),
    filename TEXT NOT NULL,
    storage_name TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_accessed DATETIME,
    distance_km REAL,
    min_elevation REAL,
    max_elevation REAL,
    max_gradient_asc REAL,
    max_gradient_desc REAL,
    point_count INTEGER
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'anonymous',
    name TEXT NOT NULL,
    name_lower TEXT NOT NULL,
    UNIQUE(user_id, name_lower)
);

CREATE TABLE IF NOT EXISTS route_tags (
    route_id INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (route_id, tag_id)
);

CREATE TABLE IF NOT EXISTS category_tags (
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (category_id, tag_id)
);
```

- [ ] **Step 3: Create models/__init__.py**

```python
import os
import sqlite3
from flask import g, current_app


def get_db():
    if "db" not in g:
        db_path = os.path.join(current_app.config["DATA_DIR"], "routes.db")
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app):
    with app.app_context():
        db = get_db()
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        with open(schema_path) as f:
            db.executescript(f.read())
        db.commit()


def init_app(app):
    init_db(app)
    app.teardown_appcontext(close_db)
```

- [ ] **Step 4: Create models/categories.py**

```python
import re
from server.models import get_db


def _slugify(name):
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "untitled"


def ensure_default_category(user_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM categories WHERE user_id = ? AND slug = 'default'",
        (user_id,),
    ).fetchone()
    if row:
        return dict(row)
    db.execute(
        "INSERT INTO categories (user_id, name, slug) VALUES (?, 'Default', 'default')",
        (user_id,),
    )
    db.commit()
    return dict(db.execute(
        "SELECT * FROM categories WHERE user_id = ? AND slug = 'default'",
        (user_id,),
    ).fetchone())


def create_category(user_id, name, description=""):
    db = get_db()
    slug = _slugify(name)
    db.execute(
        "INSERT INTO categories (user_id, name, slug, description) VALUES (?, ?, ?, ?)",
        (user_id, name, slug, description),
    )
    db.commit()
    return dict(db.execute(
        "SELECT * FROM categories WHERE user_id = ? AND slug = ?",
        (user_id, slug),
    ).fetchone())


def get_categories(user_id):
    db = get_db()
    rows = db.execute(
        """SELECT c.*, COUNT(r.id) as route_count
           FROM categories c
           LEFT JOIN routes r ON r.category_id = c.id
           WHERE c.user_id = ?
           GROUP BY c.id
           ORDER BY c.name""",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_category(user_id, category_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM categories WHERE id = ? AND user_id = ?",
        (category_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def rename_category(user_id, category_id, name=None, description=None):
    db = get_db()
    cat = get_category(user_id, category_id)
    if not cat:
        return None
    if cat["slug"] == "default":
        raise ValueError("Cannot rename the Default category")
    updates = []
    params = []
    if name is not None:
        updates.append("name = ?")
        updates.append("slug = ?")
        params.extend([name, _slugify(name)])
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if not updates:
        return cat
    params.extend([category_id, user_id])
    db.execute(
        f"UPDATE categories SET {', '.join(updates)} WHERE id = ? AND user_id = ?",
        params,
    )
    db.commit()
    return get_category(user_id, category_id)


def delete_category(user_id, category_id, move_to_default=False):
    db = get_db()
    cat = get_category(user_id, category_id)
    if not cat:
        return False
    if cat["slug"] == "default":
        raise ValueError("Cannot delete the Default category")
    route_count = db.execute(
        "SELECT COUNT(*) FROM routes WHERE category_id = ? AND user_id = ?",
        (category_id, user_id),
    ).fetchone()[0]
    if route_count > 0:
        if not move_to_default:
            raise ValueError("Category is not empty")
        default = ensure_default_category(user_id)
        db.execute(
            "UPDATE routes SET category_id = ? WHERE category_id = ? AND user_id = ?",
            (default["id"], category_id, user_id),
        )
    db.execute("DELETE FROM categories WHERE id = ? AND user_id = ?", (category_id, user_id))
    db.commit()
    return True
```

- [ ] **Step 5: Create models/routes.py**

```python
from datetime import datetime, timezone
from server.models import get_db


def create_route(user_id, category_id, filename, storage_name, title,
                 distance_km=None, min_elevation=None, max_elevation=None,
                 max_gradient_asc=None, max_gradient_desc=None, point_count=None,
                 description="", notes=""):
    db = get_db()
    db.execute(
        """INSERT INTO routes
           (user_id, category_id, filename, storage_name, title, description, notes,
            distance_km, min_elevation, max_elevation, max_gradient_asc,
            max_gradient_desc, point_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, category_id, filename, storage_name, title, description, notes,
         distance_km, min_elevation, max_elevation, max_gradient_asc,
         max_gradient_desc, point_count),
    )
    db.commit()
    return get_route(user_id, db.execute("SELECT last_insert_rowid()").fetchone()[0])


def get_routes(user_id, category_id=None):
    db = get_db()
    if category_id:
        rows = db.execute(
            "SELECT * FROM routes WHERE user_id = ? AND category_id = ? ORDER BY created_at DESC",
            (user_id, category_id),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM routes WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_route(user_id, route_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM routes WHERE id = ? AND user_id = ?",
        (route_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def update_route(user_id, route_id, title=None, description=None, notes=None):
    db = get_db()
    route = get_route(user_id, route_id)
    if not route:
        return None
    updates = []
    params = []
    if title is not None:
        updates.append("title = ?")
        params.append(title)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if notes is not None:
        updates.append("notes = ?")
        params.append(notes)
    if not updates:
        return route
    params.extend([route_id, user_id])
    db.execute(
        f"UPDATE routes SET {', '.join(updates)} WHERE id = ? AND user_id = ?",
        params,
    )
    db.commit()
    return get_route(user_id, route_id)


def touch_last_accessed(user_id, route_id):
    db = get_db()
    db.execute(
        "UPDATE routes SET last_accessed = ? WHERE id = ? AND user_id = ?",
        (datetime.now(timezone.utc).isoformat(), route_id, user_id),
    )
    db.commit()


def delete_route(user_id, route_id):
    db = get_db()
    route = get_route(user_id, route_id)
    if not route:
        return None
    db.execute("DELETE FROM routes WHERE id = ? AND user_id = ?", (route_id, user_id))
    db.commit()
    return route


def move_route(user_id, route_id, new_category_id):
    db = get_db()
    route = get_route(user_id, route_id)
    if not route:
        return None
    # Verify target category belongs to user
    cat = db.execute(
        "SELECT id FROM categories WHERE id = ? AND user_id = ?",
        (new_category_id, user_id),
    ).fetchone()
    if not cat:
        return None
    db.execute(
        "UPDATE routes SET category_id = ? WHERE id = ? AND user_id = ?",
        (new_category_id, route_id, user_id),
    )
    db.commit()
    return get_route(user_id, route_id)
```

- [ ] **Step 6: Create models/tags.py**

```python
from server.models import get_db


def _get_or_create_tag(user_id, name):
    db = get_db()
    name_lower = name.lower().strip()
    row = db.execute(
        "SELECT * FROM tags WHERE user_id = ? AND name_lower = ?",
        (user_id, name_lower),
    ).fetchone()
    if row:
        return dict(row)
    db.execute(
        "INSERT INTO tags (user_id, name, name_lower) VALUES (?, ?, ?)",
        (user_id, name.strip(), name_lower),
    )
    db.commit()
    return dict(db.execute(
        "SELECT * FROM tags WHERE user_id = ? AND name_lower = ?",
        (user_id, name_lower),
    ).fetchone())


def set_route_tags(user_id, route_id, tag_names):
    db = get_db()
    db.execute("DELETE FROM route_tags WHERE route_id = ?", (route_id,))
    tags = []
    for name in tag_names:
        tag = _get_or_create_tag(user_id, name)
        db.execute(
            "INSERT OR IGNORE INTO route_tags (route_id, tag_id) VALUES (?, ?)",
            (route_id, tag["id"]),
        )
        tags.append(tag)
    db.commit()
    # Deduplicate (case-insensitive input may produce repeats)
    seen = set()
    unique = []
    for t in tags:
        if t["id"] not in seen:
            seen.add(t["id"])
            unique.append(t)
    return unique


def set_category_tags(user_id, category_id, tag_names):
    db = get_db()
    db.execute("DELETE FROM category_tags WHERE category_id = ?", (category_id,))
    tags = []
    for name in tag_names:
        tag = _get_or_create_tag(user_id, name)
        db.execute(
            "INSERT OR IGNORE INTO category_tags (category_id, tag_id) VALUES (?, ?)",
            (category_id, tag["id"]),
        )
        tags.append(tag)
    db.commit()
    seen = set()
    unique = []
    for t in tags:
        if t["id"] not in seen:
            seen.add(t["id"])
            unique.append(t)
    return unique


def get_tags_with_counts(user_id):
    db = get_db()
    rows = db.execute(
        """SELECT t.*,
           (SELECT COUNT(*) FROM route_tags rt WHERE rt.tag_id = t.id) +
           (SELECT COUNT(*) FROM category_tags ct WHERE ct.tag_id = t.id) as usage_count
           FROM tags t WHERE t.user_id = ?
           ORDER BY t.name_lower""",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_route_tags(user_id, route_id):
    db = get_db()
    rows = db.execute(
        """SELECT t.* FROM tags t
           JOIN route_tags rt ON rt.tag_id = t.id
           WHERE t.user_id = ? AND rt.route_id = ?""",
        (user_id, route_id),
    ).fetchall()
    return [dict(r) for r in rows]


def get_category_tags(user_id, category_id):
    db = get_db()
    rows = db.execute(
        """SELECT t.* FROM tags t
           JOIN category_tags ct ON ct.tag_id = t.id
           WHERE t.user_id = ? AND ct.category_id = ?""",
        (user_id, category_id),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_tag(user_id, tag_id):
    db = get_db()
    row = db.execute(
        "SELECT id FROM tags WHERE id = ? AND user_id = ?", (tag_id, user_id)
    ).fetchone()
    if not row:
        return False
    db.execute("DELETE FROM tags WHERE id = ? AND user_id = ?", (tag_id, user_id))
    db.commit()
    return True
```

- [ ] **Step 7: Run model tests**

Run: `pytest tests/test_models.py -v`
Expected: All tests PASS.

- [ ] **Step 8: Commit**

```bash
git add server/models/ tests/test_models.py
git commit -m "feat: database schema and model layer (categories, routes, tags)"
```

### Task 4: GPX parser (Python port)

**Files:**
- Create: `server/gpx_parser.py`
- Create: `tests/test_gpx_parser.py`
- Create: `tests/fixtures/sample.gpx`
- Create: `tests/fixtures/sample_no_name.gpx`
- Create: `tests/fixtures/invalid.txt`

- [ ] **Step 1: Create test fixtures**

Create `tests/fixtures/sample.gpx`:
```xml
<?xml version='1.0' encoding='UTF-8'?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
  <metadata><name>Test Route</name></metadata>
  <trk><trkseg>
    <trkpt lat="-27.4467" lon="152.9293"><ele>68.2</ele></trkpt>
    <trkpt lat="-27.4475" lon="152.9290"><ele>72.5</ele></trkpt>
    <trkpt lat="-27.4483" lon="152.9285"><ele>78.0</ele></trkpt>
    <trkpt lat="-27.4492" lon="152.9278"><ele>85.2</ele></trkpt>
    <trkpt lat="-27.4500" lon="152.9270"><ele>90.1</ele></trkpt>
    <trkpt lat="-27.4510" lon="152.9260"><ele>95.0</ele></trkpt>
    <trkpt lat="-27.4520" lon="152.9248"><ele>88.5</ele></trkpt>
    <trkpt lat="-27.4530" lon="152.9235"><ele>80.0</ele></trkpt>
    <trkpt lat="-27.4540" lon="152.9220"><ele>72.0</ele></trkpt>
    <trkpt lat="-27.4550" lon="152.9205"><ele>65.0</ele></trkpt>
  </trkseg></trk>
</gpx>
```

Create `tests/fixtures/sample_no_name.gpx`:
```xml
<?xml version='1.0' encoding='UTF-8'?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><trkseg>
    <trkpt lat="-27.4467" lon="152.9293"><ele>68.2</ele></trkpt>
    <trkpt lat="-27.4475" lon="152.9290"><ele>72.5</ele></trkpt>
  </trkseg></trk>
</gpx>
```

Create `tests/fixtures/invalid.txt`:
```
This is not a GPX file.
```

- [ ] **Step 2: Write parser tests**

Create `tests/test_gpx_parser.py`:
```python
import os
import pytest
from server.gpx_parser import parse_gpx

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def test_parse_valid_gpx():
    with open(os.path.join(FIXTURES, "sample.gpx"), "rb") as f:
        result = parse_gpx(f.read())
    assert result["name"] == "Test Route"
    assert result["point_count"] == 10
    assert result["distance_km"] > 0
    assert result["min_elevation"] == pytest.approx(65.0)
    assert result["max_elevation"] == pytest.approx(95.0)
    assert result["max_gradient_asc"] > 0
    assert result["max_gradient_desc"] < 0


def test_parse_gpx_no_name():
    with open(os.path.join(FIXTURES, "sample_no_name.gpx"), "rb") as f:
        result = parse_gpx(f.read())
    assert result["name"] is None
    assert result["point_count"] == 2


def test_parse_invalid_file():
    with open(os.path.join(FIXTURES, "invalid.txt"), "rb") as f:
        with pytest.raises(ValueError, match="Invalid GPX"):
            parse_gpx(f.read())


def test_parse_empty_gpx():
    gpx = b"""<?xml version='1.0'?>
    <gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
    <trk><trkseg></trkseg></trk></gpx>"""
    with pytest.raises(ValueError, match="No trackpoints"):
        parse_gpx(gpx)
```

- [ ] **Step 3: Implement gpx_parser.py**

Create `server/gpx_parser.py`:
```python
import math
from lxml import etree

NS = {"g": "http://www.topografix.com/GPX/1/1"}


def _haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _smooth(elevations, window=7):
    half = window // 2
    n = len(elevations)
    return [
        sum(elevations[max(0, i - half):min(n, i + half + 1)]) /
        len(elevations[max(0, i - half):min(n, i + half + 1)])
        for i in range(n)
    ]


def parse_gpx(data: bytes) -> dict:
    try:
        root = etree.fromstring(data)
    except etree.XMLSyntaxError:
        raise ValueError("Invalid GPX: not valid XML")

    trkpts = root.findall(".//g:trkpt", NS)
    if not trkpts:
        raise ValueError("No trackpoints found in GPX")

    points = []
    for pt in trkpts:
        lat = float(pt.get("lat"))
        lon = float(pt.get("lon"))
        ele_el = pt.find("g:ele", NS)
        if ele_el is not None and ele_el.text:
            points.append((lat, lon, float(ele_el.text)))

    if not points:
        raise ValueError("No trackpoints with elevation data")

    # Extract name
    name_el = root.find(".//g:metadata/g:name", NS)
    name = name_el.text if name_el is not None and name_el.text else None

    # Cumulative distances
    dists = [0.0]
    for i in range(1, len(points)):
        d = _haversine(points[i - 1][0], points[i - 1][1], points[i][0], points[i][1])
        dists.append(dists[-1] + d)

    # Smooth and compute gradients
    raw_eles = [p[2] for p in points]
    smoothed = _smooth(raw_eles, 7)
    min_grad_dist = 100  # metres

    gradients = [0.0]
    for i in range(1, len(points)):
        j = i - 1
        while j > 0 and (dists[i] - dists[j]) < min_grad_dist:
            j -= 1
        dd = dists[i] - dists[j]
        grad = ((smoothed[i] - smoothed[j]) / dd) * 100 if dd > 1 else 0
        gradients.append(grad)

    total_gain = sum(max(0, smoothed[i] - smoothed[i - 1]) for i in range(1, len(smoothed)))
    total_loss = sum(abs(min(0, smoothed[i] - smoothed[i - 1])) for i in range(1, len(smoothed)))

    return {
        "name": name,
        "point_count": len(points),
        "distance_km": round(dists[-1] / 1000, 2),
        "min_elevation": round(min(raw_eles), 1),
        "max_elevation": round(max(raw_eles), 1),
        "max_gradient_asc": round(max(gradients), 1),
        "max_gradient_desc": round(min(gradients), 1),
        "total_gain": round(total_gain, 0),
        "total_loss": round(total_loss, 0),
    }
```

- [ ] **Step 4: Run parser tests**

Run: `pytest tests/test_gpx_parser.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add server/gpx_parser.py tests/test_gpx_parser.py tests/fixtures/
git commit -m "feat: GPX parser with stats extraction (Python port)"
```

---

## Phase 3: API Endpoints

### Task 5: Route API blueprint

**Files:**
- Create: `server/blueprints/api_routes.py`
- Create: `tests/test_api_routes.py`

- [ ] **Step 1: Add sample_gpx fixture to conftest.py**

Add to `tests/conftest.py`:
```python
import os

@pytest.fixture
def sample_gpx():
    path = os.path.join(os.path.dirname(__file__), "fixtures", "sample.gpx")
    with open(path, "rb") as f:
        return f.read()


@pytest.fixture
def sample_gpx_no_name():
    path = os.path.join(os.path.dirname(__file__), "fixtures", "sample_no_name.gpx")
    with open(path, "rb") as f:
        return f.read()
```

- [ ] **Step 2: Write route API tests**

Create `tests/test_api_routes.py`:
```python
import io


def test_upload_gpx(client, sample_gpx):
    resp = client.post("/api/routes", data={
        "file": (io.BytesIO(sample_gpx), "test.gpx"),
        "title": "My Route",
    }, content_type="multipart/form-data")
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["title"] == "My Route"
    assert data["point_count"] == 10
    assert data["distance_km"] > 0


def test_upload_uses_gpx_name_as_default_title(client, sample_gpx):
    resp = client.post("/api/routes", data={
        "file": (io.BytesIO(sample_gpx), "test.gpx"),
    }, content_type="multipart/form-data")
    assert resp.status_code == 201
    assert resp.get_json()["title"] == "Test Route"


def test_upload_requires_title_when_gpx_has_none(client, sample_gpx_no_name):
    resp = client.post("/api/routes", data={
        "file": (io.BytesIO(sample_gpx_no_name), "noname.gpx"),
    }, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "title" in resp.get_json()["error"].lower()


def test_upload_invalid_file(client):
    resp = client.post("/api/routes", data={
        "file": (io.BytesIO(b"not xml"), "bad.gpx"),
        "title": "Bad",
    }, content_type="multipart/form-data")
    assert resp.status_code == 400


def test_list_routes(client, sample_gpx):
    client.post("/api/routes", data={
        "file": (io.BytesIO(sample_gpx), "a.gpx"), "title": "A",
    }, content_type="multipart/form-data")
    client.post("/api/routes", data={
        "file": (io.BytesIO(sample_gpx), "b.gpx"), "title": "B",
    }, content_type="multipart/form-data")
    resp = client.get("/api/routes")
    assert resp.status_code == 200
    assert len(resp.get_json()) == 2


def test_get_route(client, sample_gpx):
    upload = client.post("/api/routes", data={
        "file": (io.BytesIO(sample_gpx), "t.gpx"), "title": "T",
    }, content_type="multipart/form-data")
    route_id = upload.get_json()["id"]
    resp = client.get(f"/api/routes/{route_id}")
    assert resp.status_code == 200
    assert resp.get_json()["title"] == "T"


def test_get_route_not_found(client):
    assert client.get("/api/routes/999").status_code == 404


def test_update_route_metadata(client, sample_gpx):
    upload = client.post("/api/routes", data={
        "file": (io.BytesIO(sample_gpx), "t.gpx"), "title": "T",
    }, content_type="multipart/form-data")
    route_id = upload.get_json()["id"]
    resp = client.patch(f"/api/routes/{route_id}", json={
        "title": "Updated", "description": "Desc", "notes": "Note",
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["title"] == "Updated"
    assert data["description"] == "Desc"


def test_delete_route(client, sample_gpx):
    upload = client.post("/api/routes", data={
        "file": (io.BytesIO(sample_gpx), "t.gpx"), "title": "T",
    }, content_type="multipart/form-data")
    route_id = upload.get_json()["id"]
    assert client.delete(f"/api/routes/{route_id}").status_code == 204
    assert client.get(f"/api/routes/{route_id}").status_code == 404


def test_serve_gpx(client, sample_gpx):
    upload = client.post("/api/routes", data={
        "file": (io.BytesIO(sample_gpx), "t.gpx"), "title": "T",
    }, content_type="multipart/form-data")
    route_id = upload.get_json()["id"]
    resp = client.get(f"/api/gpx/{route_id}")
    assert resp.status_code == 200
    assert b"<gpx" in resp.data


def test_user_routes_isolated(client, sample_gpx):
    client.post("/api/routes", data={
        "file": (io.BytesIO(sample_gpx), "t.gpx"), "title": "UserA",
    }, content_type="multipart/form-data", headers={"Remote-User": "user_a"})
    resp = client.get("/api/routes", headers={"Remote-User": "user_b"})
    assert len(resp.get_json()) == 0


def test_cross_user_route_access_denied(client, sample_gpx):
    upload = client.post("/api/routes", data={
        "file": (io.BytesIO(sample_gpx), "t.gpx"), "title": "Private",
    }, content_type="multipart/form-data", headers={"Remote-User": "user_a"})
    route_id = upload.get_json()["id"]
    assert client.get(f"/api/routes/{route_id}", headers={"Remote-User": "user_b"}).status_code == 404
```

- [ ] **Step 3: Implement api_routes.py and api_gpx.py blueprints**

Create `server/blueprints/api_routes.py`:
```python
import os
import uuid
from flask import Blueprint, request, jsonify, current_app
from server.auth import get_current_user
from server.gpx_parser import parse_gpx
from server.models.categories import ensure_default_category, get_category
from server.models.routes import (
    create_route, get_routes, get_route, update_route, delete_route, move_route,
)

bp = Blueprint("api_routes", __name__, url_prefix="/api")


@bp.before_request
def ensure_user_setup():
    ensure_default_category(get_current_user())


@bp.route("/routes", methods=["GET"])
def list_routes():
    user_id = get_current_user()
    category_id = request.args.get("category_id", type=int)
    routes = get_routes(user_id, category_id=category_id)
    return jsonify(routes)


@bp.route("/routes", methods=["POST"])
def upload_route():
    user_id = get_current_user()
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file provided"}), 400

    data = file.read()
    try:
        stats = parse_gpx(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    title = request.form.get("title", "").strip() or stats.get("name")
    if not title:
        return jsonify({"error": "Title is required (GPX has no <name>)"}), 400

    category_id = request.form.get("category_id", type=int)
    if not category_id:
        default = ensure_default_category(user_id)
        category_id = default["id"]
    else:
        cat = get_category(user_id, category_id)
        if not cat:
            return jsonify({"error": "Category not found"}), 404

    storage_name = f"{uuid.uuid4()}.gpx"
    cat = get_category(user_id, category_id)
    gpx_dir = os.path.join(
        current_app.config["DATA_DIR"], "gpx", user_id, cat["slug"]
    )
    os.makedirs(gpx_dir, exist_ok=True)
    with open(os.path.join(gpx_dir, storage_name), "wb") as f:
        f.write(data)

    route = create_route(
        user_id=user_id,
        category_id=category_id,
        filename=file.filename,
        storage_name=storage_name,
        title=title,
        description=request.form.get("description", ""),
        notes=request.form.get("notes", ""),
        distance_km=stats["distance_km"],
        min_elevation=stats["min_elevation"],
        max_elevation=stats["max_elevation"],
        max_gradient_asc=stats["max_gradient_asc"],
        max_gradient_desc=stats["max_gradient_desc"],
        point_count=stats["point_count"],
    )
    return jsonify(route), 201


@bp.route("/routes/<int:route_id>", methods=["GET"])
def get_route_detail(route_id):
    route = get_route(get_current_user(), route_id)
    if not route:
        return jsonify({"error": "Not found"}), 404
    return jsonify(route)


@bp.route("/routes/<int:route_id>", methods=["PATCH"])
def patch_route(route_id):
    user_id = get_current_user()
    data = request.get_json(silent=True) or {}
    route = update_route(user_id, route_id, **{
        k: v for k, v in data.items() if k in ("title", "description", "notes")
    })
    if not route:
        return jsonify({"error": "Not found"}), 404
    return jsonify(route)


@bp.route("/routes/<int:route_id>", methods=["DELETE"])
def remove_route(route_id):
    user_id = get_current_user()
    route = delete_route(user_id, route_id)
    if not route:
        return jsonify({"error": "Not found"}), 404
    # Remove GPX file
    cat = get_category(user_id, route["category_id"])
    if cat:
        filepath = os.path.join(
            current_app.config["DATA_DIR"], "gpx", user_id, cat["slug"], route["storage_name"]
        )
        if os.path.exists(filepath):
            os.remove(filepath)
    return "", 204


@bp.route("/routes/<int:route_id>/move", methods=["PATCH"])
def move_route_endpoint(route_id):
    user_id = get_current_user()
    data = request.get_json(silent=True) or {}
    new_cat_id = data.get("category_id")
    if not new_cat_id:
        return jsonify({"error": "category_id required"}), 400

    # Get current route to find old file path
    old_route = get_route(user_id, route_id)
    if not old_route:
        return jsonify({"error": "Not found"}), 404

    old_cat = get_category(user_id, old_route["category_id"])
    new_cat = get_category(user_id, new_cat_id)
    if not new_cat:
        return jsonify({"error": "Target category not found"}), 404

    route = move_route(user_id, route_id, new_cat_id)
    if not route:
        return jsonify({"error": "Not found"}), 404

    # Move file on disk
    data_dir = current_app.config["DATA_DIR"]
    old_path = os.path.join(data_dir, "gpx", user_id, old_cat["slug"], route["storage_name"])
    new_dir = os.path.join(data_dir, "gpx", user_id, new_cat["slug"])
    os.makedirs(new_dir, exist_ok=True)
    new_path = os.path.join(new_dir, route["storage_name"])
    if os.path.exists(old_path):
        os.rename(old_path, new_path)

    return jsonify(route)
```

Create `server/blueprints/api_gpx.py`:
```python
import os
from flask import Blueprint, send_file, jsonify, current_app
from server.auth import get_current_user
from server.models.routes import get_route, touch_last_accessed
from server.models.categories import get_category, ensure_default_category

bp = Blueprint("api_gpx", __name__, url_prefix="/api")


@bp.before_request
def ensure_user_setup():
    ensure_default_category(get_current_user())


@bp.route("/gpx/<int:route_id>")
def serve_gpx(route_id):
    user_id = get_current_user()
    route = get_route(user_id, route_id)
    if not route:
        return jsonify({"error": "Not found"}), 404

    cat = get_category(user_id, route["category_id"])
    filepath = os.path.join(
        current_app.config["DATA_DIR"], "gpx", user_id, cat["slug"], route["storage_name"]
    )
    if not os.path.exists(filepath):
        return jsonify({"error": "GPX file missing"}), 404

    touch_last_accessed(user_id, route_id)
    return send_file(filepath, mimetype="application/gpx+xml")
```

- [ ] **Step 4: Register blueprints**

Update `server/blueprints/__init__.py`:
```python
def register_blueprints(app):
    from server.blueprints.api_routes import bp as routes_bp
    from server.blueprints.api_gpx import bp as gpx_bp
    app.register_blueprint(routes_bp)
    app.register_blueprint(gpx_bp)
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_api_routes.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add server/blueprints/ tests/test_api_routes.py tests/conftest.py
git commit -m "feat: route API endpoints (upload, list, get, update, delete, move, serve GPX)"
```

### Task 6: Category API blueprint

**Files:**
- Create: `server/blueprints/api_categories.py`
- Create: `tests/test_api_categories.py`

- [ ] **Step 1: Write category API tests**

Create `tests/test_api_categories.py`:
```python
def test_default_category_exists(client):
    resp = client.get("/api/categories")
    assert resp.status_code == 200
    cats = resp.get_json()
    assert any(c["name"] == "Default" for c in cats)


def test_create_category(client):
    resp = client.post("/api/categories", json={"name": "Touring", "description": "Long rides"})
    assert resp.status_code == 201
    assert resp.get_json()["name"] == "Touring"


def test_create_duplicate_category(client):
    client.post("/api/categories", json={"name": "Touring"})
    resp = client.post("/api/categories", json={"name": "Touring"})
    assert resp.status_code == 409


def test_rename_category(client):
    create = client.post("/api/categories", json={"name": "Old Name"})
    cat_id = create.get_json()["id"]
    resp = client.patch(f"/api/categories/{cat_id}", json={"name": "New Name"})
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "New Name"


def test_rename_default_category_fails(client):
    cats = client.get("/api/categories").get_json()
    default_id = next(c["id"] for c in cats if c["name"] == "Default")
    resp = client.patch(f"/api/categories/{default_id}", json={"name": "Nope"})
    assert resp.status_code == 400


def test_delete_empty_category(client):
    create = client.post("/api/categories", json={"name": "Empty"})
    cat_id = create.get_json()["id"]
    assert client.delete(f"/api/categories/{cat_id}").status_code == 204


def test_delete_default_category_fails(client):
    cats = client.get("/api/categories").get_json()
    default_id = next(c["id"] for c in cats if c["name"] == "Default")
    assert client.delete(f"/api/categories/{default_id}").status_code == 400


def test_delete_nonempty_category_fails(client, sample_gpx):
    import io
    create = client.post("/api/categories", json={"name": "HasRoutes"})
    cat_id = create.get_json()["id"]
    client.post("/api/routes", data={
        "file": (io.BytesIO(sample_gpx), "t.gpx"), "title": "T", "category_id": str(cat_id),
    }, content_type="multipart/form-data")
    assert client.delete(f"/api/categories/{cat_id}").status_code == 400


def test_delete_nonempty_with_move_to_default(client, sample_gpx):
    import io
    create = client.post("/api/categories", json={"name": "Temp"})
    cat_id = create.get_json()["id"]
    client.post("/api/routes", data={
        "file": (io.BytesIO(sample_gpx), "t.gpx"), "title": "T", "category_id": str(cat_id),
    }, content_type="multipart/form-data")
    resp = client.delete(f"/api/categories/{cat_id}?move_to_default=true")
    assert resp.status_code == 204
    # Route should now be in Default
    routes = client.get("/api/routes").get_json()
    assert len(routes) == 1


def test_update_category_description(client):
    create = client.post("/api/categories", json={"name": "Cat"})
    cat_id = create.get_json()["id"]
    resp = client.patch(f"/api/categories/{cat_id}", json={"description": "Updated desc"})
    assert resp.get_json()["description"] == "Updated desc"


def test_categories_isolated_by_user(client):
    client.post("/api/categories", json={"name": "Private"}, headers={"Remote-User": "user_a"})
    resp = client.get("/api/categories", headers={"Remote-User": "user_b"})
    cats = resp.get_json()
    assert all(c["name"] != "Private" for c in cats)
```

- [ ] **Step 2: Implement api_categories.py**

Create `server/blueprints/api_categories.py`:
```python
import os
from flask import Blueprint, request, jsonify, current_app
from server.auth import get_current_user
from server.models.categories import (
    ensure_default_category, create_category, get_categories,
    get_category, rename_category, delete_category,
)
import sqlite3

bp = Blueprint("api_categories", __name__, url_prefix="/api")


@bp.before_request
def ensure_user_setup():
    ensure_default_category(get_current_user())


@bp.route("/categories", methods=["GET"])
def list_categories():
    return jsonify(get_categories(get_current_user()))


@bp.route("/categories", methods=["POST"])
def create_cat():
    user_id = get_current_user()
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Name required"}), 400
    try:
        cat = create_category(user_id, name, data.get("description", ""))
    except sqlite3.IntegrityError:
        return jsonify({"error": "Category already exists"}), 409
    # Create folder
    gpx_dir = os.path.join(current_app.config["DATA_DIR"], "gpx", user_id, cat["slug"])
    os.makedirs(gpx_dir, exist_ok=True)
    return jsonify(cat), 201


@bp.route("/categories/<int:cat_id>", methods=["PATCH"])
def update_cat(cat_id):
    user_id = get_current_user()
    data = request.get_json(silent=True) or {}
    old_cat = get_category(user_id, cat_id)
    if not old_cat:
        return jsonify({"error": "Not found"}), 404
    try:
        cat = rename_category(user_id, cat_id, data.get("name"), data.get("description"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    # Rename folder if slug changed
    if cat and cat["slug"] != old_cat["slug"]:
        data_dir = current_app.config["DATA_DIR"]
        old_dir = os.path.join(data_dir, "gpx", user_id, old_cat["slug"])
        new_dir = os.path.join(data_dir, "gpx", user_id, cat["slug"])
        if os.path.exists(old_dir):
            os.rename(old_dir, new_dir)
    return jsonify(cat)


@bp.route("/categories/<int:cat_id>", methods=["DELETE"])
def delete_cat(cat_id):
    user_id = get_current_user()
    move_to_default = request.args.get("move_to_default", "").lower() == "true"
    cat = get_category(user_id, cat_id)
    if not cat:
        return jsonify({"error": "Not found"}), 404

    try:
        # If moving routes, move files on disk first
        if move_to_default:
            from server.models.routes import get_routes
            default = ensure_default_category(user_id)
            routes = get_routes(user_id, category_id=cat_id)
            data_dir = current_app.config["DATA_DIR"]
            new_dir = os.path.join(data_dir, "gpx", user_id, default["slug"])
            os.makedirs(new_dir, exist_ok=True)
            for route in routes:
                old_path = os.path.join(data_dir, "gpx", user_id, cat["slug"], route["storage_name"])
                new_path = os.path.join(new_dir, route["storage_name"])
                if os.path.exists(old_path):
                    os.rename(old_path, new_path)

        delete_category(user_id, cat_id, move_to_default=move_to_default)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # Remove empty folder
    folder = os.path.join(current_app.config["DATA_DIR"], "gpx", user_id, cat["slug"])
    if os.path.exists(folder) and not os.listdir(folder):
        os.rmdir(folder)

    return "", 204
```

- [ ] **Step 3: Register blueprint**

Update `server/blueprints/__init__.py` to add:
```python
    from server.blueprints.api_categories import bp as categories_bp
    app.register_blueprint(categories_bp)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_api_categories.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add server/blueprints/ tests/test_api_categories.py
git commit -m "feat: category API endpoints (list, create, rename, delete)"
```

### Task 7: Tag API blueprint

**Files:**
- Create: `server/blueprints/api_tags.py`
- Create: `tests/test_api_tags.py`

- [ ] **Step 1: Write tag API tests**

Create `tests/test_api_tags.py`:
```python
import io


def _upload_route(client, sample_gpx, title="T"):
    resp = client.post("/api/routes", data={
        "file": (io.BytesIO(sample_gpx), "t.gpx"), "title": title,
    }, content_type="multipart/form-data")
    return resp.get_json()["id"]


def test_set_route_tags(client, sample_gpx):
    route_id = _upload_route(client, sample_gpx)
    resp = client.put(f"/api/routes/{route_id}/tags", json={"tags": ["Hilly", "Scenic"]})
    assert resp.status_code == 200
    tags = resp.get_json()["tags"]
    assert sorted(t["name"] for t in tags) == ["Hilly", "Scenic"]


def test_set_category_tags(client):
    cat = client.post("/api/categories", json={"name": "Cat"}).get_json()
    resp = client.put(f"/api/categories/{cat['id']}/tags", json={"tags": ["Urban"]})
    assert resp.status_code == 200


def test_tags_auto_created(client, sample_gpx):
    route_id = _upload_route(client, sample_gpx)
    client.put(f"/api/routes/{route_id}/tags", json={"tags": ["NewTag"]})
    resp = client.get("/api/tags")
    names = [t["name_lower"] for t in resp.get_json()]
    assert "newtag" in names


def test_tags_case_insensitive_dedup(client, sample_gpx):
    route_id = _upload_route(client, sample_gpx)
    client.put(f"/api/routes/{route_id}/tags", json={"tags": ["Hilly", "hilly", "HILLY"]})
    resp = client.get("/api/tags")
    hilly = [t for t in resp.get_json() if t["name_lower"] == "hilly"]
    assert len(hilly) == 1


def test_list_tags_with_counts(client, sample_gpx):
    r1 = _upload_route(client, sample_gpx, "R1")
    r2 = _upload_route(client, sample_gpx, "R2")
    client.put(f"/api/routes/{r1}/tags", json={"tags": ["Shared"]})
    client.put(f"/api/routes/{r2}/tags", json={"tags": ["Shared"]})
    resp = client.get("/api/tags")
    shared = next(t for t in resp.get_json() if t["name_lower"] == "shared")
    assert shared["usage_count"] == 2


def test_delete_tag(client, sample_gpx):
    route_id = _upload_route(client, sample_gpx)
    client.put(f"/api/routes/{route_id}/tags", json={"tags": ["ToDelete"]})
    tags = client.get("/api/tags").get_json()
    tag_id = next(t["id"] for t in tags if t["name_lower"] == "todelete")
    assert client.delete(f"/api/tags/{tag_id}").status_code == 204
    tags_after = client.get("/api/tags").get_json()
    assert all(t["name_lower"] != "todelete" for t in tags_after)


def test_tags_isolated_by_user(client, sample_gpx):
    resp = client.post("/api/routes", data={
        "file": (io.BytesIO(sample_gpx), "t.gpx"), "title": "T",
    }, content_type="multipart/form-data", headers={"Remote-User": "user_a"})
    route_id = resp.get_json()["id"]
    client.put(f"/api/routes/{route_id}/tags", json={"tags": ["Private"]},
               headers={"Remote-User": "user_a"})
    resp = client.get("/api/tags", headers={"Remote-User": "user_b"})
    assert len(resp.get_json()) == 0
```

- [ ] **Step 2: Implement api_tags.py**

Create `server/blueprints/api_tags.py`:
```python
from flask import Blueprint, request, jsonify
from server.auth import get_current_user
from server.models.categories import ensure_default_category, get_category
from server.models.routes import get_route
from server.models.tags import (
    set_route_tags, set_category_tags, get_tags_with_counts,
    get_route_tags, get_category_tags, delete_tag,
)

bp = Blueprint("api_tags", __name__, url_prefix="/api")


@bp.before_request
def ensure_user_setup():
    ensure_default_category(get_current_user())


@bp.route("/tags", methods=["GET"])
def list_tags():
    return jsonify(get_tags_with_counts(get_current_user()))


@bp.route("/tags/<int:tag_id>", methods=["DELETE"])
def remove_tag(tag_id):
    if not delete_tag(get_current_user(), tag_id):
        return jsonify({"error": "Not found"}), 404
    return "", 204


@bp.route("/routes/<int:route_id>/tags", methods=["PUT"])
def set_route_tags_endpoint(route_id):
    user_id = get_current_user()
    route = get_route(user_id, route_id)
    if not route:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json(silent=True) or {}
    tag_names = data.get("tags", [])
    tags = set_route_tags(user_id, route_id, tag_names)
    route = get_route(user_id, route_id)
    route["tags"] = tags
    return jsonify(route)


@bp.route("/categories/<int:cat_id>/tags", methods=["PUT"])
def set_category_tags_endpoint(cat_id):
    user_id = get_current_user()
    cat = get_category(user_id, cat_id)
    if not cat:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json(silent=True) or {}
    tag_names = data.get("tags", [])
    tags = set_category_tags(user_id, cat_id, tag_names)
    cat["tags"] = tags
    return jsonify(cat)
```

- [ ] **Step 3: Register blueprint and run tests**

Update `server/blueprints/__init__.py` to add:
```python
    from server.blueprints.api_tags import bp as tags_bp
    app.register_blueprint(tags_bp)
```

Run: `pytest tests/test_api_tags.py -v`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add server/blueprints/ tests/test_api_tags.py
git commit -m "feat: tag API endpoints (list, set on routes/categories, delete)"
```

### Task 8: Service proxy blueprint

**Files:**
- Create: `server/blueprints/proxy.py`
- Create: `tests/test_api_proxy.py`

- [ ] **Step 1: Write proxy tests**

Create `tests/test_api_proxy.py`:
```python
from unittest.mock import patch, MagicMock
import requests


def _mock_response(status=200, json_data=None, content=b"ok", headers=None):
    resp = MagicMock()
    resp.status_code = status
    resp.content = content
    resp.headers = headers or {"Content-Type": "application/json"}
    return resp


@patch("server.blueprints.proxy.requests.request")
def test_valhalla_proxy(mock_req, client):
    mock_req.return_value = _mock_response(json_data={"height": [100]})
    resp = client.post("/proxy/valhalla/height", json={"shape": []})
    assert resp.status_code == 200
    mock_req.assert_called_once()
    args = mock_req.call_args
    assert "/height" in args[1]["url"] or "/height" in args[0][1]


@patch("server.blueprints.proxy.requests.request")
def test_nominatim_proxy(mock_req, client):
    mock_req.return_value = _mock_response(content=b'{"status":"ok"}')
    resp = client.get("/proxy/nominatim/status")
    assert resp.status_code == 200


@patch("server.blueprints.proxy.requests.request")
def test_proxy_upstream_failure(mock_req, client):
    mock_req.side_effect = requests.Timeout("timed out")
    resp = client.get("/proxy/valhalla/status")
    assert resp.status_code == 502
    assert "error" in resp.get_json()
```

- [ ] **Step 2: Implement proxy.py**

Create `server/blueprints/proxy.py`:
```python
import requests
from flask import Blueprint, request as flask_request, Response, jsonify, current_app

bp = Blueprint("proxy", __name__, url_prefix="/proxy")

PROXY_TIMEOUT = 30


def _proxy(upstream_base, path):
    url = f"{upstream_base}/{path}"
    if flask_request.query_string:
        url += f"?{flask_request.query_string.decode()}"

    headers = {}
    if flask_request.content_type:
        headers["Content-Type"] = flask_request.content_type

    try:
        resp = requests.request(
            method=flask_request.method,
            url=url,
            headers=headers,
            data=flask_request.get_data(),
            timeout=PROXY_TIMEOUT,
        )
    except (requests.Timeout, requests.ConnectionError) as e:
        return jsonify({"error": f"Upstream service unavailable: {e}"}), 502

    return Response(
        resp.content,
        status=resp.status_code,
        headers={"Content-Type": resp.headers.get("Content-Type", "application/octet-stream")},
    )


@bp.route("/valhalla/<path:path>", methods=["GET", "POST", "PUT", "DELETE"])
def valhalla_proxy(path):
    return _proxy(current_app.config["VALHALLA_URL"], path)


@bp.route("/nominatim/<path:path>", methods=["GET", "POST", "PUT", "DELETE"])
def nominatim_proxy(path):
    return _proxy(current_app.config["NOMINATIM_URL"], path)
```

- [ ] **Step 3: Register and run tests**

Update `server/blueprints/__init__.py` to add:
```python
    from server.blueprints.proxy import bp as proxy_bp
    app.register_blueprint(proxy_bp)
```

Run: `pytest tests/test_api_proxy.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add server/blueprints/proxy.py tests/test_api_proxy.py
git commit -m "feat: Valhalla/Nominatim reverse proxy endpoints"
```

### Task 9: Backup system

**Files:**
- Create: `server/backup.py`
- Create: `tests/test_backup.py`

- [ ] **Step 1: Write backup tests**

Create `tests/test_backup.py`:
```python
import os
import tarfile
import sqlite3
from datetime import date, timedelta
from server.backup import create_backup, promote_and_purge, start_backup_scheduler


def _setup_data_dir(tmp_path):
    """Create a minimal data dir with a DB and GPX file."""
    data_dir = str(tmp_path / "data")
    os.makedirs(os.path.join(data_dir, "gpx", "testuser", "default"), exist_ok=True)
    # Create a minimal DB
    db_path = os.path.join(data_dir, "routes.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE test (id INTEGER)")
    conn.execute("INSERT INTO test VALUES (1)")
    conn.commit()
    conn.close()
    # Create a GPX file
    with open(os.path.join(data_dir, "gpx", "testuser", "default", "test.gpx"), "w") as f:
        f.write("<gpx/>")
    return data_dir


def test_create_daily_backup(tmp_path):
    data_dir = _setup_data_dir(tmp_path)
    path = create_backup(data_dir, date.today())
    assert path is not None
    assert os.path.exists(path)
    assert "daily" in path


def test_backup_contains_db_and_gpx(tmp_path):
    data_dir = _setup_data_dir(tmp_path)
    path = create_backup(data_dir, date.today())
    with tarfile.open(path, "r:gz") as tar:
        names = tar.getnames()
    assert any("routes.db" in n for n in names)
    assert any("test.gpx" in n for n in names)


def test_skip_duplicate_daily(tmp_path):
    data_dir = _setup_data_dir(tmp_path)
    path1 = create_backup(data_dir, date.today())
    path2 = create_backup(data_dir, date.today())
    assert path1 == path2  # Same path, not recreated


def test_daily_purge_promotes_to_weekly(tmp_path):
    data_dir = _setup_data_dir(tmp_path)
    daily_dir = os.path.join(data_dir, "backups", "daily")
    weekly_dir = os.path.join(data_dir, "backups", "weekly")
    os.makedirs(daily_dir, exist_ok=True)
    os.makedirs(weekly_dir, exist_ok=True)
    # Create 8 daily backups
    for i in range(8):
        d = date.today() - timedelta(days=i)
        path = os.path.join(daily_dir, f"backup-{d.isoformat()}.tar.gz")
        with tarfile.open(path, "w:gz") as tar:
            pass  # Empty tarball
    promote_and_purge(data_dir, daily_keep=7, weekly_keep=6, monthly_keep=13)
    dailies = os.listdir(daily_dir)
    weeklies = os.listdir(weekly_dir)
    assert len(dailies) == 7
    assert len(weeklies) == 1


def test_weekly_purge_promotes_to_monthly(tmp_path):
    data_dir = _setup_data_dir(tmp_path)
    weekly_dir = os.path.join(data_dir, "backups", "weekly")
    monthly_dir = os.path.join(data_dir, "backups", "monthly")
    os.makedirs(weekly_dir, exist_ok=True)
    os.makedirs(monthly_dir, exist_ok=True)
    for i in range(7):
        d = date.today() - timedelta(weeks=i)
        path = os.path.join(weekly_dir, f"backup-{d.isoformat()}.tar.gz")
        with tarfile.open(path, "w:gz") as tar:
            pass
    promote_and_purge(data_dir, daily_keep=7, weekly_keep=6, monthly_keep=13)
    assert len(os.listdir(weekly_dir)) == 6
    assert len(os.listdir(monthly_dir)) == 1


def test_monthly_purge_promotes_to_yearly(tmp_path):
    data_dir = _setup_data_dir(tmp_path)
    monthly_dir = os.path.join(data_dir, "backups", "monthly")
    yearly_dir = os.path.join(data_dir, "backups", "yearly")
    os.makedirs(monthly_dir, exist_ok=True)
    os.makedirs(yearly_dir, exist_ok=True)
    for i in range(14):
        d = date.today() - timedelta(days=30 * i)
        path = os.path.join(monthly_dir, f"backup-{d.isoformat()}.tar.gz")
        with tarfile.open(path, "w:gz") as tar:
            pass
    promote_and_purge(data_dir, daily_keep=7, weekly_keep=6, monthly_keep=13)
    assert len(os.listdir(monthly_dir)) == 13
    assert len(os.listdir(yearly_dir)) == 1


def test_yearly_never_purged(tmp_path):
    data_dir = _setup_data_dir(tmp_path)
    yearly_dir = os.path.join(data_dir, "backups", "yearly")
    os.makedirs(yearly_dir, exist_ok=True)
    for i in range(5):
        d = date.today() - timedelta(days=365 * i)
        path = os.path.join(yearly_dir, f"backup-{d.isoformat()}.tar.gz")
        with tarfile.open(path, "w:gz") as tar:
            pass
    promote_and_purge(data_dir, daily_keep=7, weekly_keep=6, monthly_keep=13)
    assert len(os.listdir(yearly_dir)) == 5


def test_backup_db_consistency(tmp_path):
    data_dir = _setup_data_dir(tmp_path)
    path = create_backup(data_dir, date.today())
    # Extract and verify DB is valid
    with tarfile.open(path, "r:gz") as tar:
        for member in tar.getmembers():
            if "routes.db" in member.name:
                tar.extract(member, tmp_path / "extracted")
                db_path = os.path.join(tmp_path, "extracted", member.name)
                conn = sqlite3.connect(db_path)
                val = conn.execute("SELECT id FROM test").fetchone()[0]
                conn.close()
                assert val == 1
                return
    assert False, "routes.db not found in backup"
```

- [ ] **Step 2: Implement backup.py**

Create `server/backup.py`:
```python
import os
import logging
import shutil
import sqlite3
import tarfile
import threading
from datetime import date

logger = logging.getLogger(__name__)

TIERS = ["daily", "weekly", "monthly", "yearly"]


def create_backup(data_dir, today=None):
    today = today or date.today()
    daily_dir = os.path.join(data_dir, "backups", "daily")
    os.makedirs(daily_dir, exist_ok=True)

    filename = f"backup-{today.isoformat()}.tar.gz"
    filepath = os.path.join(daily_dir, filename)

    if os.path.exists(filepath):
        logger.info("Daily backup already exists: %s", filename)
        return filepath

    # Consistent DB copy via sqlite3 backup API
    db_src = os.path.join(data_dir, "routes.db")
    db_tmp = os.path.join(data_dir, "backups", "routes_backup.db")
    if os.path.exists(db_src):
        src_conn = sqlite3.connect(db_src)
        dst_conn = sqlite3.connect(db_tmp)
        src_conn.backup(dst_conn)
        src_conn.close()
        dst_conn.close()

    # Create tarball
    with tarfile.open(filepath, "w:gz") as tar:
        if os.path.exists(db_tmp):
            tar.add(db_tmp, arcname="routes.db")
        gpx_dir = os.path.join(data_dir, "gpx")
        if os.path.exists(gpx_dir):
            tar.add(gpx_dir, arcname="gpx")

    # Clean up temp DB copy
    if os.path.exists(db_tmp):
        os.remove(db_tmp)

    logger.info("Created daily backup: %s", filename)
    return filepath


def promote_and_purge(data_dir, daily_keep=7, weekly_keep=6, monthly_keep=13):
    keeps = {"daily": daily_keep, "weekly": weekly_keep, "monthly": monthly_keep}

    for tier_idx in range(len(TIERS) - 1):
        tier = TIERS[tier_idx]
        next_tier = TIERS[tier_idx + 1]
        keep = keeps.get(tier, 999999)

        tier_dir = os.path.join(data_dir, "backups", tier)
        next_dir = os.path.join(data_dir, "backups", next_tier)

        if not os.path.exists(tier_dir):
            continue
        os.makedirs(next_dir, exist_ok=True)

        files = sorted(os.listdir(tier_dir))
        while len(files) > keep:
            oldest = files.pop(0)
            src = os.path.join(tier_dir, oldest)
            dst = os.path.join(next_dir, oldest)
            shutil.move(src, dst)
            logger.info("Promoted %s from %s to %s", oldest, tier, next_tier)


def _run_backup(data_dir, interval_hours, daily_keep, weekly_keep, monthly_keep):
    try:
        create_backup(data_dir)
        promote_and_purge(data_dir, daily_keep, weekly_keep, monthly_keep)
    except Exception:
        logger.exception("Backup failed")

    timer = threading.Timer(
        interval_hours * 3600,
        _run_backup,
        args=(data_dir, interval_hours, daily_keep, weekly_keep, monthly_keep),
    )
    timer.daemon = True
    timer.start()


def start_backup_scheduler(app):
    if not app.config.get("BACKUP_ENABLED", True):
        logger.info("Backups disabled")
        return

    data_dir = app.config["DATA_DIR"]
    interval = app.config.get("BACKUP_INTERVAL_HOURS", 1)
    daily_keep = app.config.get("BACKUP_DAILY_KEEP", 7)
    weekly_keep = app.config.get("BACKUP_WEEKLY_KEEP", 6)
    monthly_keep = app.config.get("BACKUP_MONTHLY_KEEP", 13)

    logger.info("Starting backup scheduler (every %dh)", interval)
    _run_backup(data_dir, interval, daily_keep, weekly_keep, monthly_keep)
```

- [ ] **Step 3: Wire backup into app factory**

Add to `server/__init__.py` after blueprint registration:
```python
    # Start backup scheduler (not in testing)
    if not app.config.get("TESTING"):
        from server.backup import start_backup_scheduler
        start_backup_scheduler(app)
```

- [ ] **Step 4: Run backup tests**

Run: `pytest tests/test_backup.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add server/backup.py tests/test_backup.py server/__init__.py
git commit -m "feat: automated backup system with tiered retention"
```

---

## Phase 4: Frontend — CSS Extraction and Analysis Page

### Task 10: Extract CSS from index.html into modules

**Files:**
- Create: `src/css/base.css`
- Create: `src/css/nav.css`
- Create: `src/css/stats.css`
- Create: `src/css/settings.css`
- Create: `src/css/legend.css`
- Create: `src/css/map.css`
- Create: `src/css/profile.css`
- Create: `src/css/modals.css`
- Create: `src/css/tags.css`

- [ ] **Step 1: Extract CSS from index.html into individual files**

Extract each CSS block from `index.html` into its matching CSS file. The `<style>` tag in `index.html` is replaced with a `<link>` to the built bundle.

`src/css/base.css` — `*`, `body`, `.leaflet-popup-content`
`src/css/nav.css` — navigation bar styles (new — create minimal placeholder)
`src/css/stats.css` — `#stats`, `.stat`
`src/css/settings.css` — `#settings-bar`, `.setting-group`
`src/css/legend.css` — `#legend`, `.legend-item`, `.legend-swatch`, `.legend-btn`
`src/css/map.css` — `#map`, `#map-hover-panel`, `#map-hover-toggle`, `#map-hover-body`, `#ctx-menu`, `.waypoint-icon`, `.modal-marker-tip`, `.peak-tip`, `@keyframes peak-pulse`
`src/css/profile.css` — `#profile-container`, `#profile-canvas`, `#hover-info`
`src/css/modals.css` — `#grad-modal-overlay`, `#grad-modal`, `#terrain-modal-overlay`, `.gm-*`
`src/css/tags.css` — tag cloud, tag chip, tag input styles (new — create placeholder)

Each file should contain only the relevant rules extracted from the existing `index.html` `<style>` block. The exact CSS is already in `index.html` lines 8-85 — split by the categories above.

- [ ] **Step 2: Build and verify output**

Run: `npm run build`
Expected: `server/static/dist/analysis.min.css` contains all analysis styles.

- [ ] **Step 3: Commit**

```bash
git add src/css/
git commit -m "feat: extract CSS into modular files with esbuild bundling"
```

### Task 11: Split existing JS into analysis modules

**Files:**
- Create: All files under `src/js/analysis/`
- Create: `src/js/shared/theme.js`

- [ ] **Step 1: Create shared theme constants**

Create `src/js/shared/theme.js`:
```js
export const VALHALLA_PROXY = '/proxy/valhalla';
export const NOMINATIM_PROXY = '/proxy/nominatim';
```

- [ ] **Step 2: Convert existing JS files to ES modules under src/js/analysis/**

Each existing file in `js/` becomes an ES module in `src/js/analysis/` with explicit `import`/`export`. The key changes:

- All globals become exports
- `context-menu.js` (548 lines) splits into three files:
  - `context-menu.js` — menu display, waypoint CRUD (~150 lines)
  - `terrain-gradient.js` — DEM sampling, terrain modal (~200 lines)
  - `gradient-modal.js` — route gradient info modal (~150 lines)
- `map.js` (249 lines) splits into:
  - `map-init.js` — Leaflet map, tile layers, layer persistence (~80 lines)
  - `map-segments.js` — gradient segments, visibility, recoloring (~60 lines)
  - `map-markers.js` — start/end/max/min markers, position marker (~80 lines)
  - `map-hover.js` — hover panel init + events (~80 lines)
- `app.js` (208 lines) splits into:
  - `settings.js` — slider controls, presets, persistence (~80 lines)
  - `app.js` — main orchestration, wiring everything together (~100 lines)
- `gpx.js` splits into:
  - `gpx-loader.js` — `loadGPX()` function
  - `track-processor.js` — `processTrackData()`, `computeDistances()`, `computeGradDist()`, `computeGradientSections()`
- `gradient.js` stays as-is (61 lines, already focused)
- `profile.js` stays as-is (155 lines, already focused)
- `nav.js` — new, navigation bar interactions
- Hardcoded Valhalla URL `http://10.0.1.25:8002/height` replaced with import from `shared/theme.js`: `VALHALLA_PROXY + '/height'`
- localStorage keys prefixed with route ID from `document.body.dataset.routeId`

- [ ] **Step 3: Update app.js as the entry point**

`src/js/analysis/app.js` imports all modules and wires them together. esbuild bundles this into `analysis.min.js`.

- [ ] **Step 4: Build and verify**

Run: `npm run build`
Expected: `server/static/dist/analysis.min.js` created, no errors.

- [ ] **Step 5: Commit**

```bash
git add src/js/
git commit -m "feat: split analysis JS into ES modules with esbuild bundling"
```

---

## Phase 5: Templates and Pages

### Task 12: Base template and pages blueprint

**Files:**
- Create: `server/templates/_base.html`
- Create: `server/templates/analysis.html`
- Create: `server/blueprints/pages.py`

- [ ] **Step 1: Create base template**

Create `server/templates/_base.html`:
```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{% block title %}GPX Gradient Analysis{% endblock %}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
{% block css %}{% endblock %}
</head>
<body>
<nav id="main-nav">
  <a href="/" class="nav-brand">GPX Analysis</a>
  {% block nav_items %}{% endblock %}
</nav>
{% block content %}{% endblock %}
{% block scripts %}{% endblock %}
</body>
</html>
```

- [ ] **Step 2: Create analysis.html template**

Create `server/templates/analysis.html` — this wraps the existing `index.html` body content, replacing:
- The `<style>` block with `<link rel="stylesheet" href="/static/dist/analysis.min.css">`
- The inline `<script>` tags with `<script src="/static/dist/analysis.min.js"></script>`
- `data-gpx-file` set from server: `data-gpx-file="/api/gpx/{{ route.id }}"`
- `data-route-id="{{ route.id }}"` for localStorage scoping
- Add nav bar with back-to-library link and route title

- [ ] **Step 3: Create pages blueprint**

Create `server/blueprints/pages.py`:
```python
from flask import Blueprint, render_template, redirect, url_for, jsonify
from server.auth import get_current_user
from server.models.categories import ensure_default_category
from server.models.routes import get_route, touch_last_accessed

bp = Blueprint("pages", __name__)


@bp.route("/")
def library():
    ensure_default_category(get_current_user())
    return render_template("library.html")


@bp.route("/route/<int:route_id>")
def analysis(route_id):
    user_id = get_current_user()
    ensure_default_category(user_id)
    route = get_route(user_id, route_id)
    if not route:
        return redirect(url_for("pages.library"))
    touch_last_accessed(user_id, route_id)
    return render_template("analysis.html", route=route)
```

- [ ] **Step 4: Register pages blueprint**

Update `server/blueprints/__init__.py` to add:
```python
    from server.blueprints.pages import bp as pages_bp
    app.register_blueprint(pages_bp)
```

- [ ] **Step 5: Commit**

```bash
git add server/templates/ server/blueprints/pages.py server/blueprints/__init__.py
git commit -m "feat: Jinja2 templates and pages blueprint (library, analysis)"
```

### Task 13: Library page frontend

**Files:**
- Create: `server/templates/library.html`
- Create: `src/js/library/api-client.js`
- Create: `src/js/library/library-app.js`
- Create: `src/js/library/route-cards.js`
- Create: `src/js/library/category-panel.js`
- Create: `src/js/library/upload.js`
- Create: `src/js/library/metadata-editor.js`
- Create: `src/js/library/tag-input.js`
- Create: `src/js/library/tag-cloud.js`
- Create: `src/js/library/confirm-modal.js`
- Create: `src/css/library.css`

- [ ] **Step 1: Create api-client.js**

```js
export async function apiFetch(path, options = {}) {
  const resp = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ error: resp.statusText }));
    throw new Error(err.error || resp.statusText);
  }
  if (resp.status === 204) return null;
  return resp.json();
}

export const api = {
  getRoutes: (categoryId) => apiFetch(categoryId ? `/api/routes?category_id=${categoryId}` : '/api/routes'),
  getRoute: (id) => apiFetch(`/api/routes/${id}`),
  updateRoute: (id, data) => apiFetch(`/api/routes/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteRoute: (id) => apiFetch(`/api/routes/${id}`, { method: 'DELETE' }),
  moveRoute: (id, categoryId) => apiFetch(`/api/routes/${id}/move`, { method: 'PATCH', body: JSON.stringify({ category_id: categoryId }) }),
  getCategories: () => apiFetch('/api/categories'),
  createCategory: (data) => apiFetch('/api/categories', { method: 'POST', body: JSON.stringify(data) }),
  updateCategory: (id, data) => apiFetch(`/api/categories/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteCategory: (id, moveToDefault) => apiFetch(`/api/categories/${id}${moveToDefault ? '?move_to_default=true' : ''}`, { method: 'DELETE' }),
  getTags: () => apiFetch('/api/tags'),
  setRouteTags: (id, tags) => apiFetch(`/api/routes/${id}/tags`, { method: 'PUT', body: JSON.stringify({ tags }) }),
  setCategoryTags: (id, tags) => apiFetch(`/api/categories/${id}/tags`, { method: 'PUT', body: JSON.stringify({ tags }) }),
  deleteTag: (id) => apiFetch(`/api/tags/${id}`, { method: 'DELETE' }),
};
```

- [ ] **Step 2: Create each library module**

Each module is a focused file (<150 lines) handling one UI concern:

- `confirm-modal.js` — exports `confirmAction(message)` returning a Promise that resolves true/false via an inline dark-themed modal
- `tag-input.js` — exports `createTagInput(container, existingTags, onChange)` rendering a chip-based tag editor with auto-complete
- `tag-cloud.js` — exports `renderTagCloud(container, tags, onTagClick)` rendering sized tag links
- `route-cards.js` — exports `renderRouteCards(container, routes, handlers)` rendering route cards grouped by category
- `category-panel.js` — exports `renderCategoryPanel(container, categories, handlers)` with create/rename/delete UI
- `upload.js` — exports `initUpload(container, categories, onUploaded)` with drag-drop, file picker, title validation
- `metadata-editor.js` — exports `showMetadataEditor(route, onSave)` inline modal for editing title/description/notes
- `library-app.js` — entry point, imports all modules, fetches initial data, wires up events

- [ ] **Step 3: Create library.html template**

```html
{% extends "_base.html" %}
{% block title %}Route Library{% endblock %}
{% block css %}
<link rel="stylesheet" href="/static/dist/library.min.css">
{% endblock %}
{% block content %}
<div id="library-container">
  <aside id="sidebar">
    <div id="tag-cloud-container"></div>
    <div id="category-panel"></div>
  </aside>
  <main id="route-list">
    <div id="upload-area"></div>
    <div id="routes-container"></div>
  </main>
</div>
<div id="confirm-modal-overlay" class="modal-overlay"></div>
<div id="metadata-modal-overlay" class="modal-overlay"></div>
{% endblock %}
{% block scripts %}
<script src="/static/dist/library.min.js"></script>
{% endblock %}
```

- [ ] **Step 4: Create library.css**

Dark themed styles matching the analysis page — cards, upload area, sidebar, responsive grid layout.

- [ ] **Step 5: Build and verify**

Run: `npm run build`
Expected: Both `library.min.js` and `library.min.css` created.

- [ ] **Step 6: Commit**

```bash
git add src/js/library/ src/css/library.css server/templates/library.html
git commit -m "feat: library page frontend (routes, categories, tags, upload)"
```

---

## Phase 6: Docker and Documentation

### Task 14: Dockerfile and docker-compose

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
FROM python:3.12-slim AS base

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Node for build step
FROM node:22-slim AS builder
WORKDIR /app
COPY package.json build.js ./
RUN npm install
COPY src/ src/
RUN npm run build

# Final image
FROM base
COPY server/ server/
COPY --from=builder /app/server/static/dist/ server/static/dist/

ENV FLASK_PORT=5000
ENV DATA_DIR=/app/data
VOLUME /app/data
EXPOSE ${FLASK_PORT}

CMD gunicorn -b 0.0.0.0:${FLASK_PORT} "server:create_app()"
```

- [ ] **Step 2: Create docker-compose.yml**

```yaml
services:
  gpx-analysis:
    build: .
    ports:
      - "${FLASK_PORT:-5000}:${FLASK_PORT:-5000}"
    environment:
      - VALHALLA_URL=${VALHALLA_URL:-http://10.0.1.25:8002}
      - NOMINATIM_URL=${NOMINATIM_URL:-http://10.0.1.25:8001}
      - FLASK_PORT=${FLASK_PORT:-5000}
      - AUTH_USER_HEADER=${AUTH_USER_HEADER:-Remote-User}
      - BACKUP_ENABLED=${BACKUP_ENABLED:-true}
    volumes:
      - ${DATA_DIR:-./data}:/app/data
    restart: unless-stopped
```

- [ ] **Step 3: Build and test Docker image**

Run:
```bash
docker compose build
docker compose up -d
curl -s http://localhost:5000/ | head -5
docker compose down
```
Expected: Library page HTML returned.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "feat: Dockerfile and docker-compose for containerised deployment"
```

### Task 15: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write README**

Cover: overview, features, quick start (Docker), environment variables table, development setup (npm, Python venv, running tests), project structure overview, architecture diagram.

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README with setup, configuration, and development guide"
```

---

## Phase 7: UI Tests (Playwright)

### Task 16: Playwright UI tests

**Files:**
- Create: `tests/test_ui_library.py`
- Create: `tests/test_ui_analysis.py`

- [ ] **Step 1: Add server fixture to conftest.py**

Add to `tests/conftest.py`:
```python
import subprocess
import time
import socket


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def server(tmp_path_factory):
    port = _find_free_port()
    data_dir = str(tmp_path_factory.mktemp("data"))
    env = {
        **os.environ,
        "DATA_DIR": data_dir,
        "FLASK_PORT": str(port),
        "BACKUP_ENABLED": "false",
    }
    proc = subprocess.Popen(
        ["python", "-m", "gunicorn", "-b", f"0.0.0.0:{port}", "server:create_app()"],
        env=env,
    )
    base_url = f"http://localhost:{port}"
    # Wait for server to be ready
    for _ in range(30):
        try:
            import requests
            requests.get(base_url, timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    yield base_url
    proc.terminate()
    proc.wait()
```

- [ ] **Step 2: Write library UI tests**

Create `tests/test_ui_library.py`:
```python
import os
from playwright.sync_api import expect

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def test_library_loads(page, server):
    page.goto(server)
    expect(page.locator("#library-container")).to_be_visible()
    expect(page.locator("text=Default")).to_be_visible()


def test_upload_via_ui(page, server):
    page.goto(server)
    page.locator("#upload-area input[type=file]").set_input_files(
        os.path.join(FIXTURES, "sample.gpx")
    )
    # Title should be pre-filled from GPX name
    expect(page.locator("input[name=title]")).to_have_value("Test Route")
    page.locator("button:has-text('Upload')").click()
    expect(page.locator(".route-card")).to_be_visible()


def test_click_route_opens_analysis(page, server):
    page.goto(server)
    # Upload first
    page.locator("#upload-area input[type=file]").set_input_files(
        os.path.join(FIXTURES, "sample.gpx")
    )
    page.locator("button:has-text('Upload')").click()
    page.locator(".route-card").first.click()
    expect(page).to_have_url(f"{server}/route/1")


def test_delete_route_inline_confirm(page, server):
    page.goto(server)
    page.locator("#upload-area input[type=file]").set_input_files(
        os.path.join(FIXTURES, "sample.gpx")
    )
    page.locator("button:has-text('Upload')").click()
    page.locator(".route-card .delete-btn").first.click()
    # Inline modal should appear, not a browser dialog
    expect(page.locator("#confirm-modal-overlay")).to_be_visible()
    page.locator("#confirm-modal-overlay .confirm-yes").click()
    expect(page.locator(".route-card")).to_have_count(0)


def test_delete_route_cancel(page, server):
    page.goto(server)
    page.locator("#upload-area input[type=file]").set_input_files(
        os.path.join(FIXTURES, "sample.gpx")
    )
    page.locator("button:has-text('Upload')").click()
    page.locator(".route-card .delete-btn").first.click()
    page.locator("#confirm-modal-overlay .confirm-no").click()
    expect(page.locator(".route-card")).to_have_count(1)
```

- [ ] **Step 3: Write analysis UI tests**

Create `tests/test_ui_analysis.py`:
```python
import io
import requests as http_requests


def _upload_route(server):
    import os
    with open(os.path.join(os.path.dirname(__file__), "fixtures", "sample.gpx"), "rb") as f:
        resp = http_requests.post(f"{server}/api/routes", files={"file": f}, data={"title": "Test"})
    return resp.json()["id"]


def test_analysis_page_loads_map(page, server):
    route_id = _upload_route(server)
    page.goto(f"{server}/route/{route_id}")
    expect(page.locator("#map")).to_be_visible()
    # Leaflet tiles should be loading
    expect(page.locator(".leaflet-tile-container")).to_be_visible()


def test_analysis_page_shows_stats(page, server):
    route_id = _upload_route(server)
    page.goto(f"{server}/route/{route_id}")
    expect(page.locator("#stats")).to_be_visible()
    expect(page.locator(".stat")).to_have_count(7)  # 7 stat boxes


def test_elevation_profile_renders(page, server):
    route_id = _upload_route(server)
    page.goto(f"{server}/route/{route_id}")
    expect(page.locator("#profile-canvas")).to_be_visible()


def test_gradient_legend_visible(page, server):
    route_id = _upload_route(server)
    page.goto(f"{server}/route/{route_id}")
    expect(page.locator("#legend")).to_be_visible()
    expect(page.locator(".legend-item")).to_have_count(6)  # 6 absolute ranges


def test_settings_sliders_present(page, server):
    route_id = _upload_route(server)
    page.goto(f"{server}/route/{route_id}")
    expect(page.locator("#set-smooth")).to_be_visible()
    expect(page.locator("#set-graddist")).to_be_visible()


def test_navigate_back_to_library(page, server):
    route_id = _upload_route(server)
    page.goto(f"{server}/route/{route_id}")
    page.locator("a[href='/']").click()
    expect(page).to_have_url(f"{server}/")


from playwright.sync_api import expect
```

- [ ] **Step 4: Run UI tests**

Run:
```bash
pip install -r requirements-dev.txt
playwright install chromium
pytest tests/test_ui_library.py tests/test_ui_analysis.py -v
```
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_ui_library.py tests/test_ui_analysis.py tests/conftest.py
git commit -m "test: Playwright UI tests for library and analysis pages"
```

---

## Phase 8: Cleanup

### Task 17: Remove old static files and final integration test

- [ ] **Step 1: Remove old js/ and index.html from root**

The original `js/` directory and `index.html` at project root are superseded by `src/js/` and `server/templates/`. Remove them.

- [ ] **Step 2: Run full test suite**

Run:
```bash
pytest tests/ -v --tb=short
```
Expected: All API, model, parser, backup, auth, and UI tests PASS.

- [ ] **Step 3: Build Docker image and smoke test**

Run:
```bash
docker compose build && docker compose up -d
curl -s http://localhost:5000/ | grep "Route Library"
curl -s http://localhost:5000/api/categories | python3 -m json.tool
docker compose down
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove legacy static files, final integration verification"
```
