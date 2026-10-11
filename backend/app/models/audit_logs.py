"""审计日志（开发文档 §5.2）。

红线：只记录"谁在什么时候对什么做了什么"，**不记录对话内容**。
"""

from __future__ import annotations

from typing import Any

from app.extensions import db

ACTION_LOGIN = "login"
ACTION_LOGOUT = "logout"
ACTION_CHANGE_PASSWORD = "change_password"
ACTION_EXPORT_DATA = "export_data"
ACTION_DELETE_DATA = "delete_data"
ACTION_RESUME_CONVERSATION = "resume_conversation"
ACTION_REVIEW_CRISIS = "review_crisis"
ACTION_UPDATE_CONFIG = "update_config"


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    # 不设外键：操作者可能已被删除，但审计记录必须留存
    actor_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(64), nullable=False)
    target_type = db.Column(db.String(32), nullable=True)
    target_id = db.Column(db.Integer, nullable=True)
    detail_json = db.Column(db.Text, nullable=True)
    request_id = db.Column(db.String(64), nullable=True)
    ip = db.Column(db.String(64), nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, server_default=db.func.current_timestamp()
    )

    __table_args__ = (
        db.Index("idx_audit_actor_time", "actor_id", db.text("created_at DESC")),
        db.Index("idx_audit_action_time", "action", db.text("created_at DESC")),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "actor_id": self.actor_id,
            "action": self.action,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "detail_json": self.detail_json,
            "request_id": self.request_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AuditLog {self.id} {self.action} actor={self.actor_id}>"

