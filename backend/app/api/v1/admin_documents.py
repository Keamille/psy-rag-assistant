"""知识库文档管理接口（开发文档 §7.7）。权限：admin。"""

from __future__ import annotations

import os
import uuid

from flask import Blueprint, current_app, g, request

from app.core.errors import ApiError, ErrorCode
from app.core.rate_limit import enforce_upload_rate
from app.core.response import ok, paginated
from app.core.security import admin_required
from app.extensions import db
from app.models import KnowledgeChunk, KnowledgeDocument
from app.rag.indexer import count_chunks
from app.services import document_service

bp = Blueprint("admin_documents", __name__)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".md", ".txt"}


def _safe_filename(original: str) -> str:
    """生成安全的落盘文件名。

    保留原名可读性便于人工排查，但必须加随机前缀——否则两个同名文件
    会互相覆盖，而且用户可以通过 `../` 之类构造路径穿越。
    original 只取 basename，杜绝 `../../etc/passwd` 这类输入。
    """
    base = os.path.basename(original).strip() or "unnamed"
    return f"{uuid.uuid4().hex[:8]}_{base}"


@bp.post("")
@admin_required
def upload_document():
    """multipart/form-data: file(必填) / title / tags / sensitivity。"""
    enforce_upload_rate(int(getattr(g, "current_user_id", 0)))

    if "file" not in request.files:
        raise ApiError(ErrorCode.INVALID_PARAM, "缺少 file 字段")

    uploaded = request.files["file"]
    filename = (uploaded.filename or "").strip()
    if not filename:
        raise ApiError(ErrorCode.INVALID_PARAM, "文件名为空")

    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise ApiError(
            ErrorCode.UPLOAD_REJECTED,
            f"仅支持 {'/'.join(sorted(ALLOWED_EXTENSIONS))}，当前为 {ext or '未知类型'}",
        )

    stored_name = _safe_filename(filename)
    path = os.path.join(document_service.upload_dir(), stored_name)
    uploaded.save(path)

    document, created = document_service.create_document(
        filename=stored_name,
        title=request.form.get("title") or filename,
        source_type=ext.lstrip("."),
        uploaded_by=int(g.current_user_id),
    )

    if not created:
        # 命中 file_hash 去重。此时刚落盘的那份是多余的，删掉避免堆积。
        if os.path.exists(path) and document.filename != stored_name:
            os.remove(path)
        return ok(
            data={
                "document_id": document.id,
                "task_id": None,
                "status": document.status,
                "deduplicated": True,
                "message": "同一份文件已存在，直接复用已有文档",
            }
        )

    task_id = document_service.dispatch_ingest(document.id)
    return ok(
        data={
            "document_id": document.id,
            "task_id": task_id,
            "status": "pending",
            "deduplicated": False,
        }
    )


@bp.get("")
@admin_required
def list_documents():
    page = max(request.args.get("page", 1, type=int), 1)
    size = min(max(request.args.get("size", 20, type=int), 1), current_app.config["MAX_PAGE_SIZE"])

    rows = document_service.list_documents(
        status=request.args.get("status"), q=request.args.get("q")
    )
    total = len(rows)
    window = rows[(page - 1) * size: page * size]
    return ok(data=paginated([d.to_dict() for d in window], page, size, total))


@bp.get("/<int:document_id>")
@admin_required
def get_document(document_id: int):
    document = db.session.get(KnowledgeDocument, document_id)
    if document is None:
        raise ApiError(ErrorCode.DOC_PARSE_FAILED, "文档不存在", 404)
    payload = document.to_dict()
    payload["vector_count"] = count_chunks(document_id)
    return ok(data=payload)


@bp.get("/<int:document_id>/chunks")
@admin_required
def list_chunks(document_id: int):
    document = db.session.get(KnowledgeDocument, document_id)
    if document is None:
        raise ApiError(ErrorCode.DOC_PARSE_FAILED, "文档不存在", 404)

    page = max(request.args.get("page", 1, type=int), 1)
    size = min(max(request.args.get("size", 20, type=int), 1), current_app.config["MAX_PAGE_SIZE"])
    query = (
        KnowledgeChunk.query.filter_by(document_id=document_id)
        .order_by(KnowledgeChunk.seq.asc())
    )
    pagination = query.paginate(page=page, per_page=size, error_out=False)
    return ok(
        data=paginated(
            [c.to_dict() for c in pagination.items], pagination.page, pagination.per_page, pagination.total
        )
    )


@bp.post("/<int:document_id>/reindex")
@admin_required
def reindex_document(document_id: int):
    task_id = document_service.reindex(document_id)
    return ok(data={"document_id": document_id, "task_id": task_id})


@bp.delete("/<int:document_id>")
@admin_required
def delete_document(document_id: int):
    return ok(data=document_service.delete_document(document_id))

