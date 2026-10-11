"""请求追踪：为每个请求分配 request_id，透传到日志与响应。"""

from __future__ import annotations

import uuid

from flask import Flask, g, request

REQUEST_ID_HEADER = "X-Request-Id"


def register_request_id(app: Flask) -> None:
    @app.before_request
    def _assign_request_id() -> None:
        incoming = request.headers.get(REQUEST_ID_HEADER, "").strip()
        g.request_id = incoming or uuid.uuid4().hex

    @app.after_request
    def _echo_request_id(response):
        request_id = getattr(g, "request_id", None)
        if request_id:
            response.headers[REQUEST_ID_HEADER] = request_id
        return response


__all__ = ["register_request_id", "REQUEST_ID_HEADER"]

