"""记忆与上下文预算（开发文档 §9）。

两级记忆：
  短期 —— 最近若干轮原文，保证"刚才说了什么"完全准确；
  长期 —— 更早内容的滚动摘要，保证"一个月前聊过什么"还能被想起。

两者都要，只留其一都会有明显缺陷：只有短期，长对话会遗忘；
只有摘要，最近几轮的细节会被压缩得不准确，而心理支持恰恰最依赖细节。

**摘要放在 `done` 事件之后同步执行，而非异步队列**（开发文档 §9.2 写的是异步）：
异步会留下一个尴尬窗口——用户看完回答紧接着追问，此时摘要还没生成完，
下一轮用不到它，等于白做。而 `done` 之后回答已完整显示，多等一两秒无体感损失。
"""

from __future__ import annotations

import logging

from flask import current_app

from app.core.errors import ApiError
from app.extensions import db
from app.models import ConversationSummary, Message
from app.rag import prompt as prompt_module

logger = logging.getLogger(__name__)

# 预算（token）。中文粗略按 1 字 ≈ 1 token 估算——不精确，但预算本来就是
# 留余量的保守估计，不需要精确到 token 级别。
SUMMARY_BUDGET = 400
RECENT_BUDGET = 1800
MAX_RECENT_TURNS = 12  # 6 轮问答 = 12 条消息
MIN_KEEP_TURNS = 4  # 无论如何保留最近 2 轮（4 条）
SUMMARY_TRIGGER_MESSAGES = 12


def _estimate_tokens(text: str) -> int:
    return len(text or "")


class MemoryService:
    def __init__(self, settings=None) -> None:  # noqa: ANN001
        self.settings = settings or current_app.config

    # ------------------------------------------------------------------
    # 读
    # ------------------------------------------------------------------

    def build_context(self, conversation) -> dict:  # noqa: ANN001
        """返回 {"summary": str|None, "recent_turns": [...]}，已按预算裁剪。"""
        summary_row = ConversationSummary.query.filter_by(
            conversation_id=conversation.id
        ).one_or_none()

        messages = (
            Message.query.filter(
                Message.conversation_id == conversation.id,
                Message.role.in_(("user", "assistant")),
            )
            .order_by(Message.id.desc())
            .limit(40)
            .all()
        )
        messages.reverse()  # 取回后恢复时间正序

        # 摘要已覆盖的部分不再以原文重复进上下文
        if summary_row is not None:
            messages = [m for m in messages if m.id > summary_row.covered_until_message_id]

        recent = self._trim_recent(messages)
        summary = self._trim_summary(summary_row.summary_text if summary_row else None)

        return {
            "summary": summary,
            "recent_turns": [{"role": m.role, "content": m.content} for m in recent],
        }

    def _trim_recent(self, messages: list) -> list:
        """按预算裁剪最近对话。

        裁剪顺序（开发文档 §9.1）：从最旧的开始丢，但至少保留最近 2 轮。
        "至少保留 2 轮"是有意的下限：只留 1 轮的话，模型看不到对话走向，
        回答会变得像在回答一个孤立的问题。
        """
        recent = messages[-MAX_RECENT_TURNS:]
        kept: list = []
        used = 0
        for message in reversed(recent):
            cost = _estimate_tokens(message.content)
            if kept and used + cost > RECENT_BUDGET and len(kept) >= MIN_KEEP_TURNS:
                break
            kept.append(message)
            used += cost
        kept.reverse()
        return kept

    @staticmethod
    def _trim_summary(summary: str | None) -> str | None:
        if not summary:
            return None
        if _estimate_tokens(summary) <= SUMMARY_BUDGET:
            return summary
        # 摘要超预算时保留前段——结构化摘要把"主要困扰/情绪主题"放在最前面，
        # 那是最重要的部分
        return summary[:SUMMARY_BUDGET] + "……"

    # ------------------------------------------------------------------
    # 写
    # ------------------------------------------------------------------

    def needs_summary(self, conversation) -> bool:  # noqa: ANN001
        """消息数超过阈值，且确有未被摘要覆盖的内容时才需要刷新。"""
        total = Message.query.filter(
            Message.conversation_id == conversation.id,
            Message.role.in_(("user", "assistant")),
        ).count()
        if total <= SUMMARY_TRIGGER_MESSAGES:
            return False

        summary_row = ConversationSummary.query.filter_by(
            conversation_id=conversation.id
        ).one_or_none()
        if summary_row is None:
            return True
        # 未覆盖的消息超过一轮问答，才值得再跑一次摘要
        uncovered = Message.query.filter(
            Message.conversation_id == conversation.id,
            Message.id > summary_row.covered_until_message_id,
        ).count()
        return uncovered > 4

    def refresh_summary(self, conversation, llm) -> bool:  # noqa: ANN001
        """滚动压缩摘要。失败不抛异常——摘要不是关键路径。"""
        row = ConversationSummary.query.filter_by(
            conversation_id=conversation.id
        ).one_or_none()
        since_id = row.covered_until_message_id if row else 0

        pending = (
            Message.query.filter(
                Message.conversation_id == conversation.id,
                Message.id > since_id,
                Message.role.in_(("user", "assistant")),
            )
            .order_by(Message.id.asc())
            .all()
        )
        # 至少留最近两条不进摘要，避免把"刚说的话"过早抽象掉
        if len(pending) <= 2:
            return False
        to_compress = pending[:-2]

        previous = (
            f"（此前的摘要，请在它的基础上继续压缩）\n{row.summary_text}"
            if row
            else "（此前没有摘要）"
        )
        new_messages = "\n".join(
            f"{'用户' if m.role == 'user' else '助手'}：{m.content}" for m in to_compress
        )

        try:
            text = llm.complete_json(
                prompt_module.SUMMARY_PROMPT.format(
                    previous_summary=previous, new_messages=new_messages
                ),
                temperature=0.0,
                timeout=60,
                max_tokens=400,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("摘要生成失败，跳过本次刷新：%s", exc)
            return False

        text = (text or "").strip()
        if not text:
            return False

        covered_until = to_compress[-1].id
        if row is None:
            row = ConversationSummary(
                conversation_id=conversation.id,
                summary_text=text,
                covered_until_message_id=covered_until,
            )
            db.session.add(row)
        else:
            row.summary_text = text
            row.covered_until_message_id = covered_until
        db.session.commit()
        return True


def build_context(conversation) -> dict:  # noqa: ANN001
    return MemoryService().build_context(conversation)


def needs_summary(conversation) -> bool:  # noqa: ANN001
    return MemoryService().needs_summary(conversation)


def refresh_summary(conversation, llm) -> bool:  # noqa: ANN001
    return MemoryService().refresh_summary(conversation, llm)


__all__ = [
    "MemoryService",
    "build_context",
    "needs_summary",
    "refresh_summary",
    "ApiError",
]

