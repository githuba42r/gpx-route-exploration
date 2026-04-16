import sqlite3
import pytest

from server.models.categories import (
    ensure_default_category,
    create_category,
    get_categories,
    get_category,
)
from server.models.routes import (
    create_route,
    get_routes,
    get_route,
    move_route,
)
from server.models.tags import (
    set_route_tags,
    get_route_tags,
    get_tags_with_counts,
)


def test_ensure_default_category(app):
    with app.app_context():
        cat = ensure_default_category("user_a")
        assert cat["name"] == "Default"
        assert cat["slug"] == "default"
        assert cat["user_id"] == "user_a"

        # Idempotent — second call returns the same row
        cat2 = ensure_default_category("user_a")
        assert cat2["id"] == cat["id"]


def test_create_category(app):
    with app.app_context():
        cat = create_category("user_a", "Mountain Rides", "Big climbs")
        assert cat["name"] == "Mountain Rides"
        assert cat["slug"] == "mountain-rides"
        assert cat["description"] == "Big climbs"


def test_create_duplicate_category_fails(app):
    with app.app_context():
        create_category("user_a", "Gravel")
        with pytest.raises(sqlite3.IntegrityError):
            create_category("user_a", "Gravel")


def test_categories_isolated_by_user(app):
    with app.app_context():
        create_category("user_a", "Alpine")
        cats_b = get_categories("user_b")
        names = [c["name"] for c in cats_b]
        assert "Alpine" not in names


def test_create_route(app):
    with app.app_context():
        cat = ensure_default_category("user_a")
        route = create_route(
            user_id="user_a",
            category_id=cat["id"],
            filename="ride.gpx",
            storage_name="user_a_ride.gpx",
            title="Morning Ride",
            distance_km=42.5,
            min_elevation=100.0,
            max_elevation=800.0,
            max_gradient_asc=12.3,
            max_gradient_desc=-14.1,
            point_count=500,
            description="A nice ride",
            notes="Bring water",
        )
        assert route["title"] == "Morning Ride"
        assert route["distance_km"] == 42.5
        assert route["min_elevation"] == 100.0
        assert route["max_elevation"] == 800.0
        assert route["max_gradient_asc"] == 12.3
        assert route["max_gradient_desc"] == -14.1
        assert route["point_count"] == 500
        assert route["description"] == "A nice ride"
        assert route["notes"] == "Bring water"
        assert route["user_id"] == "user_a"


def test_routes_isolated_by_user(app):
    with app.app_context():
        cat_a = ensure_default_category("user_a")
        create_route(
            user_id="user_a",
            category_id=cat_a["id"],
            filename="secret.gpx",
            storage_name="user_a_secret.gpx",
            title="Secret Route",
        )
        routes_b = get_routes("user_b")
        titles = [r["title"] for r in routes_b]
        assert "Secret Route" not in titles


def test_move_route(app):
    with app.app_context():
        cat_a = ensure_default_category("user_a")
        cat_b = create_category("user_a", "Weekend")
        route = create_route(
            user_id="user_a",
            category_id=cat_a["id"],
            filename="trail.gpx",
            storage_name="user_a_trail.gpx",
            title="Trail Run",
        )
        assert route["category_id"] == cat_a["id"]
        moved = move_route("user_a", route["id"], cat_b["id"])
        assert moved["category_id"] == cat_b["id"]


def test_set_route_tags(app):
    with app.app_context():
        cat = ensure_default_category("user_a")
        route = create_route(
            user_id="user_a",
            category_id=cat["id"],
            filename="loop.gpx",
            storage_name="user_a_loop.gpx",
            title="Loop Route",
        )
        set_route_tags("user_a", route["id"], ["scenic", "hilly", "gravel"])
        tags = get_route_tags("user_a", route["id"])
        tag_names = sorted(t["name"] for t in tags)
        assert tag_names == ["gravel", "hilly", "scenic"]


def test_tags_case_insensitive_dedup(app):
    with app.app_context():
        cat = ensure_default_category("user_a")
        route = create_route(
            user_id="user_a",
            category_id=cat["id"],
            filename="climb.gpx",
            storage_name="user_a_climb.gpx",
            title="Climb Route",
        )
        set_route_tags("user_a", route["id"], ["Hilly", "hilly", "HILLY"])
        tags = get_route_tags("user_a", route["id"])
        assert len(tags) == 1
        assert tags[0]["name_lower"] == "hilly"


def test_tags_isolated_by_user(app):
    with app.app_context():
        cat_a = ensure_default_category("user_a")
        route_a = create_route(
            user_id="user_a",
            category_id=cat_a["id"],
            filename="private.gpx",
            storage_name="user_a_private.gpx",
            title="Private Route",
        )
        set_route_tags("user_a", route_a["id"], ["exclusive"])

        tags_b = get_tags_with_counts("user_b")
        tag_names_b = [t["name"] for t in tags_b]
        assert "exclusive" not in tag_names_b
