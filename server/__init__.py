import os
import time
from flask import Flask
from server.config import Config


# Asset version — set at server start, appended to static CSS/JS URLs as
# ?v=<version> so the browser can never serve stale bundles after a rebuild.
ASSET_VERSION = str(int(time.time()))


def create_app(config_override=None):
    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates",
    )
    app.config.from_object(Config)
    if config_override:
        app.config.update(config_override)

    # Expose ASSET_VERSION to every Jinja template.
    @app.context_processor
    def _inject_asset_version():
        return {"asset_version": ASSET_VERSION}

    # Ensure data directories exist
    data_dir = app.config["DATA_DIR"]
    os.makedirs(os.path.join(data_dir, "gpx"), exist_ok=True)

    # Init database
    from server.models import init_app as init_db
    init_db(app)

    # Register blueprints
    from server.blueprints import register_blueprints
    register_blueprints(app)

    if not app.config.get("TESTING"):
        from server.backup import start_backup_scheduler
        start_backup_scheduler(app)

    return app
