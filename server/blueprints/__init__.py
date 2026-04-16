def register_blueprints(app):
    from server.blueprints.api_routes import bp as routes_bp
    from server.blueprints.api_gpx import bp as gpx_bp
    app.register_blueprint(routes_bp)
    app.register_blueprint(gpx_bp)
