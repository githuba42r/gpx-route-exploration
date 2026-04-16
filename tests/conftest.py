import os
import subprocess
import time
import socket
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


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def server_url(tmp_path_factory):
    """Start a live Flask server for Playwright tests."""
    port = _find_free_port()
    data_dir = str(tmp_path_factory.mktemp("playwright_data"))
    env = {
        **os.environ,
        "DATA_DIR": data_dir,
        "FLASK_PORT": str(port),
        "BACKUP_ENABLED": "false",
    }
    proc = subprocess.Popen(
        [".venv/bin/python", "-c",
         f"from server import create_app; create_app({{'DATA_DIR': '{data_dir}', 'BACKUP_ENABLED': False}}).run(port={port})"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://localhost:{port}"
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
