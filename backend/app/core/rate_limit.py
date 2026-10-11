"""基于 Redis 的限流与配额。

Redis 不可用时不阻断请求，仅在响应头标注降级状态——
限流是保护措施而不是业务前提，不该让它在依赖缺失时把接口整体打死。
"""

from __future__ import annotations

from datetime import date

from flask import current_app, g

from app.core.errors import ApiError, ErrorCode
from app.extensions import redis_store


def _check(key: str, limit: int, window_seconds: int) -> None:
    count = redis_store.incr_with_ttl(key, window_seconds)
    if count is None:
        # Redis 不可用：降级放行
        g.rate_limit_degraded = True
        return
    if count > limit:
        # 告诉调用方还要等多久，前端才能做倒计时。
        # 拿不到 TTL（key 恰好过期等边界情况）时回退成整个窗口长度。
        retry_after = redis_store.ttl_seconds(key) or window_seconds
        raise ApiError(
            ErrorCode.RATE_LIMITED,
            http_status=429,
            data={"retry_after": int(retry_after)},
        )


def enforce_message_rate(user_id: int) -> None:
    limit = current_app.config["MESSAGE_RATE_PER_MINUTE"]
    _check(f"rl:msg:min:{user_id}", limit, 60)


def enforce_message_quota(user_id: int) -> None:
    limit = current_app.config["DAILY_MESSAGE_QUOTA"]
    today = date.today().isoformat()
    _check(f"rl:msg:day:{today}:{user_id}", limit, 86400)


def remaining_message_quota(user_id: int) -> int | None:
    client = redis_store.client
    if client is None:
        return None
    today = date.today().isoformat()
    try:
        used = int(client.get(f"rl:msg:day:{today}:{user_id}") or 0)
    except Exception:  # noqa: BLE001
        return None
    return max(current_app.config["DAILY_MESSAGE_QUOTA"] - used, 0)


def enforce_login_rate(ip: str) -> None:
    _check(f"rl:login:{ip}", 5, 60)


def enforce_register_rate(ip: str) -> None:
    _check(f"rl:register:{ip}", 3, 3600)


def enforce_upload_rate(user_id: int) -> None:
    _check(f"rl:upload:day:{date.today().isoformat()}:{user_id}", 10, 86400)


__all__ = [
    "enforce_message_rate",
    "enforce_message_quota",
    "remaining_message_quota",
    "enforce_login_rate",
    "enforce_register_rate",
    "enforce_upload_rate",
]

