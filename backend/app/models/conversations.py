"""会话表（开发文档 §5.2）。"""

from __future__ import annotations

from typing import Any

from app.extensions import db

STATUS_ACTIVE = "active"
STATUS_PAUSED = "paused"  # 危机中断后锁定，需用户确认安全才能恢复
STATUS_ARCHIVED = "archived"


class Conversation(db.Model):
    __tablename__ = "conversations"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title = db.Column(db.String(120), nullable=False, server_default=db.text("'新的对话'"))
    status = db.Column(db.String(16), nullable=False, server_default=db.text("'active'"))
    crisis_level = db.Column(db.String(16), nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, server_default=db.func.current_timestamp()
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )
    # 软删除：所有查询都必须带 deleted_at IS NULL
    deleted_at = db.Column(db.DateTime, nullable=True)

    messages = db.relationship(
        "Message",
        backref="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )

    __table_args__ = (
        # 会话列表按"最近更新"倒序，这个复合索引直接服务该查询
        db.Index(
            "idx_conv_user_updated",
            "user_id",
            "deleted_at",
            db.text("updated_at DESC"),
        ),
    )

    @property
    def is_paused(self) -> bool:
        return self.status == STATUS_PAUSED

    def to_dict(self, message_count: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "crisis_level": self.crisis_level,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if message_count is not None:
            payload["message_count"] = message_count
        return payload

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Conversation {self.id} user={self.user_id} status={self.status}>"
