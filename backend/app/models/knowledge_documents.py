"""知识库文档（开发文档 §5.2）。

状态机：pending → processing → ready / failed
`file_hash` 用于去重：同一份文件重复上传直接返回已有记录。
"""

from __future__ import annotations

from typing import Any

from app.extensions import db

STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_READY = "ready"
STATUS_FAILED = "failed"

SOURCE_PDF = "pdf"
SOURCE_DOCX = "docx"
SOURCE_MD = "md"
SOURCE_TXT = "txt"
SOURCE_BUILTIN = "builtin"


class KnowledgeDocument(db.Model):
    __tablename__ = "knowledge_documents"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    source_type = db.Column(db.String(16), nullable=False)
    filename = db.Column(db.String(255), nullable=True)
    file_hash = db.Column(db.String(64), nullable=True)
    status = db.Column(db.String(16), nullable=False, server_default=db.text("'pending'"))
    error_message = db.Column(db.Text, nullable=True)
    chunk_count = db.Column(db.Integer, nullable=False, server_default=db.text("0"))
    version = db.Column(db.Integer, nullable=False, server_default=db.text("1"))
    is_builtin = db.Column(db.Boolean, nullable=False, server_default=db.false())
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, server_default=db.func.current_timestamp()
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )

    chunks = db.relationship(
        "KnowledgeChunk",
        backref="document",
        cascade="all, delete-orphan",
        order_by="KnowledgeChunk.seq",
    )

    __table_args__ = (
        db.Index("idx_doc_status", "status"),
        # 部分唯一索引：file_hash 非空时唯一。SQLite 与 PostgreSQL 都支持带条件的索引，
        # 其他方言（如 MySQL）不支持，会退化成普通索引。
        db.Index(
            "uk_doc_hash",
            "file_hash",
            unique=True,
            sqlite_where=db.text("file_hash IS NOT NULL"),
            postgresql_where=db.text("file_hash IS NOT NULL"),
        ),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "source_type": self.source_type,
            "filename": self.filename,
            "status": self.status,
            "error_message": self.error_message,
            "chunk_count": self.chunk_count,
            "version": self.version,
            "is_builtin": self.is_builtin,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<KnowledgeDocument {self.id} {self.title!r} status={self.status}>"

