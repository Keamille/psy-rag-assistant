"""路由注册完整性：对照开发文档 7.3–7.8 的接口清单。"""

from __future__ import annotations

import pytest

# (路径, 方法)：文档 7.3–7.8 全部端点
EXPECTED_ENDPOINTS = [
    # 7.3 认证
    ("/api/v1/auth/register", "POST"),
    ("/api/v1/auth/login", "POST"),
    ("/api/v1/auth/refresh", "POST"),
    ("/api/v1/auth/logout", "POST"),
    # 7.4 用户
    ("/api/v1/users/me", "GET"),
    ("/api/v1/users/me", "PATCH"),
    ("/api/v1/users/me/export", "GET"),
    ("/api/v1/users/me/data", "DELETE"),
    # 7.5 会话
    ("/api/v1/conversations", "GET"),
    ("/api/v1/conversations", "POST"),
    ("/api/v1/conversations/<int:conversation_id>", "GET"),
    ("/api/v1/conversations/<int:conversation_id>", "PATCH"),
    ("/api/v1/conversations/<int:conversation_id>", "DELETE"),
    ("/api/v1/conversations/<int:conversation_id>/messages", "GET"),
    # 7.6 消息（SSE）
    ("/api/v1/conversations/<int:conversation_id>/messages", "POST"),
    ("/api/v1/conversations/<int:conversation_id>/resume", "POST"),
    # 7.7 管理后台
    ("/api/v1/admin/documents", "POST"),
    ("/api/v1/admin/documents", "GET"),
    ("/api/v1/admin/documents/<int:document_id>", "GET"),
    ("/api/v1/admin/documents/<int:document_id>/chunks", "GET"),
    ("/api/v1/admin/documents/<int:document_id>/reindex", "POST"),
    ("/api/v1/admin/documents/<int:document_id>", "DELETE"),
    ("/api/v1/admin/tasks/<task_id>", "GET"),
    ("/api/v1/admin/config", "GET"),
    ("/api/v1/admin/config", "PUT"),
    ("/api/v1/admin/crisis-events", "GET"),
    ("/api/v1/admin/crisis-events/<int:event_id>", "GET"),
    ("/api/v1/admin/crisis-events/<int:event_id>/review", "POST"),
    ("/api/v1/admin/stats/overview", "GET"),
    # 7.8 系统
    ("/api/v1/health", "GET"),
    ("/api/v1/ready", "GET"),
    ("/api/v1/meta/hotlines", "GET"),
    ("/api/v1/meta/config", "GET"),
]


@pytest.mark.parametrize(("path", "method"), EXPECTED_ENDPOINTS)
def test_endpoint_registered(url_map, path, method):
    assert path in url_map, f"路由未注册：{path}"
    assert method in url_map[path], f"{path} 缺少方法 {method}，实际 {url_map[path]}"


def test_endpoint_set_matches_document_exactly(url_map):
    """实际注册的 (路径, 方法) 集合必须与文档清单完全一致，不多不少。

    除文档清单外，只额外允许 /meta/build（服务信息与能力开关）。
    """
    actual = {
        (path, method)
        for path, methods in url_map.items()
        if path.startswith("/api/v1")
        for method in methods
    }
    expected = set(EXPECTED_ENDPOINTS) | {("/api/v1/meta/build", "GET")}

    missing = expected - actual
    extra = actual - expected
    assert not missing, f"文档要求但未注册的接口：{sorted(missing)}"
    assert not extra, f"未在文档中声明却已注册的接口：{sorted(extra)}"


