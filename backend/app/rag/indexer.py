"""向量入库与同步（开发文档 §8.4）。

**SQLite 的 knowledge_chunks 与 Chroma 的向量必须成对增删。**
只删一边的后果不会立刻暴露，但会在检索时以"引用了不存在的分块"
或"永远搜不到刚上传的文档"这种很难查的形式出现。

底层走 app/rag/chroma_http.py 里的极简客户端，原因见那个文件的说明。
"""

from __future__ import annotations

import logging

from flask import current_app

from app.rag.chroma_http import ChromaError, ChromaHTTP

logger = logging.getLogger(__name__)


def get_client() -> ChromaHTTP:
    """按配置构造客户端。

    CHROMA_HOST 在宿主机跑后端时必须填 localhost——
    compose 里的服务名 `chroma` 只在 Docker 网络内部能解析。
    """
    host = (current_app.config.get("CHROMA_HOST") or "").strip()
    if not host:
        raise ChromaError(
            "CHROMA_HOST 未配置。本项目只用 HTTP 模式（内嵌模式需要完整的 chromadb 包，"
            "而它与服务端存在 API 版本不匹配问题）。请设置 CHROMA_HOST/CHROMA_PORT。"
        )
    return ChromaHTTP(host=host, port=int(current_app.config["CHROMA_PORT"]))


def collection_id() -> str:
    return get_client().get_or_create_collection(
        name=current_app.config["CHROMA_COLLECTION"],
        metadata={"hnsw:space": "cosine"},
    )


def upsert_chunks(document_id: int, version: int, chunks: list, vectors: list) -> list[str]:
    """写入向量。向量 id 形如 `doc{id}-v{version}-c{seq}`。

    用 upsert 而不是 add：重建索引时会用同样的 id 重写，
    幂等让"重跑一次入库"变得安全。
    """
    if len(chunks) != len(vectors):
        raise ValueError(f"分块数（{len(chunks)}）与向量数（{len(vectors)}）不一致")
    if not chunks:
        return []

    client = get_client()
    cid = client.get_or_create_collection(
        name=current_app.config["CHROMA_COLLECTION"],
        metadata={"hnsw:space": "cosine"},
    )
    ids = [f"doc{document_id}-v{version}-c{c.seq}" for c in chunks]
    client.upsert(
        collection_id=cid,
        ids=ids,
        embeddings=vectors,
        documents=[c.content for c in chunks],
        metadatas=[
            {
                "document_id": document_id,
                "chunk_id": c.db_id if c.db_id is not None else -1,
                "seq": c.seq,
                "version": version,
                "is_active": True,
                "sensitivity": c.sensitivity or "internal",
                "page": c.page or 0,
                "title": c.title or "",
                "section_path": c.section_path or "",
                "tags": ",".join(c.tags or []),
            }
            for c in chunks
        ],
    )
    return ids


def delete_document_vectors(document_id: int) -> int:
    """按 document_id 删除该文档的全部向量，返回删除前的条数。

    先取一次再删：这个数字要写进日志，删错了至少能看出规模异常。
    """
    client = get_client()
    cid = client.get_or_create_collection(name=current_app.config["CHROMA_COLLECTION"])
    existing = client.get(collection_id=cid, where={"document_id": document_id}, include=[])
    count = len(existing.get("ids") or [])
    if count:
        client.delete(collection_id=cid, where={"document_id": document_id})
    return count


def count_chunks(document_id: int | None = None) -> int:
    """统计向量条数。传 document_id 则只统计该文档。"""
    client = get_client()
    cid = client.get_or_create_collection(name=current_app.config["CHROMA_COLLECTION"])
    if document_id is None:
        return client.count(cid)
    result = client.get(collection_id=cid, where={"document_id": document_id}, include=[])
    return len(result.get("ids") or [])


def search(
    query_embedding: list[float],
    top_k: int,
    where: dict | None = None,
) -> list[dict]:
    """向量召回。返回扁平的命中列表，字段已经拍平，调用方不用再拆嵌套列表。"""
    client = get_client()
    cid = client.get_or_create_collection(name=current_app.config["CHROMA_COLLECTION"])
    result = client.query(
        collection_id=cid,
        query_embedding=query_embedding,
        n_results=top_k,
        where=where or {"is_active": True},
        include=["documents", "metadatas", "distances"],
    )

    ids = (result.get("ids") or [[]])[0]
    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    hits: list[dict] = []
    for position, vector_id in enumerate(ids):
        meta = metadatas[position] if position < len(metadatas) else {}
        hits.append(
            {
                "vector_id": vector_id,
                "content": documents[position] if position < len(documents) else "",
                "metadata": meta or {},
                # cosine 距离 → 相似度，便于日志与前端展示
                "similarity": 1.0 - float(distances[position]) if position < len(distances) else 0.0,
            }
        )
    return hits

