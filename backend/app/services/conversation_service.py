"""会话与消息的业务逻辑（开发文档 §6.1 的 service 层）。

为什么单独抽一层，而不是把查询写在蓝图里：
1. 归属校验、软删除过滤、幂等这三件事在每个端点里都要用，
   写在蓝图里必然复制粘贴，而复制粘贴正是漏掉某个过滤条件的主要来源；
2. 路由函数保持"解析入参 → 调 service → 组装响应"三步，
   读起来不用在 HTTP 细节和查询条件之间来回跳；
3. service 不依赖 request 对象，可以直接用普通函数测试。
"""

from __future__ import annotations

from typing import Any

from flask import g
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func

from app.core.clock import utcnow
from app.core.errors import ApiError, ErrorCode
from app.extensions import db
from app.models import AuditLog, Conversation, Message
from app.models.audit_logs import ACTION_RESUME_CONVERSATION
from app.models.conversations import (
    STATUS_ACTIVE,
    STATUS_ARCHIVED,
    STATUS_PAUSED,
)
from app.models.messages import ROLE_USER

DEFAULT_TITLE = "新的对话"
TITLE_MAX = 120
TEXT_MAX = 4000

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

EDITABLE_STATUS = {STATUS_ACTIVE, STATUS_ARCHIVED}


# ---------------------------------------------------------------------------
# 公共查询
# ---------------------------------------------------------------------------


def get_owned(conversation_id: int, user_id: int) -> Conversation:
    """取属于该用户的未删除会话，取不到就抛 3001。

    两个刻意的设计：

    1. **查询同时带 id 与 user_id**，而不是先按 id 查出来再比较 user_id。
       后者容易出现"忘了比较"的分支，而写在 WHERE 里就不可能忘。
    2. **"不存在"与"不属于你"返回同一个错误码**。若区分开，
       攻击者就能通过错误码差异枚举出系统里有哪些会话 id 存在。
    """
    conversation = Conversation.query.filter(
        Conversation.id == conversation_id,
        Conversation.user_id == user_id,
        Conversation.deleted_at.is_(None),
    ).one_or_none()

    if conversation is None:
        raise ApiError(ErrorCode.CONVERSATION_NOT_FOUND)
    return conversation


def _paging(page: int | None, size: int | None) -> tuple[int, int]:
    """归一化分页参数。

    size 必须设上限：不设的话 `?size=100000` 一次就能把整张表拉出来，
    既是性能问题也是数据泄漏面。
    """
    page_no = max(int(page or 1), 1)
    page_size = int(size or DEFAULT_PAGE_SIZE)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    return page_no, page_size


def _paginated(query, page: int, size: int, to_item) -> dict[str, Any]:
    """把 SQLAlchemy 查询转成契约规定的分页结构。

    契约是 {items, page, size, total}（开发文档 §7.1），
    注意字段名是 size 而不是 per_page。

    `error_out=False` 是关键：Flask-SQLAlchemy 在页码越界时默认会抛 404，
    于是"这个会话还没有消息"这种正常情况会变成 404 报错。
    关掉之后越界页返回空 items。
    """
    pagination = query.paginate(page=page, per_page=size, error_out=False)
    return {
        "items": [to_item(item) for item in pagination.items],
        "page": pagination.page,
        "size": pagination.per_page,
        "total": pagination.total,
    }


# ---------------------------------------------------------------------------
# 会话
# ---------------------------------------------------------------------------


