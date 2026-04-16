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
