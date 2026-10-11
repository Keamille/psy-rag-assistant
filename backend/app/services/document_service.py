"""知识库文档的状态机与入库编排（开发文档 §8.2 / §7.7）。

状态机：pending → processing → ready / failed

**为什么向量化必须离开 HTTP 请求**

一篇 50 页 PDF 的解析 + 向量化在 CPU 上要几十秒到几分钟。
如果放在上传请求里做，浏览器会超时、Gunicorn worker 会被长期占住，
并发几个上传就能把服务拖垮。所以上传接口只做"存文件 + 建记录 + 派任务"，
真正的活交给 RQ worker。

进度写进 Redis，供 `/admin/tasks/{task_id}` 查询。
"""

from __future__ import annotations

import hashlib
import logging
import os

from flask import current_app

from app.core.errors import ApiError, ErrorCode
from app.extensions import db, redis_store
from app.models import KnowledgeChunk, KnowledgeDocument
from app.models.knowledge_documents import (
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PROCESSING,
    STATUS_READY,
)
from app.rag import cleaner, embedder, indexer, loader, retriever, splitter

logger = logging.getLogger(__name__)

UPLOAD_DIR = "uploads"

# 与前端 accept 保持一致
ALLOWED_EXTENSIONS = {"pdf", "docx", "md", "txt"}


# ---------------------------------------------------------------------------
# 上传
# ---------------------------------------------------------------------------


def upload_dir() -> str:
    """上传原件的存放目录。容器里挂在 /data/uploads 下。"""
    instance = os.path.join(current_app.instance_path, UPLOAD_DIR)
    os.makedirs(instance, exist_ok=True)
    return instance


