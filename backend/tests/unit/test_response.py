"""统一响应包装体的契约测试（开发文档 6.3）。"""

from __future__ import annotations


def test_success_envelope(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body) == {"code", "message", "data", "request_id"}
    assert body["code"] == 0
    assert body["message"] == "ok"
    assert body["data"]["status"] == "ok"
    assert body["request_id"]


def test_request_id_is_echoed(client):
    resp = client.get("/api/v1/health", headers={"X-Request-Id": "trace-me-123"})
    assert resp.headers["X-Request-Id"] == "trace-me-123"
    assert resp.get_json()["request_id"] == "trace-me-123"


def test_error_envelope_uses_same_shape(client):
    resp = client.get("/api/v1/conversations")
    assert resp.status_code == 401
    body = resp.get_json()
    assert set(body) == {"code", "message", "data", "request_id"}
    assert body["code"] == 1002
    assert body["data"] is None


def test_unknown_path_returns_404_with_business_code(client):
    resp = client.get("/api/v1/definitely-not-exist")
    assert resp.status_code == 404
    assert resp.get_json()["code"] == 1004


def test_method_not_allowed_maps_to_business_code(client):
    resp = client.delete("/api/v1/health")
    assert resp.status_code == 405
    assert resp.get_json()["code"] == 1004

