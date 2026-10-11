"""会话长期摘要（开发文档 §5.2）。

一个会话一行，滚动更新：`covered_until_message_id` 表示摘要已覆盖到哪条消息，
它之后的消息仍以原文进入上下文。
"""

from __future__ import annotations

from typing import Any

from app.extensions import db


class ConversationSummary(db.Model):
    __tablename__ = "conversation_summaries"

    # 一会话一行，会话主键直接作为本表主键
    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey("conversations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    summary_text = db.Column(db.Text, nullable=False)
    covered_until_message_id = db.Column(db.Integer, nullable=False)
    emotion_tags = db.Column(db.String(255), nullable=True)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "summary_text": self.summary_text,
            "covered_until_message_id": self.covered_until_message_id,
            "emotion_tags": self.emotion_tags,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ConversationSummary conv={self.conversation_id}>"

