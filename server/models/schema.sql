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

CREATE TABLE IF NOT EXISTS route_waypoints (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id        INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
    position        INTEGER NOT NULL,
    kind            TEXT    NOT NULL CHECK(kind IN ('stop', 'waypoint')),
    name            TEXT    NOT NULL,
    address         TEXT,
    lat             REAL,
    lon             REAL,
    included        INTEGER NOT NULL DEFAULT 1 CHECK(included IN (0, 1)),
    pin_role        TEXT    CHECK(pin_role IN ('start', 'end') OR pin_role IS NULL),
    dwell_minutes   INTEGER NOT NULL DEFAULT 0,
    description     TEXT,
    arrival_time    TEXT,           -- ISO 8601 string; optional per-stop arrival target
    UNIQUE(route_id, position)
);
CREATE INDEX IF NOT EXISTS idx_waypoints_route ON route_waypoints(route_id);

CREATE TABLE IF NOT EXISTS route_options (
    route_id          INTEGER PRIMARY KEY REFERENCES routes(id) ON DELETE CASCADE,
    profile           TEXT    NOT NULL DEFAULT 'bicycle' CHECK(profile IN ('bicycle','pedestrian','auto')),
    costing_preset    TEXT    NOT NULL DEFAULT 'hybrid' CHECK(costing_preset IN ('road','gravel-mtb','easy','hike','drive','custom','hybrid')),
    costing_options   TEXT,
    round_trip        INTEGER NOT NULL DEFAULT 0 CHECK(round_trip IN (0, 1)),
    max_gradient_warn REAL,
    last_optimised_at INTEGER,
    last_generated_at INTEGER
);

CREATE TABLE IF NOT EXISTS route_legs (
    route_id        INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
    from_position   INTEGER NOT NULL,
    to_position     INTEGER NOT NULL,
    distance_m      REAL    NOT NULL,
    duration_s      REAL    NOT NULL,
    polyline        TEXT    NOT NULL,
    max_grade_pct   REAL,
    warnings        TEXT,
    PRIMARY KEY (route_id, from_position, to_position)
);

CREATE TABLE IF NOT EXISTS geocode_cache (
    query        TEXT PRIMARY KEY,
    lat          REAL,
    lon          REAL,
    display_name TEXT,
    created_at   INTEGER NOT NULL
);

-- M8: bookmarks (per-user reusable locations)
CREATE TABLE IF NOT EXISTS bookmarks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid        TEXT    NOT NULL UNIQUE,
    user_id     TEXT    NOT NULL DEFAULT 'anonymous',
    name        TEXT    NOT NULL,
    description TEXT    DEFAULT '',
    lat         REAL    NOT NULL,
    lon         REAL    NOT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_bookmarks_user ON bookmarks(user_id);

CREATE TABLE IF NOT EXISTS bookmark_tags (
    bookmark_id INTEGER NOT NULL REFERENCES bookmarks(id) ON DELETE CASCADE,
    tag_id      INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (bookmark_id, tag_id)
);

CREATE TABLE IF NOT EXISTS bookmark_photos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    bookmark_id   INTEGER NOT NULL REFERENCES bookmarks(id) ON DELETE CASCADE,
    position      INTEGER NOT NULL,
    storage_name  TEXT    NOT NULL,
    mime_type     TEXT    NOT NULL,
    byte_size     INTEGER NOT NULL,
    caption       TEXT    DEFAULT '',
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bookmark_id, position)
);
CREATE INDEX IF NOT EXISTS idx_bookmark_photos_bookmark ON bookmark_photos(bookmark_id);
