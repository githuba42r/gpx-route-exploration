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
