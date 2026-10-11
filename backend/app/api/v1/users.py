"""用户接口（开发文档 §7.4）。

关于昵称：开发文档 §7.4 提到 PATCH 可改 `nickname`，但 §5.2 的 DDL 中
并没有这个字段。本次以 DDL 为准，PATCH 只支持改密码；
若要支持昵称需要先给 users 表加列并补一条迁移。
"""

from __future__ import annotations

import json
import time

from flask import Blueprint, Response, current_app, g, request
from flask_jwt_extended import get_jwt

from app.core.clock import utcnow
from app.core.errors import ApiError, ErrorCode
from app.core.rate_limit import remaining_message_quota
from app.core.response import ok
from app.core.security import (
    ROLE_ADMIN,
    hash_password,
    is_valid_password,
    login_required,
    revoke_token,
    verify_password,
)
from app.extensions import db
from app.models import AuditLog, Conversation, Message
from app.models.conversations import STATUS_ARCHIVED

bp = Blueprint("users", __name__)


@bp.get("/me")
@login_required
def get_me():
    """返回当前用户资料与当日剩余消息配额。

    `quota_remaining` 在 Redis 不可用时为 None（前端应显示为"未知"而不是 0，
    否则会误导用户以为配额已用尽）。
    """
    user = g.current_user
    return ok(
        data={
            **user.to_dict(include_private=True),
            "quota_remaining": remaining_message_quota(user.id),
            "is_admin": user.role == ROLE_ADMIN,
        }
    )


@bp.patch("/me")
@login_required
def update_me():
    """修改密码。请求体：`{"old_password": "...", "password": "..."}`。

    改密码后撤销当前 refresh 令牌，强制其他设备重新登录——
    否则"改密码"在用户预期里应当等同于"踢掉所有已登录设备"。
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ApiError(ErrorCode.INVALID_PARAM, "请求体必须是 JSON 对象")

    old_password = body.get("old_password")
    new_password = body.get("password")

    if not isinstance(old_password, str) or not old_password:
        raise ApiError(ErrorCode.INVALID_PARAM, "请输入原密码")
    if not isinstance(new_password, str) or not new_password:
        raise ApiError(ErrorCode.INVALID_PARAM, "请输入新密码")

    user = g.current_user

    if not verify_password(user.password_hash, old_password):
        raise ApiError(ErrorCode.BAD_CREDENTIALS, "原密码不正确")
    if not is_valid_password(new_password):
        raise ApiError(ErrorCode.INVALID_PARAM, "新密码至少 10 位，且需同时包含字母与数字")
    if old_password == new_password:
        raise ApiError(ErrorCode.INVALID_PARAM, "新密码不能与原密码相同")

    user.password_hash = hash_password(new_password)
    db.session.add(
        AuditLog(
            actor_id=user.id,
            action="change_password",
            target_type="user",
            target_id=user.id,
            request_id=getattr(g, "request_id", None),
            ip=request.remote_addr,
        )
    )
    db.session.commit()

    # 撤销当前 refresh 令牌。失败时只记日志、不阻断——
    # 密码已经改成功，此时返回 5xx 会让用户误以为没改上。
    claims = get_jwt()
    jti, exp = claims.get("jti"), claims.get("exp")
    revoked = revoke_token(jti, int(exp)) if jti and exp is not None else False
    if not revoked:
        current_app.logger.warning(
            "改密码后未能撤销 refresh 令牌 user_id=%s（Redis 不可用？）", user.id
        )

    return ok(data={"revoked_current_token": revoked, "changed_at": utcnow().isoformat()})


@bp.get("/me/export")
@login_required
def export_me():
    """导出当前用户的全部数据为 JSON 附件。

    这是《个人信息保护法》下的"可携带权"对应的功能：用户可以把自己的
    数据拿走。所以必须**包含完整内容**，不能只给摘要。
    """
    user = g.current_user
    conversations = (
        Conversation.query.filter_by(user_id=user.id)
        .order_by(Conversation.id.asc())
        .all()
    )

    from app.core.clock import utcnow

    payload = {
        "exported_at": utcnow().isoformat(),
        "user": user.to_dict(include_private=True),
        "conversations": [],
    }

    for conversation in conversations:
        messages = (
            Message.query.filter_by(conversation_id=conversation.id)
            .order_by(Message.id.asc())
            .all()
        )
        payload["conversations"].append(
            {
                "conversation": conversation.to_dict(message_count=len(messages)),
                "messages": [m.to_dict() for m in messages],
            }
        )

    db.session.add(
        AuditLog(
            actor_id=user.id,
            action="export_data",
            target_type="user",
            target_id=user.id,
            detail_json=json.dumps({"conversations": len(conversations)}, ensure_ascii=False),
            request_id=getattr(g, "request_id", None),
            ip=request.remote_addr,
        )
    )
    db.session.commit()

    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return Response(
        body,
        mimetype="application/json",
        headers={
            # 用 attachment 触发浏览器下载而不是直接打开
            "Content-Disposition": 'attachment; filename="psy-assistant-export.json"'
        },
    )


@bp.delete("/me/data")
@login_required
def delete_my_data():
    """删除数据。scope 取 conversations（只删会话）或 all（并失效所有登录）。

    两者都是**软删除**：行还在，只写 deleted_at。原因是危机事件与审计日志
    仍引用着这些会话，物理删除会破坏安全记录的可追溯性。
    这一点必须在界面上向用户说明，否则"删除"看起来没有真正删掉。
    """
    user = g.current_user
    body = request.get_json(silent=True) or {}
    scope = (body.get("scope") or "conversations").lower()
    if scope not in ("conversations", "all"):
        raise ApiError(ErrorCode.INVALID_PARAM, "scope 只能是 conversations 或 all")

    from app.core.clock import utcnow

    now = utcnow()
    affected = (
        Conversation.query.filter_by(user_id=user.id)
        .filter(Conversation.deleted_at.is_(None))
        .all()
    )
    for conversation in affected:
        conversation.deleted_at = now
        conversation.status = STATUS_ARCHIVED
    db.session.commit()

    revoked = False
    if scope == "all":
        # 截止点设为"现在"：此刻之前签发的令牌全部失效
        revoked = revoke_all_tokens(user.id)

    db.session.add(
        AuditLog(
            actor_id=user.id,
            action="delete_data",
            target_type="user",
            target_id=user.id,
            detail_json=json.dumps(
                {"scope": scope, "conversations": len(affected), "tokens_revoked": revoked},
                ensure_ascii=False,
            ),
            request_id=getattr(g, "request_id", None),
            ip=request.remote_addr,
        )
    )
    db.session.commit()

    return ok(
        data={
            "scope": scope,
            "deleted_conversations": len(affected),
            "tokens_revoked": revoked,
            "retention_notice": (
                "会话已标记删除。备份轮转期内（默认 7 天）数据仍可能存在于备份中，"
                "之后会随备份轮转清除。危机事件记录会按合规要求保留更久。"
            ),
        }
    )


def revoke_all_tokens(user_id: int) -> bool:
    """让该用户所有已签发的令牌立刻失效。Redis 不可用时返回 False。"""
    from app.extensions import redis_store

    cutoff = int(time.time())
    if not redis_store.set_user_cutoff(user_id, cutoff):
        current_app.logger.warning(
            "用户级令牌失效失败（Redis 不可用）user_id=%s；数据已删除，但旧令牌仍有效",
            user_id,
        )
        return False
    return True

