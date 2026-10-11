"""知识库切块（开发文档 §5.2）。

与 Chroma 中的向量**一一对应**：`chroma_id` 就是向量库里的主键。
删除文档时，业务表与向量库必须成对清理，只删一边会造成脏数据。
"""

from __future__ import annotations

from typing import Any

from app.extensions import db


class KnowledgeChunk(db.Model):
    __tablename__ = "knowledge_chunks"

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(
        db.Integer,
        db.ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    seq = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=False)
    section_path = db.Column(db.String(255), nullable=True)
    page = db.Column(db.Integer, nullable=True)
    token_count = db.Column(db.Integer, nullable=True)
    chroma_id = db.Column(db.String(64), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, server_default=db.true())

    __table_args__ = (
        db.Index("idx_chunk_doc", "document_id", "seq"),
        db.Index("uk_chunk_chroma", "chroma_id", unique=True),
    )

    def to_dict(self, with_content: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "document_id": self.document_id,
            "seq": self.seq,
            "section_path": self.section_path,
            "page": self.page,
            "token_count": self.token_count,
            "chroma_id": self.chroma_id,
            "is_active": self.is_active,
        }
        if with_content:
            payload["content"] = self.content
        return payload

    def __repr__(self) -> str:  # pragma: no cover
        return f"<KnowledgeChunk {self.id} doc={self.document_id} seq={self.seq}>"

