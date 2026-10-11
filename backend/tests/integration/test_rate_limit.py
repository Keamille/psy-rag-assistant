"""限流响应契约（开发文档 §6.5 / §11.8）。

本机没有 Redis，限流默认走"降级放行"分支，因此这里用 monkeypatch
模拟一个正在限流的 Redis，专门验证 429 的响应形状。
"""

from __future__ import annotations

import pytest

from app.core.errors import ApiError, ErrorCode
from app.extensions import RedisStore


@pytest.fixture()
def redis_over_limit(monkeypatch):
    """让每一次限流检查都判定为超额，并告知还要等 37 秒。"""
    monkeypatch.setattr(RedisStore, "incr_with_ttl", lambda self, key, ttl: 999)
    monkeypatch.setattr(RedisStore, "ttl_seconds", lambda self, key: 37)
    return 37


@pytest.fixture()
def redis_unavailable(monkeypatch):
    """模拟 Redis 挂掉：incr 返回 None，应降级放行而不是拦人。"""
    monkeypatch.setattr(RedisStore, "incr_with_ttl", lambda self, key, ttl: None)


def test_limited_response_carries_retry_after(client, redis_over_limit):
    resp = client.post(
        "/api/v1/auth/login", json={"account": "nobody", "password": "Whatever123"}
    )
    assert resp.status_code == 429

    body = resp.get_json()
    assert body["code"] == ErrorCode.RATE_LIMITED
    assert body["data"] == {"retry_after": redis_over_limit}

    # 同时要有标准的 Retry-After 头，方便中间代理与通用客户端识别
    assert resp.headers["Retry-After"] == str(redis_over_limit)


def test_limited_response_shape_matches_envelope(client, redis_over_limit):
    resp = client.post(
        "/api/v1/auth/login", json={"account": "nobody", "password": "Whatever123"}
    )
    assert set(resp.get_json()) == {"code", "message", "data", "request_id"}


def test_register_rate_limit_also_carries_retry_after(client, redis_over_limit):
    resp = client.post("/api/v1/auth/register", json={})
    assert resp.status_code == 429
    assert resp.get_json()["data"]["retry_after"] == redis_over_limit


def test_degrades_open_when_redis_unavailable(client, redis_unavailable):
    """Redis 不可用时不能因为"数不了次数"就把用户全拦下来。"""
    resp = client.post(
        "/api/v1/auth/login", json={"account": "nobody", "password": "Whatever123"}
    )
    # 应当继续走到业务逻辑（账号不存在 → 2001），而不是返回 429
    assert resp.status_code == 401
    assert resp.get_json()["code"] == ErrorCode.BAD_CREDENTIALS


def test_ttl_fallback_uses_window_when_ttl_missing(monkeypatch, client):
    """边界情况：计数值超了但 TTL 读不到（key 恰好过期），
    此时回退成窗口长度，而不是丢一个空的 retry_after 给前端。"""
    monkeypatch.setattr(RedisStore, "incr_with_ttl", lambda self, key, ttl: 999)
    monkeypatch.setattr(RedisStore, "ttl_seconds", lambda self, key: None)

    resp = client.post(
        "/api/v1/auth/login", json={"account": "nobody", "password": "Whatever123"}
    )
    assert resp.status_code == 429
    # 登录限流窗口是 60 秒
    assert resp.get_json()["data"]["retry_after"] == 60


def test_api_error_data_is_optional(client):
    """普通业务异常（不带 data）不应凭空多出一个 data 字段。"""
    from app.core.response import fail

    with client.application.test_request_context():
        response, status = fail(ErrorCode.INVALID_PARAM, "参数不对", 400)
        assert status == 400
        assert response.get_json()["data"] is None


def test_api_error_can_carry_data():
    exc = ApiError(ErrorCode.RATE_LIMITED, "太频繁", 429, data={"retry_after": 12})
    assert exc.data == {"retry_after": 12}
    assert exc.http_status == 429


def test_ttl_seconds_returns_none_without_redis(app):
    """没有 Redis 时 ttl_seconds 必须安全返回 None，而不是抛异常。"""
    with app.app_context():
        assert RedisStore().ttl_seconds("any-key") is None

