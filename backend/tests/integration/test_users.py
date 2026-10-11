"""用户接口测试（开发文档 §7.4）。"""

from __future__ import annotations

from app.core.errors import ErrorCode
from app.core.security import verify_password
from app.extensions import db
from app.models import AuditLog, User
from tests.conftest import DEFAULT_PASSWORD


def test_get_me_returns_profile(client, auth_headers):
    headers, user = auth_headers()
    resp = client.get("/api/v1/users/me", headers=headers)
    assert resp.status_code == 200

    data = resp.get_json()["data"]
    assert data["id"] == user.id
    assert data["username"] == user.username
    assert data["role"] == "user"
    assert data["status"] == "active"
    assert data["consent_version"] == "v1.0"
    assert data["is_admin"] is False
    # 未配 Redis 时配额未知，必须是 None 而不是 0
    assert data["quota_remaining"] is None
    # 绝不能泄漏密码哈希
    assert "password_hash" not in data


def test_get_me_requires_auth(client):
    resp = client.get("/api/v1/users/me")
    assert resp.status_code == 401
    assert resp.get_json()["code"] == ErrorCode.UNAUTHORIZED


def test_patch_me_changes_password(client, auth_headers):
    headers, user = auth_headers()
    new_password = "BrandNewPass456"

    resp = client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"old_password": DEFAULT_PASSWORD, "password": new_password},
    )
    assert resp.status_code == 200

    refreshed = db.session.get(User, user.id)
    assert verify_password(refreshed.password_hash, new_password)
    assert not verify_password(refreshed.password_hash, DEFAULT_PASSWORD)

    # 旧密码登录失败，新密码登录成功
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"account": user.username, "password": DEFAULT_PASSWORD},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login", json={"account": user.username, "password": new_password}
        ).status_code
        == 200
    )


def test_patch_me_wrong_old_password_returns_2001(client, auth_headers):
    headers, _ = auth_headers()
    resp = client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"old_password": "WrongOldPass1", "password": "BrandNewPass456"},
    )
    assert resp.status_code == 401
    assert resp.get_json()["code"] == ErrorCode.BAD_CREDENTIALS


def test_patch_me_rejects_weak_new_password(client, auth_headers):
    headers, _ = auth_headers()
    resp = client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"old_password": DEFAULT_PASSWORD, "password": "short"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == ErrorCode.INVALID_PARAM


def test_patch_me_rejects_same_password(client, auth_headers):
    headers, _ = auth_headers()
    resp = client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"old_password": DEFAULT_PASSWORD, "password": DEFAULT_PASSWORD},
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == ErrorCode.INVALID_PARAM


def test_patch_me_writes_audit_log(client, auth_headers):
    headers, user = auth_headers()
    client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"old_password": DEFAULT_PASSWORD, "password": "BrandNewPass456"},
    )
    assert AuditLog.query.filter_by(action="change_password", actor_id=user.id).count() == 1


def test_patch_me_requires_auth(client):
    resp = client.patch(
        "/api/v1/users/me", json={"old_password": "x", "password": "BrandNewPass456"}
    )
    assert resp.status_code == 401

