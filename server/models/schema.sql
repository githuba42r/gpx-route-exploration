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
