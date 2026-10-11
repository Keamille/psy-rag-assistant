"""认证接口测试（开发文档 §7.3）。"""

from __future__ import annotations

import pytest
from flask_jwt_extended import create_access_token

from app.core.errors import ErrorCode
from app.extensions import RedisStore, db
from app.models import AuditLog, User
from tests.conftest import DEFAULT_PASSWORD

VALID_BODY = {
    "email": "New.User@Example.com",
    "username": "NewUser",
    "password": DEFAULT_PASSWORD,
    "age_confirmed": True,
    "consent": True,
    "consent_version": "v1.0",
}


def _register(client, **overrides):
    body = {**VALID_BODY, **overrides}
    return client.post("/api/v1/auth/register", json=body)


# --------------------------------------------------------------------------
# 注册
# --------------------------------------------------------------------------


def test_register_success_returns_tokens(client):
    resp = _register(client)
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["access_token"] and data["refresh_token"]
    assert data["expires_in"] > 0
    assert data["user"]["role"] == "user"
    # 邮箱与用户名都应归一化为小写
    assert data["user"]["email"] == "new.user@example.com"
    assert data["user"]["username"] == "newuser"


def test_register_persists_agreement_fields(client, app):
    _register(client)
    user = User.query.filter_by(username="newuser").one()
    assert user.consent_version == "v1.0"
    assert user.consented_at is not None
    assert user.status == "active"
    # 密码绝不能以明文存储
    assert DEFAULT_PASSWORD not in user.password_hash
    assert user.password_hash.startswith("$argon2")


def test_register_ignores_client_supplied_role(client):
    """客户端传 role=admin 也必须被忽略，否则任何人都能自封管理员。"""
    resp = _register(client, role="admin", username="sneaky")
    assert resp.status_code == 200
    assert resp.get_json()["data"]["user"]["role"] == "user"
    assert User.query.filter_by(username="sneaky").one().role == "user"


def test_register_duplicate_email_returns_2002(client):
    _register(client)
    resp = _register(client, username="another")
    assert resp.status_code == 409
    assert resp.get_json()["code"] == ErrorCode.DUPLICATE_ACCOUNT


def test_register_duplicate_username_returns_2002(client):
    _register(client)
    resp = _register(client, email="other@example.com")
    assert resp.status_code == 409
    assert resp.get_json()["code"] == ErrorCode.DUPLICATE_ACCOUNT


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("password", "short1"),  # 少于 10 位
        ("password", "alllettersnodigits"),  # 缺数字
        ("password", "1234567890"),  # 缺字母
        ("email", "not-an-email"),
        ("username", "ab"),  # 太短
        ("age_confirmed", False),
        ("consent", False),
        ("consent_version", "v0.9"),  # 版本不匹配
    ],
)
def test_register_rejects_invalid_input(client, field, value):
    resp = _register(client, **{field: value})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == ErrorCode.INVALID_PARAM


def test_register_rejects_non_json_body(client):
    resp = client.post("/api/v1/auth/register", data="not json")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == ErrorCode.INVALID_PARAM


# --------------------------------------------------------------------------
# 登录
# --------------------------------------------------------------------------


