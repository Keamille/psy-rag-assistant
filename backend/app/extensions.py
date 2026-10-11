"""Flask 扩展实例。

Redis 采用惰性连接：Redis 不可用时应用仍能启动，
依赖 Redis 的能力（限流、队列）降级而不是崩溃。
"""

from __future__ import annotations

import logging
from typing import Any

import redis as redis_lib
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

logger = logging.getLogger(__name__)

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
cors = CORS()


class RedisStore:
    """极简 Redis 门面：惰性建连 + 失败降级。"""

    def __init__(self) -> None:
        self._client: redis_lib.Redis | None = None
        self._url: str | None = None
        self._available: bool | None = None

    def init_app(self, app) -> None:  # noqa: ANN001 - Flask app
        self._url = app.config.get("REDIS_URL")
        self._timeout = app.config.get("REDIS_TIMEOUT", 2)
        app.extensions["redis_store"] = self

    @property
    def client(self) -> redis_lib.Redis | None:
        if self._client is None and self._url:
            try:
                self._client = redis_lib.Redis.from_url(
                    self._url,
                    socket_connect_timeout=self._timeout,
                    socket_timeout=self._timeout,
                    decode_responses=True,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Redis 客户端创建失败：%s", exc)
                return None
        return self._client

    def ping(self) -> tuple[bool, str | None]:
        client = self.client
        if client is None:
            return False, "未配置 REDIS_URL"
        try:
            client.ping()
            self._available = True
            return True, None
        except Exception as exc:  # noqa: BLE001
            self._available = False
            return False, str(exc)

    def is_available(self) -> bool:
        if self._available is None:
            ok, _ = self.ping()
            return ok
        return bool(self._available)

    def get_json(self, key: str) -> Any:  # noqa: ANN401
        client = self.client
        if client is None:
            return None
        try:
            import json

            raw = client.get(key)
            return json.loads(raw) if raw else None
        except Exception:  # noqa: BLE001
            return None

    def set_json(self, key: str, value: Any, ttl: int | None = None) -> bool:  # noqa: ANN401
        client = self.client
        if client is None:
            return False
        try:
            import json

            client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
            return True
        except Exception:  # noqa: BLE001
            return False

    def incr_with_ttl(self, key: str, ttl: int) -> int | None:
        """原子自增并在首次创建时设置过期时间；Redis 不可用返回 None。"""
        client = self.client
        if client is None:
            return None
        try:
            pipe = client.pipeline()
            pipe.incr(key)
            pipe.expire(key, ttl)
            count, _ = pipe.execute()
            return int(count)
        except Exception:  # noqa: BLE001
            return None

    def ttl_seconds(self, key: str) -> int | None:
        """返回 key 的剩余存活秒数。

        用于限流提示"还要等多久"。以下情况都返回 None：
        - Redis 不可用
        - key 不存在（TTL 返回 -2）
        - key 存在但没有过期时间（TTL 返回 -1）
        """
        client = self.client
        if client is None:
            return None
        try:
            ttl = int(client.ttl(key))
        except Exception:  # noqa: BLE001
            return None
        return ttl if ttl > 0 else None

    # ------------------------------------------------------------------
    # 令牌黑名单
    # ------------------------------------------------------------------
    # 用于"注销后旧令牌立即失效"。JWT 本身无状态，只能靠服务端记录
    # 已注销的 jti 来实现撤销。

    BLOCKLIST_PREFIX = "jwt:blocklist:"

    def blocklist_add(self, jti: str, ttl: int) -> bool:
        """把 jti 写入黑名单。Redis 不可用时返回 False，由调用方决定怎么提示。"""
        client = self.client
        if client is None:
            logger.warning("Redis 不可用，令牌撤销失败：jti=%s", jti)
            return False
        try:
            client.set(f"{self.BLOCKLIST_PREFIX}{jti}", "1", ex=max(int(ttl), 1))
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("令牌撤销失败：%s", exc)
            return False

    def blocklist_contain(self, jti: str) -> bool:
        """判断 jti 是否已被撤销。

        **降级口径**：Redis 不可用时返回 False（视为未撤销）。
        这是可用性优先的选择——否则 Redis 一挂，所有已登录用户会被立刻踢下线。
        代价是此期间已注销的令牌在自然过期前仍可用。
        """
        client = self.client
        if client is None:
            return False
        try:
            return bool(client.exists(f"{self.BLOCKLIST_PREFIX}{jti}"))
        except Exception:  # noqa: BLE001
            return False

    # 用户级令牌失效：删除全部数据、或用户要求"退出所有设备"时使用。
    # 不去逐个枚举该用户已签发的 jti（那是无状态的 JWT 做不到的），
    # 而是记一个"签发时间早于此的令牌一律失效"的截止点，靠 iat 比对。
    USER_CUTOFF_PREFIX = "jwt:user_cutoff:"

    def set_user_cutoff(self, user_id: int, timestamp: int) -> bool:
        return self.set_json(f"{self.USER_CUTOFF_PREFIX}{user_id}", int(timestamp))

    def get_user_cutoff(self, user_id: int) -> int | None:
        value = self.get_json(f"{self.USER_CUTOFF_PREFIX}{user_id}")
        return int(value) if isinstance(value, int) else None


redis_store = RedisStore()

__all__ = ["db", "migrate", "jwt", "cors", "redis_store", "RedisStore"]

