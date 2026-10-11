"""统一响应包装体。

所有接口（含错误）统一返回：
    {"code": 0, "message": "ok", "data": {...}, "request_id": "..."}
"""

from __future__ import annotations

from typing import Any

from flask import g, jsonify


def _request_id() -> str | None:
    return getattr(g, "request_id", None)


def ok(data: Any = None, code: int = 0, message: str = "ok", http_status: int = 200):  # noqa: ANN401
    return (
        jsonify(code=code, message=message, data=data, request_id=_request_id()),
        http_status,
    )


def fail(code: int, message: str, http_status: int = 400, data: Any = None):  # noqa: ANN401
    return (
        jsonify(code=code, message=message, data=data, request_id=_request_id()),
        http_status,
    )


def paginated(items: list, page: int, size: int, total: int, **extra) -> dict:  # noqa: ANN003
    payload = {"items": items, "page": page, "size": size, "total": total}
    payload.update(extra)
    return payload