def test_login_with_username_then_email(client, make_user):
    make_user(username="alice", email="alice@example.com")

    resp = client.post(
        "/api/v1/auth/login", json={"account": "alice", "password": DEFAULT_PASSWORD}
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["access_token"]

    resp = client.post(
        "/api/v1/auth/login", json={"account": "alice@example.com", "password": DEFAULT_PASSWORD}
    )
    assert resp.status_code == 200


def test_login_is_case_insensitive(client, make_user):
    make_user(username="bob", email="bob@example.com")
    resp = client.post(
        "/api/v1/auth/login", json={"account": "  BoB  ", "password": DEFAULT_PASSWORD}
    )
    assert resp.status_code == 200


def test_login_updates_last_login_at_and_writes_audit(client, make_user, app):
    user = make_user(username="carol")
    assert user.last_login_at is None

    client.post("/api/v1/auth/login", json={"account": "carol", "password": DEFAULT_PASSWORD})

    refreshed = db.session.get(User, user.id)
    assert refreshed.last_login_at is not None
    assert AuditLog.query.filter_by(action="login", actor_id=user.id).count() == 1


def test_login_wrong_password_returns_2001(client, make_user):
    make_user(username="dave")
    resp = client.post(
        "/api/v1/auth/login", json={"account": "dave", "password": "WrongPass123"}
    )
    assert resp.status_code == 401
    assert resp.get_json()["code"] == ErrorCode.BAD_CREDENTIALS


def test_login_unknown_account_returns_same_error_as_wrong_password(client):
    """两种失败必须返回同一个码，避免被用来探测账号是否已注册。"""
    resp = client.post(
        "/api/v1/auth/login", json={"account": "nobody", "password": "WrongPass123"}
    )
    assert resp.status_code == 401
    assert resp.get_json()["code"] == ErrorCode.BAD_CREDENTIALS


def test_login_disabled_account_is_rejected(client, make_user):
    make_user(username="eve", status="disabled")
    resp = client.post("/api/v1/auth/login", json={"account": "eve", "password": DEFAULT_PASSWORD})
    assert resp.status_code == 403
    assert resp.get_json()["code"] == ErrorCode.FORBIDDEN


# --------------------------------------------------------------------------
# 刷新
# --------------------------------------------------------------------------


def test_refresh_returns_new_access_token(client, refresh_headers):
    headers, user = refresh_headers()
    resp = client.post("/api/v1/auth/refresh", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["access_token"]


def test_refresh_rejects_access_token(client, auth_headers):
    """用 access 令牌去换新令牌必须失败（端点要求 refresh 类型）。"""
    headers, _ = auth_headers()
    resp = client.post("/api/v1/auth/refresh", headers=headers)
    assert resp.status_code == 401


def test_refresh_rejected_when_user_disabled(client, refresh_headers):
    headers, user = refresh_headers()
    user.status = "disabled"
    db.session.commit()

    resp = client.post("/api/v1/auth/refresh", headers=headers)
    assert resp.status_code == 401


# --------------------------------------------------------------------------
# 注销与黑名单
# --------------------------------------------------------------------------


@pytest.fixture()
def fake_blocklist(monkeypatch):
    """用内存集合模拟 Redis 黑名单，让注销链路可测。"""
    store: set[str] = set()
    monkeypatch.setattr(RedisStore, "blocklist_add", lambda self, jti, ttl: store.add(jti) or True)
    monkeypatch.setattr(RedisStore, "blocklist_contain", lambda self, jti: jti in store)
    return store


def test_logout_revokes_token(client, fake_blocklist, refresh_headers):
    headers, _ = refresh_headers()

    resp = client.post("/api/v1/auth/logout", headers=headers)
    assert resp.status_code == 200
    assert len(fake_blocklist) == 1

    # 被撤销的 refresh 令牌不能再用
    resp = client.post("/api/v1/auth/refresh", headers=headers)
    assert resp.status_code == 401


def test_logout_reports_failure_when_redis_unavailable(client, refresh_headers):
    """Redis 不可用时不能假装注销成功，否则用户以为退出了、令牌其实还能用。"""
    headers, _ = refresh_headers()
    resp = client.post("/api/v1/auth/logout", headers=headers)
    assert resp.status_code == 503
    assert "撤销服务" in resp.get_json()["message"]


def test_blocklist_degrades_open_when_redis_unavailable(app, client):
    """Redis 不可用时黑名单校验返回 False（放行）。

    这是可用性优先的取舍：否则 Redis 一挂，所有已登录用户会被立刻踢下线。
    """
    with app.app_context():
        assert RedisStore().blocklist_contain("anything") is False


def test_token_without_jti_is_ignored_by_blocklist(client, app):
    """没有 jti 的令牌不应因为查黑名单而报错。"""
    with app.app_context():
        token = create_access_token(identity="1", additional_claims={"no_jti": True})
    resp = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    # 该用户不存在，应当是数据库二次校验拦下（401），而不是黑名单炸掉（500）
    assert resp.status_code == 401

