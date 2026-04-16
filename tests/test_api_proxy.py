import json
from unittest.mock import patch, MagicMock
import requests as real_requests


def _mock_response(status=200, content=b"ok", headers=None):
    resp = MagicMock()
    resp.status_code = status
    resp.content = content
    resp.headers = headers or {"Content-Type": "application/json"}
    return resp


def test_valhalla_proxy(client):
    mock_resp = _mock_response(200, b'{"height": [100]}', {"Content-Type": "application/json"})
    with patch("server.blueprints.proxy.requests.request", return_value=mock_resp) as mock_req:
        resp = client.post(
            "/proxy/valhalla/height",
            data=json.dumps({"shape": []}),
            content_type="application/json",
        )
    assert resp.status_code == 200
    call_args = mock_req.call_args
    assert "/height" in call_args.kwargs["url"]


def test_nominatim_proxy(client):
    mock_resp = _mock_response(200, b'{"status": 0}', {"Content-Type": "application/json"})
    with patch("server.blueprints.proxy.requests.request", return_value=mock_resp) as mock_req:
        resp = client.get("/proxy/nominatim/status")
    assert resp.status_code == 200
    call_args = mock_req.call_args
    assert "/status" in call_args.kwargs["url"]


def test_proxy_upstream_failure(client):
    with patch("server.blueprints.proxy.requests.request", side_effect=real_requests.Timeout("timed out")):
        resp = client.get("/proxy/valhalla/status")
    assert resp.status_code == 502
    data = resp.get_json()
    assert "error" in data
