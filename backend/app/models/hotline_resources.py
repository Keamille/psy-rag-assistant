"""求助资源（开发文档 §5.2）。

可由后台维护。`priority` 数值越小越靠前；120 / 110 这类紧急号码固定展示，
不参与常规排序。
"""

from __future__ import annotations

from typing import Any

from app.extensions import db


class HotlineResource(db.Model):
    __tablename__ = "hotline_resources"

    id = db.Column(db.Integer, primary_key=True)
    region = db.Column(db.String(16), nullable=False, server_default=db.text("'CN'"))
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(64), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    priority = db.Column(db.Integer, nullable=False, server_default=db.text("100"))
    is_active = db.Column(db.Boolean, nullable=False, server_default=db.true())

    __table_args__ = (db.Index("idx_hotline_region_priority", "region", "priority"),)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "region": self.region,
            "name": self.name,
            "phone": self.phone,
            "description": self.description,
            "priority": self.priority,
            "is_active": self.is_active,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<HotlineResource {self.name} {self.phone}>"

