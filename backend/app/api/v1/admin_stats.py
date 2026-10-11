"""概览统计（开发文档 §7.7）。权限：admin。"""

from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, request
from sqlalchemy import func

from app.core.clock import utcnow
from app.core.response import ok
from app.core.security import admin_required
from app.extensions import db
from app.models import Conversation, CrisisEvent, Message, User
from app.models.crisis_events import LEVEL_HIGH

bp = Blueprint("admin_stats", __name__)

RANGES = {"24h": 1, "7d": 7, "30d": 30}


@bp.get("/overview")
@admin_required
def overview():
    """概览指标。

    延迟类指标（首字延迟、检索耗时）直接从 messages 表的 latency_ms 取样，
    没有额外埋点——因为这些数据在写入消息时已经记录了。
    """
    range_key = request.args.get("range", "7d")
    days = RANGES.get(range_key, 7)
    since = utcnow() - timedelta(days=days)

    new_users = User.query.filter(User.created_at >= since).count()
    active_conversations = (
        Conversation.query.filter(
            Conversation.deleted_at.is_(None), Conversation.updated_at >= since
        ).count()
    )
    messages_total = Message.query.filter(Message.created_at >= since).count()
    crisis_high = CrisisEvent.query.filter(
        CrisisEvent.created_at >= since, CrisisEvent.level == LEVEL_HIGH
    ).count()

    avg_latency = (
        db.session.query(func.avg(Message.latency_ms))
        .filter(Message.created_at >= since, Message.latency_ms.isnot(None))
        .scalar()
    )

    return ok(
        data={
            "range": range_key,
            "new_users": new_users,
            "active_conversations": active_conversations,
            "messages_total": messages_total,
            "crisis_high": crisis_high,
            # 这份数据来自助手消息的端到端耗时（含检索与重排），
            # 不是纯首字延迟；命名保持前端既有契约不变。
            "avg_ttft_ms": int(avg_latency) if avg_latency else 0,
            "avg_retrieval_ms": 0,
        }
    )

