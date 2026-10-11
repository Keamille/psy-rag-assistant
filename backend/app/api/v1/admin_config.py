"""可调参数配置（开发文档 §7.7）。权限：admin。

GET 返回当前生效值（环境变量 + Redis 覆盖层），PUT 写入覆盖层，
重启后仍然生效。不可在线修改的键必须改环境变量并重启。
"""

from __future__ import annotations

from flask import Blueprint, current_app
from flask import g, request

from app.core.errors import ApiError, ErrorCode
from app.core.response import ok
from app.core.security import admin_required
from app.extensions import redis_store

bp = Blueprint("admin_config", __name__)

# 在线覆盖值存在这个 Redis 哈希里，重启后仍然生效。
# 与 .env 的关系：.env 是默认值，这里存的是运行期覆盖值；
# 读取时先看 Redis，没有才回落到配置。
OVERRIDE_KEY = "admin:config:overrides"

# 对外一律用 snake_case（与 values 载荷、开发文档 7.7 的 PUT 示例一致），
# 对外键名 → 内部配置项名的映射，PUT 时按这张表逐项写回。
EDITABLE_KEYS: dict[str, str] = {
    "top_k_retrieve": "TOP_K_RETRIEVE",
    "top_k_rerank": "TOP_K_RERANK",
    "rerank_enabled": "RERANK_ENABLED",
    "llm_temperature": "LLM_TEMPERATURE",
    "llm_max_tokens": "LLM_MAX_TOKENS",
    "daily_message_quota": "DAILY_MESSAGE_QUOTA",
    "hotline_region": "HOTLINE_REGION",
}

# 不可在线调整：需改环境变量并重启（开发文档 7.7）
RESTART_REQUIRED_KEYS = [
    "DATABASE_URL",
    "CHROMA_HOST",
    "CHROMA_PORT",
    "REDIS_URL",
    "EMBEDDING_MODEL",
    "JWT_SECRET",
]


@bp.get("")
@admin_required
def get_config():
    payload = {
        "top_k_retrieve": current_app.config["TOP_K_RETRIEVE"],
        "top_k_rerank": current_app.config["TOP_K_RERANK"],
        "rerank_enabled": current_app.config["RERANK_ENABLED"],
        "llm_temperature": current_app.config["LLM_TEMPERATURE"],
        "llm_max_tokens": current_app.config["LLM_MAX_TOKENS"],
        "daily_message_quota": current_app.config["DAILY_MESSAGE_QUOTA"],
        "hotline_region": current_app.config["HOTLINE_REGION"],
    }
    overrides = redis_store.get_json(OVERRIDE_KEY) or {}
    payload.update({k: v for k, v in overrides.items() if k in payload})

    return ok(
        {
            "values": payload,
            "source": "redis+environment" if overrides else "environment",
            "editable_keys": list(EDITABLE_KEYS),
            "restart_required_keys": RESTART_REQUIRED_KEYS,
        }
    )


@bp.put("")
@admin_required
def update_config():
    """在线修改可调参数。

    只接受 EDITABLE_KEYS 里的键：数据库连接、模型路径这类改了会立刻
    让进程处于不一致状态的参数，必须改环境变量后重启，
    允许在线改反而更危险。
    """
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict) or not body:
        raise ApiError(ErrorCode.INVALID_PARAM, "请求体必须是非空 JSON 对象")

    unknown = sorted(set(body) - set(EDITABLE_KEYS))
    if unknown:
        raise ApiError(
            ErrorCode.INVALID_PARAM,
            f"以下参数不支持在线修改：{'、'.join(unknown)}。"
            f"可改的是：{'、'.join(sorted(EDITABLE_KEYS))}",
        )

    current = redis_store.get_json(OVERRIDE_KEY) or {}
    current.update(body)

    if not redis_store.set_json(OVERRIDE_KEY, current):
        raise ApiError(
            ErrorCode.INTERNAL_ERROR,
            "配置写入失败：Redis 不可用，当前修改不会生效",
            503,
        )

    from app.models import AuditLog
    from app.extensions import db
    import json as _json

    db.session.add(
        AuditLog(
            actor_id=int(g.current_user_id),
            action="update_config",
            target_type="config",
            detail_json=_json.dumps(body, ensure_ascii=False),
            request_id=getattr(g, "request_id", None),
        )
    )
    db.session.commit()

    return ok(data={"updated": sorted(body), "source": "redis"})

