def register_blueprints(app):
    from server.blueprints.api_routes import bp as routes_bp
    from server.blueprints.api_gpx import bp as gpx_bp
    from server.blueprints.api_categories import bp as categories_bp
    from server.blueprints.api_tags import bp as tags_bp
    from server.blueprints.api_waypoints import bp as waypoints_bp
    from server.blueprints.api_routing import bp as routing_bp
    from server.blueprints.api_presets import bp as presets_bp
    from server.blueprints.api_geocode import bp as geocode_bp
    from server.blueprints.api_bookmarks import bp as bookmarks_bp
    from server.blueprints.proxy import bp as proxy_bp
    app.register_blueprint(routes_bp)
    app.register_blueprint(gpx_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(tags_bp)
    app.register_blueprint(waypoints_bp)
    app.register_blueprint(routing_bp)
    app.register_blueprint(presets_bp)
    app.register_blueprint(geocode_bp)
    app.register_blueprint(bookmarks_bp)
    app.register_blueprint(proxy_bp)

    from server.blueprints.pages import bp as pages_bp
    app.register_blueprint(pages_bp)
