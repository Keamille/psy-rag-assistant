"""鉴权、密码与权限。

集中放在这里的三类能力：
1. 密码：argon2 哈希与校验（**禁止**任何可逆加密或 MD5/SHA1）
2. 请求身份：装饰器 + 数据库二次校验
3. 令牌黑名单：注销后让旧令牌立即失效
"""

from __future__ import annotations

import re
from functools import wraps
from typing import Callable

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from flask import current_app, g
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request

from app.core.errors import ApiError, ErrorCode
from app.extensions import redis_store

ROLE_USER = "user"
ROLE_ADMIN = "admin"

# argon2 的哈希开销是**故意**设计得昂贵的（默认 m=64MB, t=3）。
# 但跑测试时每个用例都要建用户、验密码，用生产参数会让测试慢到难以忍受。
# 因此参数做成可配置：生产用默认值，测试用最便宜的合法值。
_hasher: PasswordHasher | None = None
_hasher_params: dict | None = None


def _get_hasher() -> PasswordHasher:
    """按当前应用配置返回 hasher；配置变化时自动重建。"""
    global _hasher, _hasher_params

    params: dict | None
    try:
        params = current_app.config.get("ARGON2_PARAMS") or None
    except RuntimeError:
        # 不在应用上下文里（例如命令行脚本）时用生产默认值
        params = None

    if _hasher is None or params != _hasher_params:
        _hasher = PasswordHasher(**params) if params else PasswordHasher()
        _hasher_params = params
    return _hasher


# --------------------------------------------------------------------------
# 密码
# --------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """生成 argon2id 哈希。返回值约 97 字符。"""
    return _get_hasher().hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """校验密码。哈希串损坏等异常一律按"校验失败"处理，不向外抛出。"""
    try:
        return _get_hasher().verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, ValueError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """参数升级后（例如提高了内存开销），旧哈希需要重新计算。"""
    try:
        return _get_hasher().check_needs_rehash(password_hash)
    except (VerificationError, ValueError):
        return True


def is_valid_password(password: str) -> bool:
    """密码规则：至少 10 位，且同时包含字母与数字。

    刻意不强制大小写与特殊字符——过严的规则会把用户推向"写在便利贴上"。
    """
    if not isinstance(password, str) or len(password) < 10:
        return False
    if not re.search(r"[A-Za-z]", password):
        return False
    if not re.search(r"\d", password):
        return False
    return True


# --------------------------------------------------------------------------
# 请求身份
# --------------------------------------------------------------------------


def load_current_user() -> None:
    """解析令牌并做**数据库二次校验**。

    为什么必须回查数据库：JWT 是无状态的，签发后服务端无法更改其内容。
    如果用户已被禁用、或角色被降级，仅凭令牌里的 claim 判断会让旧令牌
    继续保有权限，直到过期为止。因此这里以数据库为权威来源。

    校验失败统一返回 401/1002，不区分"用户不存在"与"用户被禁用"。
    """
    from app.models import User  # 延迟导入：避免 models 与 core 的循环依赖

    user_id = int(get_jwt_identity())

    # 用户级失效检查：删除全部数据或"退出所有设备"后，
    # 该用户此前签发的令牌应立刻失效，而不必等它们自然过期。
    cutoff = redis_store.get_user_cutoff(user_id)
    if cutoff is not None:
        issued_at = get_jwt().get("iat")
        if issued_at is not None and int(issued_at) < cutoff:
            raise ApiError(ErrorCode.UNAUTHORIZED, "登录状态已失效，请重新登录", 401)

    user = User.query.get(user_id)
    if user is None or not user.is_active:
        raise ApiError(ErrorCode.UNAUTHORIZED, "账号不可用或已被禁用", 401)

    g.current_user = user
    g.current_user_id = user.id
    # 角色以数据库为准：管理员被降级后，旧令牌不应继续拥有管理员权限
    g.current_user_role = user.role


def login_required(fn: Callable) -> Callable:
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        load_current_user()
        return fn(*args, **kwargs)

    return wrapper


def role_required(*roles: str) -> Callable:
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            load_current_user()
            if g.current_user_role not in roles:
                raise ApiError(ErrorCode.FORBIDDEN)
            return fn(*args, **kwargs)

        return wrapper

    return decorator


admin_required = role_required(ROLE_ADMIN)


# --------------------------------------------------------------------------
# 令牌黑名单
# --------------------------------------------------------------------------


def revoke_token(jti: str, exp_timestamp: int) -> bool:
    """把令牌的 jti 加入黑名单，TTL 与令牌剩余有效期一致。

    Redis 不可用时返回 False（调用方据此决定是否提示），
    因为"注销失败"应当让用户知道，而不是静默假装成功。
    """
    import time

    ttl = max(int(exp_timestamp) - int(time.time()), 1)
    return redis_store.blocklist_add(jti, ttl)


def register_jwt_blocklist(jwt_manager) -> None:
    """注册令牌黑名单校验回调。

    放在 core 层统一注册，而不是塞在 create_app 里，
    这样 create_app 只保留"组装"职责。

    **降级行为的取舍**：Redis 不可用时 token_in_blocklist_loader 返回 False，
    即"不拦截"。这是可用性优先的选择——否则 Redis 一挂，全部已登录用户
    会被立刻踢下线。代价是此时已注销的令牌在过期前仍可用，属于已知残余风险。
    """

    @jwt_manager.token_in_blocklist_loader
    def _is_token_revoked(jwt_header, jwt_payload) -> bool:  # noqa: ANN001
        jti = jwt_payload.get("jti")
        if not jti:
            return False
        return redis_store.blocklist_contain(jti)


__all__ = [
    "hash_password",
    "verify_password",
    "password_needs_rehash",
    "is_valid_password",
    "login_required",
    "role_required",
    "admin_required",
    "revoke_token",
    "register_jwt_blocklist",
    "ROLE_USER",
    "ROLE_ADMIN",
]
