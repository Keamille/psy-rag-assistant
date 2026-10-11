"""错误码表与全局异常处理。错误码与开发文档 §6.3 一致。"""

from __future__ import annotations

from typing import Any

from flask import Flask
from werkzeug.exceptions import HTTPException

from app.core.response import fail


class ErrorCode:
    OK = 0

    # 通用
    INVALID_PARAM = 1001
    UNAUTHORIZED = 1002
    FORBIDDEN = 1003
    NOT_FOUND = 1004
    RATE_LIMITED = 1005
    UPLOAD_REJECTED = 1006

    # 账号
    BAD_CREDENTIALS = 2001
    DUPLICATE_ACCOUNT = 2002

    # 会话
    CONVERSATION_NOT_FOUND = 3001
    CONVERSATION_PAUSED = 3002

    # 模型
    LLM_UNAVAILABLE = 4001
    LLM_TIMEOUT = 4002

    # 知识库
    DOC_PARSE_FAILED = 5001
    EMBEDDING_FAILED = 5002

    # 服务端
    INTERNAL_ERROR = 9001


DEFAULT_MESSAGES = {
    ErrorCode.OK: "ok",
    ErrorCode.INVALID_PARAM: "参数校验失败",
    ErrorCode.UNAUTHORIZED: "未认证或令牌失效",
    ErrorCode.FORBIDDEN: "权限不足",
    ErrorCode.NOT_FOUND: "资源不存在",
    ErrorCode.RATE_LIMITED: "操作过于频繁，请稍后再试",
    ErrorCode.UPLOAD_REJECTED: "文件类型不支持或超过大小限制",
    ErrorCode.BAD_CREDENTIALS: "账号或密码错误",
    ErrorCode.DUPLICATE_ACCOUNT: "邮箱或用户名已被注册",
    ErrorCode.CONVERSATION_NOT_FOUND: "会话不存在",
    ErrorCode.CONVERSATION_PAUSED: "该会话已因安全原因暂停，请先确认安全状态",
    ErrorCode.LLM_UNAVAILABLE: "模型服务暂不可用",
    ErrorCode.LLM_TIMEOUT: "模型调用超时",
    ErrorCode.DOC_PARSE_FAILED: "文档解析失败",
    ErrorCode.EMBEDDING_FAILED: "向量化失败",
    ErrorCode.INTERNAL_ERROR: "服务器内部错误",
}

DEFAULT_HTTP_STATUS = {
    ErrorCode.INVALID_PARAM: 400,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.UPLOAD_REJECTED: 400,
    ErrorCode.BAD_CREDENTIALS: 401,
    ErrorCode.DUPLICATE_ACCOUNT: 409,
    ErrorCode.CONVERSATION_NOT_FOUND: 404,
    ErrorCode.CONVERSATION_PAUSED: 409,
    ErrorCode.LLM_UNAVAILABLE: 503,
    ErrorCode.LLM_TIMEOUT: 504,
    ErrorCode.DOC_PARSE_FAILED: 500,
    ErrorCode.EMBEDDING_FAILED: 500,
    ErrorCode.INTERNAL_ERROR: 500,
}


class ApiError(Exception):
    """业务异常。抛出后由全局处理器转成统一响应体。"""

    def __init__(
        self,
        code: int,
        message: str | None = None,
        http_status: int | None = None,
        data: Any = None,
    ):
        self.code = code
        self.message = message or DEFAULT_MESSAGES.get(code, "请求失败")
        self.http_status = http_status or DEFAULT_HTTP_STATUS.get(code, 400)
        # 可选的结构化附加信息。目前用于限流：data={"retry_after": 37}
        self.data = data
        super().__init__(self.message)


def register_error_handlers(app: Flask) -> None:
    from flask_jwt_extended.exceptions import JWTExtendedException
    from werkzeug.exceptions import HTTPException as _HTTPException

    _register_jwt_loaders(app)

    @app.errorhandler(ApiError)
    def _handle_api_error(exc: ApiError):
        app.logger.info("业务异常 code=%s message=%s", exc.code, exc.message)
        response, status = fail(exc.code, exc.message, exc.http_status, data=exc.data)
        # 限流时补上标准的 Retry-After 头，方便前端与中间代理读取
        if isinstance(exc.data, dict) and "retry_after" in exc.data:
            response.headers["Retry-After"] = str(exc.data["retry_after"])
        return response, status

    @app.errorhandler(JWTExtendedException)
    def _handle_jwt_error(exc: JWTExtendedException):
        app.logger.info("鉴权异常：%s", exc)
        return fail(ErrorCode.UNAUTHORIZED, DEFAULT_MESSAGES[ErrorCode.UNAUTHORIZED], 401)

    @app.errorhandler(_HTTPException)
    def _handle_http_error(exc: _HTTPException):
        code = exc.code or 500
        mapped = {
            400: ErrorCode.INVALID_PARAM,
            401: ErrorCode.UNAUTHORIZED,
            403: ErrorCode.FORBIDDEN,
            404: ErrorCode.NOT_FOUND,
            405: ErrorCode.NOT_FOUND,
            413: ErrorCode.UPLOAD_REJECTED,
            429: ErrorCode.RATE_LIMITED,
        }.get(code, ErrorCode.INTERNAL_ERROR)
        message = DEFAULT_MESSAGES.get(mapped, exc.description or "请求失败")
        return fail(mapped, message, code)

    @app.errorhandler(Exception)
    def _handle_unexpected(exc: Exception):
        app.logger.exception("未捕获异常：%s", exc)
        return fail(ErrorCode.INTERNAL_ERROR, DEFAULT_MESSAGES[ErrorCode.INTERNAL_ERROR], 500)


def _jwt_error(reason: str):
    """统一的 JWT 失败响应：401 + 1002。"""
    return fail(ErrorCode.UNAUTHORIZED, f"{DEFAULT_MESSAGES[ErrorCode.UNAUTHORIZED]}（{reason}）", 401)


def _register_jwt_loaders(app: Flask) -> None:
    """注册 JWT 各类失败的载荷回调。

    若不注册，PyJWT 抛出的 ExpiredSignatureError 会落到通用异常处理器上
    变成 500，前端就无法走"401 → 静默 refresh"的路径。
    """
    from app.extensions import jwt

    @jwt.unauthorized_loader
    def _missing_token(reason: str):
        return _jwt_error(reason or "缺少令牌")

    @jwt.invalid_token_loader
    def _invalid_token(reason: str):
        return _jwt_error(reason or "令牌无效")

    @jwt.expired_token_loader
    def _expired_token(jwt_header, jwt_payload):  # noqa: ANN001
        return _jwt_error("令牌已过期")

    @jwt.revoked_token_loader
    def _revoked_token(jwt_header, jwt_payload):  # noqa: ANN001
        return _jwt_error("令牌已被撤销")

    @jwt.needs_fresh_token_loader
    def _needs_fresh(jwt_header, jwt_payload):  # noqa: ANN001
        return _jwt_error("需要重新登录")


__all__ = ["ErrorCode", "ApiError", "register_error_handlers", "DEFAULT_MESSAGES"]

