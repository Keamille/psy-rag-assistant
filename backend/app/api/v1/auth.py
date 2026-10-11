"""认证接口（开发文档 §7.3）。

四个端点：注册 / 登录 / 刷新令牌 / 注销。

两个容易踩的实现细节，写在最前面：
1. **JWT 的 `sub` 必须是字符串**。PyJWT 2.10 起强制校验，传 int 会在
   签发那一刻抛 TypeError；因此一律用 `identity=str(user.id)`。
2. **配置必须在请求上下文里读**（`current_app.config`），不能在模块层读成常量，
   否则测试用 `create_app("testing")` 覆盖配置时不生效。
"""

from __future__ import annotations

import re

from flask import Blueprint, current_app, g, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
)
from sqlalchemy.exc import IntegrityError

from app.core.clock import utcnow
from app.core.errors import ApiError, ErrorCode
from app.core.rate_limit import enforce_login_rate, enforce_register_rate
from app.core.response import ok
from app.core.security import (
    ROLE_USER,
    hash_password,
    is_valid_password,
    password_needs_rehash,
    revoke_token,
    verify_password,
)
from app.extensions import db
from app.models import AuditLog, User

bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

USERNAME_MIN, USERNAME_MAX = 3, 64

# 用于"账号不存在"时也走一次哈希校验的哑哈希，让两种失败耗时接近
_DUMMY_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$"
    "c29tZXNhbHRzb21lc2FsdA$"
    "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE"
)


# --------------------------------------------------------------------------
# 入参解析
# --------------------------------------------------------------------------


def _json_body() -> dict:
    """取请求体。非 JSON 或不是对象时给出 1001，而不是让框架抛 500。"""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ApiError(ErrorCode.INVALID_PARAM, "请求体必须是 JSON 对象")
    return body


def _require_str(body: dict, key: str, label: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ApiError(ErrorCode.INVALID_PARAM, f"{label}不能为空")
    return value


def _normalize_account(raw: str) -> str:
    """账号归一化：去首尾空白并转小写。

    注册与登录必须共用这一套规则，否则会出现"注册时存了 XyZ、
    登录时输入 xyz 却找不到"的问题。
    """
    return raw.strip().lower()


def _access_token(user: User) -> str:
    # role 仅作展示用途；鉴权以数据库为准（见 core/security.load_current_user）
    return create_access_token(identity=str(user.id), additional_claims={"role": user.role})


def _refresh_token(user: User) -> str:
    return create_refresh_token(identity=str(user.id))


def _expires_in() -> int:
    return int(current_app.config["JWT_ACCESS_TOKEN_EXPIRES"].total_seconds())


# --------------------------------------------------------------------------
# 注册
# --------------------------------------------------------------------------


@bp.post("/register")
def register():
    enforce_register_rate(request.remote_addr or "unknown")
    body = _json_body()

    username = _normalize_account(_require_str(body, "username", "用户名"))
    email = _normalize_account(_require_str(body, "email", "邮箱"))
    password = _require_str(body, "password", "密码")

    if not EMAIL_RE.match(email):
        raise ApiError(ErrorCode.INVALID_PARAM, "邮箱格式不正确")
    if not (USERNAME_MIN <= len(username) <= USERNAME_MAX):
        raise ApiError(
            ErrorCode.INVALID_PARAM, f"用户名长度需在 {USERNAME_MIN}-{USERNAME_MAX} 之间"
        )
    if not is_valid_password(password):
        raise ApiError(ErrorCode.INVALID_PARAM, "密码至少 10 位，且需同时包含字母与数字")

    # 年龄与知情同意：两项都必须为 True，缺一不可
    if body.get("age_confirmed") is not True:
        raise ApiError(ErrorCode.INVALID_PARAM, "需确认已年满 18 周岁")
    if body.get("consent") is not True:
        raise ApiError(ErrorCode.INVALID_PARAM, "需同意知情同意书后方可注册")

    # 版本校验以**服务端配置**为准，不信任客户端传来的值
    expected_version = current_app.config["CONSENT_VERSION"]
    if body.get("consent_version") != expected_version:
        raise ApiError(
            ErrorCode.INVALID_PARAM,
            f"知情同意书版本已更新（当前 {expected_version}），请刷新页面后重试",
        )

    # 先查一次给出具体提示；唯一索引仍然兜底并发注册
    if User.query.filter_by(username=username).first() is not None:
        raise ApiError(ErrorCode.DUPLICATE_ACCOUNT, "该用户名已被注册")
    if User.query.filter_by(email=email).first() is not None:
        raise ApiError(ErrorCode.DUPLICATE_ACCOUNT, "该邮箱已被注册")

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        # 角色强制为普通用户：绝不接受客户端传入的 role，
        # 否则任何人都能用 {"role": "admin"} 把自己注册成管理员
        role=ROLE_USER,
        status="active",
        consent_version=expected_version,
        consented_at=utcnow(),
    )
    try:
        db.session.add(user)
        db.session.commit()
    except IntegrityError:
        # 并发注册同名账号时走到这里
        db.session.rollback()
        raise ApiError(ErrorCode.DUPLICATE_ACCOUNT, "用户名或邮箱已被注册") from None

    return ok(
        data={
            "user": user.to_dict(),
            "access_token": _access_token(user),
            "refresh_token": _refresh_token(user),
            "expires_in": _expires_in(),
        }
    )


