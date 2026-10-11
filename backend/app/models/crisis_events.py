"""危机事件（开发文档 §5.2）。

设计约定：
- 只增不改（复核相关字段除外）——它是安全审计记录，不是可变业务数据
- `snippet` 只保留命中句前后各 60 字，避免把整段对话留痕
"""

from __future__ import annotations

from typing import Any

from app.extensions import db

LEVEL_MEDIUM = "medium"
LEVEL_HIGH = "high"

SOURCE_RULE = "rule"
SOURCE_MODEL = "model"
SOURCE_BOTH = "both"

ACTION_INTERRUPTED = "interrupted"
ACTION_WARNED_AND_CONTINUED = "warned_and_continued"

FOLLOW_UP_PENDING = "pending"
FOLLOW_UP_CONTACTED = "contacted"
FOLLOW_UP_CLOSED = "closed"


class CrisisEvent(db.Model):
    __tablename__ = "crisis_events"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    conversation_id = db.Column(
        db.Integer, db.ForeignKey("conversations.id"), nullable=False
    )
    message_id = db.Column(db.Integer, db.ForeignKey("messages.id"), nullable=True)
    level = db.Column(db.String(16), nullable=False)
    source = db.Column(db.String(16), nullable=False)
    matched_terms = db.Column(db.String(255), nullable=True)
    snippet = db.Column(db.Text, nullable=True)
    action_taken = db.Column(db.String(32), nullable=False)
    reviewed = db.Column(db.Boolean, nullable=False, server_default=db.false())
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    follow_up_status = db.Column(db.String(32), nullable=True)
    review_note = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, server_default=db.func.current_timestamp()
    )

    __table_args__ = (
        # 后台默认视图：按等级筛选、按时间倒序
        db.Index("idx_crisis_level_time", "level", db.text("created_at DESC")),
        # 每日值班待办：未复核的事件
        db.Index("idx_crisis_reviewed", "reviewed", db.text("created_at DESC")),
    )

    def to_dict(self, with_snippet: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "message_id": self.message_id,
            "level": self.level,
            "source": self.source,
            "matched_terms": self.matched_terms,
            "action_taken": self.action_taken,
            "reviewed": self.reviewed,
            "follow_up_status": self.follow_up_status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if with_snippet:
            payload["snippet"] = self.snippet
            payload["review_note"] = self.review_note
        return payload

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CrisisEvent {self.id} level={self.level} user={self.user_id}>"

