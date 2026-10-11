"""用户表（开发文档 §5.2）。

字段约束的取舍说明：
- password_hash 用 VARCHAR(255)：argon2id 的哈希串约 97 字符，留足余量
- role / status 用 VARCHAR(16) 并给默认值：实际取值只有 user|admin、active|disabled
- last_login_at **可空且不设 onupdate**：它表示"上次登录时间"，只在登录成功时写；
  若加 onupdate，用户改个昵称也会把这个字段刷新，语义就错了
"""

from __future__ import annotations

from typing import Any

from app.extensions import db

ROLE_USER = "user"
ROLE_ADMIN = "admin"

STATUS_ACTIVE = "active"
STATUS_DISABLED = "disabled"


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True)
    username = db.Column(db.String(64), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(16), nullable=False, server_default=db.text("'user'"))
    status = db.Column(db.String(16), nullable=False, server_default=db.text("'active'"))
    consent_version = db.Column(db.String(16), nullable=False)
    consented_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(
        db.DateTime, nullable=False, server_default=db.func.current_timestamp()
    )
    last_login_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.Index("idx_users_role", "role"),
        db.Index("idx_users_status", "status"),
    )

    @property
    def is_active(self) -> bool:
        return self.status == STATUS_ACTIVE

    def to_dict(self, include_private: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
        }
        if include_private:
            payload.update(
                {
                    "status": self.status,
                    "consent_version": self.consent_version,
                    "consented_at": self.consented_at.isoformat() if self.consented_at else None,
                    "created_at": self.created_at.isoformat() if self.created_at else None,
                    "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
                }
            )
        return payload

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<User {self.id} {self.username} role={self.role} status={self.status}>"