# --------------------------------------------------------------------------
# 登录
# --------------------------------------------------------------------------


@bp.post("/login")
def login():
    enforce_login_rate(request.remote_addr or "unknown")
    body = _json_body()

    account = _normalize_account(_require_str(body, "account", "账号"))
    password = _require_str(body, "password", "密码")

    # 用户名或邮箱都能登录
    user = User.query.filter(db.or_(User.username == account, User.email == account)).first()

    if user is None:
        # 账号不存在时也跑一次哈希校验，让两种失败的响应耗时接近，
        # 避免通过计时差异探测某个账号是否已注册。
        verify_password(_DUMMY_HASH, password)
        raise ApiError(ErrorCode.BAD_CREDENTIALS)

    if not verify_password(user.password_hash, password):
        raise ApiError(ErrorCode.BAD_CREDENTIALS)

    # 账号不存在与密码错误统一返回 2001；"已禁用"是运营动作，
    # 明确告知用户有助于其联系管理员，不算信息泄漏。
    if not user.is_active:
        raise ApiError(ErrorCode.FORBIDDEN, "账号已被禁用，请联系管理员")

    # 哈希参数升级后顺手重算
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    user.last_login_at = utcnow()
    db.session.add(
        AuditLog(
            actor_id=user.id,
            action="login",
            target_type="user",
            target_id=user.id,
            request_id=getattr(g, "request_id", None),
            ip=request.remote_addr,
        )
    )
    db.session.commit()

    return ok(
        data={
            "user": user.to_dict(),
            "access_token": _access_token(user),
            "refresh_token": _refresh_token(user),
            "expires_in": _expires_in(),
        }
    )


# --------------------------------------------------------------------------
# 刷新与注销
# --------------------------------------------------------------------------


@bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    """用 refresh 令牌换一枚新的 access 令牌。

    这里必须回查数据库：refresh 令牌有效期长达 14 天，期间用户可能已被禁用，
    不能仅凭"令牌本身有效"就继续签发新令牌。
    """
    user = User.query.get(int(get_jwt_identity()))
    if user is None or not user.is_active:
        raise ApiError(ErrorCode.UNAUTHORIZED, "账号不可用或已被禁用", 401)

    return ok(data={"access_token": _access_token(user), "expires_in": _expires_in()})


@bp.post("/logout")
@jwt_required(refresh=True)
def logout():
    """把当前 refresh 令牌加入黑名单，使其立即失效。

    JWT 是无状态的，服务端无法"删除"已签发的令牌，
    只能记录已注销的 jti，在后续请求中拒绝它。
    """
    claims = get_jwt()
    jti = claims.get("jti")
    exp = claims.get("exp")

    if not jti or exp is None:
        raise ApiError(ErrorCode.UNAUTHORIZED, "令牌缺少必要字段", 401)

    if not revoke_token(jti, int(exp)):
        # Redis 不可用时不能假装注销成功，否则用户以为已退出、令牌实际仍可用
        raise ApiError(
            ErrorCode.INTERNAL_ERROR,
            "注销失败：令牌撤销服务暂不可用，请稍后重试",
            503,
        )

    return ok(data=None)

