"""端点目录与访问控制。

守卫：**不允许再有任何业务端点返回 501**。
价值在于防止回退——改动若弄坏了某个端点的注册，或把实现换回
`not_implemented()` 占位，这里会立刻红。
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from flask_jwt_extended import create_access_token

from app.core.errors import ErrorCode

# 全部业务端点。每一项都在别处有专门的行为测试，
# 这里只做"存在且未回退成 501"的守卫。
ALL_ENDPOINTS = [
    ("post", "/api/v1/auth/register", None),
    ("post", "/api/v1/auth/login", None),
    ("get", "/api/v1/users/me", "user"),
    ("get", "/api/v1/users/me/export", "user"),
    ("get", "/api/v1/conversations", "user"),
    ("post", "/api/v1/conversations", "user"),
    ("get", "/api/v1/admin/documents", "admin"),
    ("get", "/api/v1/admin/config", "admin"),
    ("get", "/api/v1/admin/crisis-events", "admin"),
    ("get", "/api/v1/admin/stats/overview", "admin"),
    ("get", "/api/v1/admin/tasks/does-not-exist", "admin"),
]


@pytest.mark.parametrize(("method", "path", "role"), ALL_ENDPOINTS)
def test_endpoint_never_returns_501(client, auth_headers, method, path, role):
    headers = {}
    if role:
        headers, _ = auth_headers(role=role)
    resp = getattr(client, method)(path, headers=headers, json={})
    assert resp.status_code != 501, f"{path} 又变回未实现了"


def test_no_code_references_not_implemented_anymore():
    """静态检查：整个后端都不该再出现 not_implemented / 9002。

    骨架期靠 not_implemented() 占位，现在全部实现完毕，这套机制连同
    ErrorCode.NOT_IMPLEMENTED(9002) 一起删掉了。这条断言防止它被重新引入——
    也要防止前端再收到"该接口尚未实现"这类会误导用户的消息。
    """
    import pathlib
    import re

    app_dir = pathlib.Path(__file__).resolve().parents[2] / "app"
    offenders = []
    for path in app_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"not_implemented|NOT_IMPLEMENTED|9002", text):
            line = text[: match.start()].count("\n") + 1
            offenders.append(f"{path.relative_to(app_dir)}:{line}")
    assert not offenders, f"仍存在未实现的占位机制：{offenders}"


# ---------------------------------------------------------------------------
# 访问控制
# ---------------------------------------------------------------------------


def test_admin_endpoint_rejects_normal_user(client, auth_headers):
    headers, _ = auth_headers(role="user")
    resp = client.get("/api/v1/admin/documents", headers=headers)
    assert resp.status_code == 403
    assert resp.get_json()["code"] == ErrorCode.FORBIDDEN


def test_admin_endpoint_rejects_anonymous(client):
    resp = client.get("/api/v1/admin/documents")
    assert resp.status_code == 401
    assert resp.get_json()["code"] == ErrorCode.UNAUTHORIZED


def test_expired_token_returns_401_not_500(app, client):
    """过期令牌必须走 401，而不是掉进通用异常处理器变成 500。"""
    with app.app_context():
        token = create_access_token(identity="1", expires_delta=timedelta(seconds=-1))
    resp = client.get("/api/v1/conversations", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert resp.get_json()["code"] == ErrorCode.UNAUTHORIZED


def test_token_of_deleted_user_is_rejected(client, auth_headers):
    """令牌有效但用户已不存在时也必须拒绝。

    这是"数据库二次校验"的意义：JWT 无状态，用户被删掉后
    旧令牌在自然过期前仍然能被解析出来。
    """
    headers, user = auth_headers(role="user")

    from app.extensions import db
    from app.models import User

    db.session.delete(User.query.get(user.id))
    db.session.commit()

    resp = client.get("/api/v1/users/me", headers=headers)
    assert resp.status_code == 401
    assert resp.get_json()["code"] == ErrorCode.UNAUTHORIZED


# ---------------------------------------------------------------------------
# 上传校验
# ---------------------------------------------------------------------------


def test_upload_rejects_unsupported_extension(client, auth_headers):
    import io

    headers, _ = auth_headers(role="admin")
    data = {"file": (io.BytesIO(b"hello"), "notes.exe")}
    resp = client.post(
        "/api/v1/admin/documents",
        headers=headers,
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == ErrorCode.UPLOAD_REJECTED


def test_upload_missing_file_field(client, auth_headers):
    headers, _ = auth_headers(role="admin")
    resp = client.post(
        "/api/v1/admin/documents", headers=headers, data={}, content_type="multipart/form-data"
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == ErrorCode.INVALID_PARAM


# ---------------------------------------------------------------------------
# 管理配置
# ---------------------------------------------------------------------------


def test_admin_config_is_readable(client, auth_headers):
    headers, _ = auth_headers(role="admin")
    resp = client.get("/api/v1/admin/config", headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert "top_k_retrieve" in data["values"]
    assert "restart_required_keys" in data


def test_admin_config_rejects_unknown_keys(client, auth_headers):
    """不可在线修改的键必须被明确拒绝，而不是静默忽略。"""
    headers, _ = auth_headers(role="admin")
    resp = client.put(
        "/api/v1/admin/config", headers=headers, json={"JWT_SECRET": "hacked"}
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == ErrorCode.INVALID_PARAM
    assert "JWT_SECRET" in resp.get_json()["message"]


def test_admin_config_accepts_editable_key(client, auth_headers):
    """Redis 不可用时应当明确报错，而不是假装保存成功。"""
    headers, _ = auth_headers(role="admin")
    resp = client.put("/api/v1/admin/config", headers=headers, json={"top_k_retrieve": 12})
    # 测试环境没有 Redis（指向保留端口），因此期望 503；
    # 若将来测试环境接入 Redis，这里会变成 200，两种都算符合契约。
    assert resp.status_code in (200, 503)