def list_conversations(
    user_id: int,
    page: int | None = None,
    size: int | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """列出该用户的会话，按最近更新倒序。

    必须过滤 deleted_at：软删除的会话不能出现在列表里，
    否则用户"删掉"的对话还会一直挂在那儿。
    """
    page_no, page_size = _paging(page, size)

    query = Conversation.query.filter(
        Conversation.user_id == user_id,
        Conversation.deleted_at.is_(None),
    )
    if status in EDITABLE_STATUS | {STATUS_PAUSED}:
        query = query.filter(Conversation.status == status)

    query = query.order_by(Conversation.updated_at.desc(), Conversation.id.desc())
    page_payload = _paginated(query, page_no, page_size, lambda c: c.to_dict())

    # 补 message_count。用一次聚合查询而不是逐个会话查——
    # 后者在列表有 50 条时就是 51 次数据库往返（经典的 N+1）。
    counts = _message_counts([item["id"] for item in page_payload["items"]])
    for item in page_payload["items"]:
        item["message_count"] = counts.get(item["id"], 0)
    return page_payload


def _message_counts(conversation_ids: list[int]) -> dict[int, int]:
    if not conversation_ids:
        return {}
    rows = (
        db.session.query(Message.conversation_id, func.count(Message.id))
        .filter(Message.conversation_id.in_(conversation_ids))
        .group_by(Message.conversation_id)
        .all()
    )
    return {conversation_id: total for conversation_id, total in rows}


def create_conversation(user_id: int, title: str | None = None) -> Conversation:
    """新建会话。标题可省略，省略时用默认标题。

    注意不要对标题做 .lower()。账号需要归一化（大小写不敏感地比对），
    但标题是展示文本：把 Job Stress 强行变成 job stress 没有任何好处，
    而且会造成"创建时小写、修改时保持原样"这种前后不一致。
    """
    clean = (title or "").strip()
    if len(clean) > TITLE_MAX:
        raise ApiError(ErrorCode.INVALID_PARAM, f"标题不能超过 {TITLE_MAX} 个字符")

    conversation = Conversation(
        user_id=user_id,
        title=clean or DEFAULT_TITLE,
        status=STATUS_ACTIVE,
    )
    db.session.add(conversation)
    db.session.commit()
    return conversation


def count_messages(conversation_id: int) -> int:
    """单个会话的消息条数，用于详情接口的 message_count 字段。"""
    return (
        db.session.query(func.count(Message.id))
        .filter(Message.conversation_id == conversation_id)
        .scalar()
        or 0
    )


def update_conversation(
    conversation_id: int,
    user_id: int,
    title: str | None = None,
    status: str | None = None,
) -> Conversation:
    """修改标题或状态（开发文档 §7.5）。

    status 只允许改成 active / archived：paused 是危机中断后由风控流程设置的，
    不能让客户端自己把会话标成"已暂停"或从暂停里解出来。
    """
    conversation = get_owned(conversation_id, user_id)

    if title is not None:
        clean = title.strip()
        if not clean:
            raise ApiError(ErrorCode.INVALID_PARAM, "标题不能为空")
        if len(clean) > TITLE_MAX:
            raise ApiError(ErrorCode.INVALID_PARAM, f"标题不能超过 {TITLE_MAX} 个字符")
        conversation.title = clean

    if status is not None:
        if status not in EDITABLE_STATUS:
            raise ApiError(
                ErrorCode.INVALID_PARAM,
                f"status 只能是 {' 或 '.join(sorted(EDITABLE_STATUS))}",
            )
        conversation.status = status

    conversation.updated_at = utcnow()
    db.session.commit()
    return conversation


def soft_delete_conversation(conversation_id: int, user_id: int) -> None:
    """软删除：只写 deleted_at，不真的删行。

    为什么不物理删除：危机事件、审计日志都还引用着这个会话，
    真删会破坏这些记录的可追溯性（开发文档 §5.3）。

    时间用 core.clock.utcnow()，与库里其它时间字段保持同一口径（朴素 UTC）。
    """
    conversation = get_owned(conversation_id, user_id)
    conversation.deleted_at = utcnow()
    db.session.commit()


def resume_conversation(conversation_id: int, user_id: int) -> Conversation:
    """解除危机锁定：paused → active。

    只改状态，**不删除危机事件**——那次中断是一条安全记录，
    用户确认安全不代表事件没发生过，后台仍需要能看到它并复核。
    解锁动作本身由调用方写审计日志。
    """
    conversation = get_owned(conversation_id, user_id)
    conversation.status = STATUS_ACTIVE
    # crisis_level 保留：它记录了上次中断的等级，后台统计要用
    conversation.updated_at = utcnow()
    db.session.add(
        AuditLog(
            actor_id=user_id,
            action=ACTION_RESUME_CONVERSATION,
            target_type="conversation",
            target_id=conversation.id,
            request_id=getattr(g, "request_id", None),
        )
    )
    db.session.commit()
    return conversation


# ---------------------------------------------------------------------------
# 消息
# ---------------------------------------------------------------------------


def list_messages(
    conversation_id: int,
    user_id: int,
    page: int | None = None,
    size: int | None = None,
) -> dict[str, Any]:
    """列出会话内的消息。

    倒序返回（新的在前），由前端翻转成正序展示——开发文档 §7.5 约定的。

    页码与每页条数必须来自查询参数。写死 page=2 这类常量是最隐蔽的 bug：
    接口"能用"，但永远只返回第 2 页，而分页越大越容易一直 404
    （Flask-SQLAlchemy 在页码越界时默认抛 404）。
    """
    conversation = get_owned(conversation_id, user_id)
    page_no, page_size = _paging(page, size or 50)

    query = (
        Message.query.filter(Message.conversation_id == conversation.id)
        .order_by(Message.id.desc())
    )
    return _paginated(query, page_no, page_size, lambda m: m.to_dict())


def append_user_message(
    conversation_id: int,
    user_id: int,
    text: str,
    client_msg_id: str | None = None,
) -> tuple[Message, bool]:
    """写入一条用户消息，返回 (消息, 是否新建)。

    **幂等**是这里的核心：前端在网络抖动时会重发同一条消息，
    靠 `(conversation_id, client_msg_id)` 唯一索引 + 先查后写来保证
    数据库里只有一条。

    并发下仍然可能两个请求同时通过"先查"这一步，所以还要 catch
    IntegrityError 再回查一次——唯一索引是最终防线，代码里的检查只是
    为了给出更友好的响应。
    """
    conversation = get_owned(conversation_id, user_id)

    if conversation.status == STATUS_PAUSED:
        raise ApiError(ErrorCode.CONVERSATION_PAUSED)

    content = (text or "").strip()
    if not content:
        raise ApiError(ErrorCode.INVALID_PARAM, "消息内容不能为空")
    if len(content) > TEXT_MAX:
        raise ApiError(
            ErrorCode.INVALID_PARAM, f"消息长度需在 1-{TEXT_MAX} 字符之间"
        )

    if client_msg_id:
        existing = _find_by_client_id(conversation.id, client_msg_id)
        if existing is not None:
            return existing, False

    message = Message(
        conversation_id=conversation.id,
        role=ROLE_USER,
        content=content,
        client_msg_id=client_msg_id,
    )
    try:
        db.session.add(message)
        # 会话列表按 updated_at 倒序，发消息后应当冒到最前面
        conversation.updated_at = utcnow()
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = _find_by_client_id(conversation.id, client_msg_id)
        if existing is None:
            raise ApiError(ErrorCode.INTERNAL_ERROR, "消息保存失败", 500) from None
        return existing, False

    return message, True


def _find_by_client_id(conversation_id: int, client_msg_id: str) -> Message | None:
    return Message.query.filter_by(
        conversation_id=conversation_id,
        client_msg_id=client_msg_id,
    ).one_or_none()