def compute_file_hash(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fp:
        for block in iter(lambda: fp.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_document(
    *,
    filename: str,
    title: str | None,
    source_type: str,
    uploaded_by: int,
    is_builtin: bool = False,
) -> tuple[KnowledgeDocument, bool]:
    """登记一篇文档，返回 (文档, 是否新建)。

    按 `file_hash` 去重：同一份文件重复上传直接复用已有记录。
    这不只是省事——重复入库会让同一段内容在检索结果里占多个名额，
    等于把检索的多样性挤掉。
    """
    path = os.path.join(upload_dir(), filename)
    file_hash = compute_file_hash(path) if os.path.exists(path) else None

    if file_hash:
        existing = KnowledgeDocument.query.filter_by(file_hash=file_hash).first()
        if existing is not None:
            logger.info("文件已存在（hash 相同），复用文档 %s", existing.id)
            return existing, False

    document = KnowledgeDocument(
        title=(title or filename).strip()[:200],
        source_type=source_type,
        filename=filename,
        file_hash=file_hash,
        status=STATUS_PENDING,
        is_builtin=is_builtin,
        uploaded_by=None if is_builtin else uploaded_by,
    )
    db.session.add(document)
    db.session.commit()
    return document, True


def dispatch_ingest(document_id: int) -> str:
    """把入库任务放进 RQ 队列，返回 task_id。

    Redis 不可用时**不派任务**，而是直接把文档标记为 failed 并说明原因——
    比"接口返回成功但文档永远停在 pending"要诚实得多。
    """
    from rq import Queue

    client = redis_store.client
    if client is None:
        _mark_failed(document_id, "任务队列不可用（Redis 未连接），无法派发入库任务")
        raise ApiError(
            ErrorCode.INTERNAL_ERROR,
            "任务队列不可用，文档已标记为失败，请确认 Redis 已启动",
            503,
        )

    # 预先定好 job_id 并作为 task_id 传给任务体：
    # 这样 worker 在运行过程中就能往同一个 key 写进度，前端轮询得到的
    # 才是"实时进度"而不是"完成后才有结果"。
    import uuid

    task_id = uuid.uuid4().hex
    queue = Queue("ingest", connection=client)
    queue.enqueue(
        "app.tasks.ingest_job.ingest_document",
        document_id,
        task_id,
        job_id=task_id,
        job_timeout=int(current_app.config.get("INGEST_TIMEOUT", 1800)),
    )
    _set_progress(task_id, {"task_id": task_id, "status": "queued", "progress": 0.0, "stage": "queued", "detail": {}, "error": None})
    return task_id


def reindex(document_id: int) -> str:
    """重建索引：清掉旧向量与旧分块，然后重新走一遍入库。

    version 加 1 而不是覆盖：向量 id 里带 version，新旧可以共存一小段时间，
    万一重建失败还能对照排查。
    """
    document = db.session.get(KnowledgeDocument, document_id)
    if document is None:
        raise ApiError(ErrorCode.DOC_PARSE_FAILED, "文档不存在", 404)

    indexer.delete_document_vectors(document_id)
    KnowledgeChunk.query.filter_by(document_id=document_id).delete()
    document.version += 1
    document.status = STATUS_PENDING
    document.error_message = None
    document.chunk_count = 0
    db.session.commit()
    retriever.bump_bm25_version()
    return dispatch_ingest(document_id)


def delete_document(document_id: int) -> dict:
    """删除文档、分块、向量与上传原件。

    四样都要删。少删一样就会出现"列表里没有了但检索还能搜到"这种脏状态，
    而且越晚发现越难定位。
    """
    document = db.session.get(KnowledgeDocument, document_id)
    if document is None:
        raise ApiError(ErrorCode.DOC_PARSE_FAILED, "文档不存在", 404)

    vector_count = indexer.delete_document_vectors(document_id)
    chunk_count = KnowledgeChunk.query.filter_by(document_id=document_id).delete()

    removed_file = False
    if document.filename:
        path = os.path.join(upload_dir(), document.filename)
        if os.path.exists(path):
            os.remove(path)
            removed_file = True

    db.session.delete(document)
    db.session.commit()
    retriever.bump_bm25_version()

    logger.info(
        "删除文档 %s：分块 %d、向量 %d、原件 %s",
        document_id, chunk_count, vector_count, removed_file,
    )
    return {
        "document_id": document_id,
        "deleted_chunks": chunk_count,
        "deleted_vectors": vector_count,
        "deleted_file": removed_file,
    }


# ---------------------------------------------------------------------------
# 入库执行（由 RQ worker 调用，也可以同步调用做测试）
# ---------------------------------------------------------------------------


def run_ingest(document_id: int, task_id: str | None = None) -> dict:
    """真正干活的地方。异常一律转成文档的 failed 状态，不向上抛。"""
    document = db.session.get(KnowledgeDocument, document_id)
    if document is None:
        raise ApiError(ErrorCode.DOC_PARSE_FAILED, f"文档 {document_id} 不存在", 404)

    document.status = STATUS_PROCESSING
    document.error_message = None
    db.session.commit()

    try:
        path = os.path.join(upload_dir(), document.filename or "")
        _progress(task_id, 0.05, "parsing")
        blocks = loader.load(path, document.source_type)

        _progress(task_id, 0.25, "cleaning")
        blocks = cleaner.clean(blocks)

        _progress(task_id, 0.40, "chunking")
        chunks = splitter.split_document(
            blocks,
            size=current_app.config["CHUNK_SIZE"],
            overlap=current_app.config["CHUNK_OVERLAP"],
            title=document.title,
            sensitivity="internal",
        )
        if not chunks:
            raise loader.ParseError("切分后没有产生任何内容块")

        # 先落业务表拿到 db_id，再写向量——两个 id 要互相对应
        KnowledgeChunk.query.filter_by(document_id=document_id).delete()
        for chunk in chunks:
            chunk.chroma_id = f"doc{document_id}-v{document.version}-c{chunk.seq}"
            row = KnowledgeChunk(
                document_id=document_id,
                seq=chunk.seq,
                content=chunk.content,
                section_path=chunk.section_path,
                page=chunk.page,
                token_count=len(chunk.content),
                chroma_id=chunk.chroma_id,
            )
            db.session.add(row)
            db.session.flush()
            chunk.db_id = row.id
        db.session.commit()

        _progress(task_id, 0.60, "embedding")
        vectors = embedder.embed_documents([c.content for c in chunks])

        _progress(task_id, 0.85, "indexing")
        indexer.delete_document_vectors(document_id)
        indexer.upsert_chunks(document_id, document.version, chunks, vectors)

        document.chunk_count = len(chunks)
        document.status = STATUS_READY
        document.error_message = None
        db.session.commit()

        # 让各进程知道 BM25 索引过期了
        retriever.bump_bm25_version()
        _progress(task_id, 1.0, "done", {"total_chunks": len(chunks)})

        logger.info("文档 %s 入库完成：%d 块", document_id, len(chunks))
        return {"document_id": document_id, "chunk_count": len(chunks)}

    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        _mark_failed(document_id, str(exc))
        _progress(task_id, 1.0, "failed", error=str(exc)[:300])
        logger.exception("文档 %s 入库失败", document_id)
        # 不向上抛：RQ 任务失败会重试，而解析失败重试多少次都一样
        return {"document_id": document_id, "error": str(exc)[:300]}


def _mark_failed(document_id: int, message: str) -> None:
    document = db.session.get(KnowledgeDocument, document_id)
    if document is None:
        return
    document.status = STATUS_FAILED
    document.error_message = message[:1000]
    db.session.commit()


# ---------------------------------------------------------------------------
# 任务进度
# ---------------------------------------------------------------------------


def _progress_key(task_id: str) -> str:
    return f"ingest:task:{task_id}"


def _set_progress(task_id: str, payload: dict) -> None:
    redis_store.set_json(_progress_key(task_id), payload, ttl=86400)


def _progress(
    task_id: str | None,
    value: float,
    stage: str,
    detail: dict | None = None,
    error: str | None = None,
) -> None:
    if not task_id:
        return
    payload = {
        "task_id": task_id,
        "status": "failed" if stage == "failed" else ("finished" if stage == "done" else "running"),
        "progress": value,
        "stage": stage,
        "detail": detail or {},
        "error": error,
    }
    _set_progress(task_id, payload)


def get_task(task_id: str) -> dict | None:
    return redis_store.get_json(_progress_key(task_id))


def list_documents(status: str | None = None, q: str | None = None) -> list[KnowledgeDocument]:
    query = KnowledgeDocument.query
    if status:
        query = query.filter(KnowledgeDocument.status == status)
    if q:
        query = query.filter(KnowledgeDocument.title.like(f"%{q}%"))
    return query.order_by(KnowledgeDocument.id.desc()).all()


def seed_base_knowledge() -> dict:
    """把 app/data/base_knowledge 下的内置语料入库。

    幂等：按文件名跳过已存在的，重复调用不会产生重复文档。
    """
    base = os.path.join(current_app.root_path, "data", "base_knowledge")
    if not os.path.isdir(base):
        return {"seeded": 0, "skipped": 0, "message": "内置语料目录不存在"}

    seeded, skipped = 0, 0
    for name in sorted(os.listdir(base)):
        if not name.endswith(".md"):
            continue
        exists = KnowledgeDocument.query.filter_by(filename=name, is_builtin=True).first()
        if exists is not None:
            skipped += 1
            continue

        target = os.path.join(upload_dir(), name)
        with open(os.path.join(base, name), encoding="utf-8") as src:
            content = src.read()
        with open(target, "w", encoding="utf-8") as dst:
            dst.write(content)

        document, created = create_document(
            filename=name,
            title=os.path.splitext(name)[0],
            source_type="md",
            uploaded_by=0,
            is_builtin=True,
        )
        if not created:
            skipped += 1
            continue
        # 内置语料直接同步入库：它们很小，而且首次启动就要能检索
        run_ingest(document.id)
        seeded += 1

    return {"seeded": seeded, "skipped": skipped}

