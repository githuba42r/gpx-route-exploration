def register_blueprints(app):
    from server.blueprints.api_routes import bp as routes_bp
    from server.blueprints.api_gpx import bp as gpx_bp
    from server.blueprints.api_categories import bp as categories_bp
    from server.blueprints.api_tags import bp as tags_bp
    from server.blueprints.proxy import bp as proxy_bp
    app.register_blueprint(routes_bp)
    app.register_blueprint(gpx_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(tags_bp)
    app.register_blueprint(proxy_bp)
