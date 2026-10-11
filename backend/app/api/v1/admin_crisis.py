"""危机事件复核（开发文档 §7.7 / §10.8）。权限：admin。"""

from __future__ import annotations

import json

from flask import Blueprint, current_app, g, request
from sqlalchemy import or_

from app.core.clock import utcnow
from app.core.errors import ApiError, ErrorCode
from app.core.response import ok, paginated
from app.core.security import admin_required
from app.extensions import db
from app.models import AuditLog, Conversation, CrisisEvent, Message
from app.models.audit_logs import ACTION_REVIEW_CRISIS
from app.models.crisis_events import FOLLOW_UP_CLOSED, FOLLOW_UP_CONTACTED, FOLLOW_UP_PENDING

bp = Blueprint("admin_crisis", __name__)

VALID_FOLLOW_UP = {FOLLOW_UP_PENDING, FOLLOW_UP_CONTACTED, FOLLOW_UP_CLOSED}

# 详情里展示的上下文条数（前后各 3 条，开发文档 §10.6）
CONTEXT_RADIUS = 3


@bp.get("")
@admin_required
def list_crisis_events():
    page = max(request.args.get("page", 1, type=int), 1)
    size = min(max(request.args.get("size", 20, type=int), 1), current_app.config["MAX_PAGE_SIZE"])

    query = CrisisEvent.query
    level = request.args.get("level")
    if level:
        query = query.filter(CrisisEvent.level == level)
    if request.args.get("reviewed") is not None:
        reviewed = request.args.get("reviewed", "").lower() in ("1", "true", "yes")
        query = query.filter(CrisisEvent.reviewed.is_(reviewed))
    if request.args.get("follow_up_status"):
        query = query.filter(CrisisEvent.follow_up_status == request.args["follow_up_status"])

    query = query.order_by(CrisisEvent.created_at.desc(), CrisisEvent.id.desc())
    pagination = query.paginate(page=page, per_page=size, error_out=False)
    return ok(
        data=paginated(
            [event.to_dict() for event in pagination.items],
            pagination.page,
            pagination.per_page,
            pagination.total,
        )
    )


@bp.get("/<int:event_id>")
@admin_required
def get_crisis_event(event_id: int):
    event = db.session.get(CrisisEvent, event_id)
    if event is None:
        raise ApiError(ErrorCode.NOT_FOUND, "危机事件不存在", 404)

    payload = event.to_dict()
    payload["context"] = _context_around(event)
    return ok(data=payload)


def _context_around(event: CrisisEvent) -> list[dict]:
    """取触发消息前后各 3 条，供人工判断紧急程度。

    只给这几条而不是整段对话，是隐私上的最小必要：复核者需要知道
    "在这句话之前用户经历了什么"，但不需要读到用户全部倾诉内容。
    """
    if not event.message_id:
        return []
    anchor = db.session.get(Message, event.message_id)
    if anchor is None:
        return []
    rows = (
        Message.query.filter(
            Message.conversation_id == event.conversation_id,
            Message.id >= anchor.id - CONTEXT_RADIUS,
            Message.id <= anchor.id + CONTEXT_RADIUS,
        )
        .order_by(Message.id.asc())
        .all()
    )
    return [
        {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at.isoformat() if m.created_at else None}
        for m in rows
    ]


@bp.post("/<int:event_id>/review")
@admin_required
def review_crisis_event(event_id: int):
    event = db.session.get(CrisisEvent, event_id)
    if event is None:
        raise ApiError(ErrorCode.NOT_FOUND, "危机事件不存在", 404)

    body = request.get_json(silent=True) or {}
    status = body.get("follow_up_status")
    if status not in VALID_FOLLOW_UP:
        raise ApiError(
            ErrorCode.INVALID_PARAM,
            f"follow_up_status 只能是 {' / '.join(sorted(VALID_FOLLOW_UP))}",
        )

    event.reviewed = True
    event.reviewed_by = int(g.current_user_id)
    event.reviewed_at = utcnow()
    event.follow_up_status = status
    event.review_note = (body.get("note") or "")[:2000] or None

    db.session.add(
        AuditLog(
            actor_id=int(g.current_user_id),
            action=ACTION_REVIEW_CRISIS,
            target_type="crisis_event",
            target_id=event.id,
            detail_json=json.dumps(
                {"follow_up_status": status, "note": event.review_note}, ensure_ascii=False
            ),
            request_id=getattr(g, "request_id", None),
        )
    )
    db.session.commit()
    return ok(data=event.to_dict())

