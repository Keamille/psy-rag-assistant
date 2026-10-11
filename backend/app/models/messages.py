"""消息表（开发文档 §5.2）。

`(conversation_id, client_msg_id)` 的唯一索引实现**幂等**：
前端重发同一条消息时，数据库层面直接拒绝第二条。
"""

from __future__ import annotations

import json
from typing import Any

from app.extensions import db

ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_SYSTEM_CARD = "system_card"


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer, db.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role = db.Column(db.String(16), nullable=False)
    content = db.Column(db.Text, nullable=False)
    client_msg_id = db.Column(db.String(64), nullable=True)
    risk_level = db.Column(db.String(16), nullable=True)
    prompt_tokens = db.Column(db.Integer, nullable=True)
    completion_tokens = db.Column(db.Integer, nullable=True)
    latency_ms = db.Column(db.Integer, nullable=True)
    model = db.Column(db.String(64), nullable=True)
    sources_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, server_default=db.func.current_timestamp()
    )

    __table_args__ = (
        # 幂等的核心：同一个会话里 client_msg_id 不能重复
        db.Index(
            "uk_msg_client",
            "conversation_id",
            "client_msg_id",
            unique=True,
        ),
        db.Index("idx_msg_conv_created", "conversation_id", "created_at"),
    )

    @property
    def sources(self) -> list[dict]:
        if not self.sources_json:
            return []
        try:
            return json.loads(self.sources_json)
        except (TypeError, ValueError):
            return []

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "client_msg_id": self.client_msg_id,
            "risk_level": self.risk_level,
            "sources": self.sources,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Message {self.id} conv={self.conversation_id} role={self.role}>"
