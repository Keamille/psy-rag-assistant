"""会话与消息接口（开发文档 §7.5 / §7.6）。

分层约定（开发文档 §6.1）：
    路由函数只做三件事——解析入参、调用 service、组装响应。
    归属校验、软删除过滤、分页归一化、幂等这些都在
    `app/services/conversation_service.py` 里，本文件不写查询条件。

这样做的直接好处是：本文件可以快速读完，而"哪些数据能被看到"
这类问题只需要去 service 里看一处。
"""

from __future__ import annotations

from flask import Blueprint, g, request
from flask import Response, stream_with_context

from app.core.errors import ApiError, ErrorCode
from app.core.rate_limit import enforce_message_quota, enforce_message_rate
from app.core.response import ok
from app.core.security import login_required
from app.services import conversation_service
from app.services.chat_service import ChatService

bp = Blueprint("conversations", __name__)


# ---------------------------------------------------------------------------
# 会话
# ---------------------------------------------------------------------------


@bp.get("")
@login_required
def list_conversations():
    """会话列表。支持 page / size / status，按最近更新倒序。"""
    payload = conversation_service.list_conversations(
        user_id=g.current_user_id,
        page=request.args.get("page", type=int),
        size=request.args.get("size", type=int),
        status=request.args.get("status"),
    )
    return ok(data=payload)


@bp.post("")
@login_required
def create_conversation():
    """新建会话。请求体可省略，或只给 title。"""
    body = request.get_json(silent=True) or {}
    conversation = conversation_service.create_conversation(
        user_id=g.current_user_id,
        title=body.get("title") if isinstance(body, dict) else None,
    )
    return ok(data=conversation.to_dict(message_count=0))


@bp.get("/<int:conversation_id>")
@login_required
def get_conversation(conversation_id: int):
    conversation = conversation_service.get_owned(conversation_id, g.current_user_id)
    return ok(
        data=conversation.to_dict(
            message_count=conversation_service.count_messages(conversation.id)
        )
    )


@bp.patch("/<int:conversation_id>")
@login_required
def update_conversation(conversation_id: int):
    """改标题或归档。status 只接受 active / archived。"""
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        raise ApiError(ErrorCode.INVALID_PARAM, "请求体必须是 JSON 对象")

    conversation = conversation_service.update_conversation(
        conversation_id=conversation_id,
        user_id=g.current_user_id,
        title=body.get("title"),
        status=body.get("status"),
    )
    return ok(
        data=conversation.to_dict(
            message_count=conversation_service.count_messages(conversation.id)
        )
    )


@bp.delete("/<int:conversation_id>")
@login_required
def delete_conversation(conversation_id: int):
    """软删除。只写 deleted_at，不物理删行。"""
    conversation_service.soft_delete_conversation(conversation_id, g.current_user_id)
    return ok(data=None)


# ---------------------------------------------------------------------------
# 消息
# ---------------------------------------------------------------------------


@bp.get("/<int:conversation_id>/messages")
@login_required
def list_messages(conversation_id: int):
    """消息列表，倒序返回（前端自行翻转成正序）。"""
    payload = conversation_service.list_messages(
        conversation_id=conversation_id,
        user_id=g.current_user_id,
        page=request.args.get("page", type=int),
        size=request.args.get("size", type=int),
    )
    return ok(data=payload)


@bp.post("/<int:conversation_id>/messages")
@login_required
def send_message(conversation_id: int):
    """SSE 流式对话（开发文档 §7.6）。

    校验顺序：归属 → 暂停状态 → 限流与配额 → 请求体。
    越早失败的检查放越前面——省掉后面的开销，也让错误定位更直接。

    校验不通过时返回**普通 JSON 错误**，不进入事件流：
    一旦开始推 text/event-stream，前端就按流去解析了，
    再塞一个错误对象进去会破坏协议。
    """
    user_id = g.current_user_id
    conversation = conversation_service.get_owned(conversation_id, user_id)

    if conversation.status == "paused":
        raise ApiError(ErrorCode.CONVERSATION_PAUSED)

    enforce_message_rate(user_id)
    enforce_message_quota(user_id)

    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        raise ApiError(ErrorCode.INVALID_PARAM, "请求体必须是 JSON 对象")

    text = (body.get("text") or "").strip()
    if not text:
        raise ApiError(ErrorCode.INVALID_PARAM, "消息内容不能为空")
    # 长度也必须在**进入流之前**校验。
    # 放到 service 里校验的话，异常会在生成器内部抛出——
    # 那时响应头已经发出去了，前端拿到的是一个中途断掉的流，
    # 而不是一个干净的 400。
    if len(text) > 4000:
        raise ApiError(ErrorCode.INVALID_PARAM, "消息长度需在 1-4000 字符之间")

    service = ChatService(user_id=user_id, conversation=conversation)

    def event_stream():
        yield from service.stream_reply(
            text=text, client_msg_id=body.get("client_msg_id")
        )

    return Response(
        stream_with_context(event_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # 关掉 Nginx 的响应缓冲。漏了这一行，流式回答会退化成
            # "转圈很久后整段蹦出来"——这是本项目最容易翻车的部署问题。
            "X-Accel-Buffering": "no",
        },
    )


@bp.post("/<int:conversation_id>/resume")
@login_required
def resume_conversation(conversation_id: int):
    """危机中断后解锁会话（开发文档 §10.3）。

    要求客户端显式传 `{"confirm": "i_am_safe"}`，并要求会话确实处于 paused。
    这两道校验的意义在于：解锁是一次有后果的操作（会写审计日志），
    不应该被一个误触或重放请求完成。
    """
    conversation = conversation_service.get_owned(conversation_id, g.current_user_id)

    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict) or body.get("confirm") != "i_am_safe":
        raise ApiError(
            ErrorCode.INVALID_PARAM,
            '需显式确认安全：请发送 {"confirm": "i_am_safe"}',
        )

    if conversation.status != "paused":
        raise ApiError(ErrorCode.INVALID_PARAM, "该会话当前不处于锁定状态")

    conversation_service.resume_conversation(conversation_id, g.current_user_id)
    return ok(
        data=conversation.to_dict(
            message_count=conversation_service.count_messages(conversation.id)
        )
    )

