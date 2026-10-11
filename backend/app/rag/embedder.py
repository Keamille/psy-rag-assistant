"""文本向量化（开发文档 §8.3）。模型：BAAI/bge-m3，1024 维，cosine 距离。

**为什么 query 要加前缀、文档块不加**

bge 系列是「非对称检索」模型：训练时 query 侧带了指令前缀、文档侧不带。
推理时保持一致才能对上训练分布。加了前缀 query 和文档就在同一个语义空间里；
不加则 query 的向量会系统性偏移，检索质量明显下降。
这是 bge 特有的约定，换成别的模型（如 m3e、text-embedding-3）就不需要。

**为什么要 L2 归一化**

归一化后余弦相似度退化成点积，省掉一次开方与除法；更重要的是，
Chroma 用 cosine 距离时如果向量没归一化，距离排序会失真。
"""

from __future__ import annotations

import logging
import threading
import time

from flask import current_app

logger = logging.getLogger(__name__)

QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："

_model = None
_load_lock = threading.Lock()


def get_model():
    """惰性加载，进程内单例。

    加锁是必要的：web 进程用 gthread 多线程，若两个线程同时首次请求，
    会各自加载一份 2GB 权重，内存直接翻倍。
    """
    global _model
    if _model is not None:
        return _model

    with _load_lock:
        if _model is not None:
            return _model
        from sentence_transformers import SentenceTransformer

        model_name = current_app.config["EMBEDDING_MODEL"]
        device = current_app.config["EMBEDDING_DEVICE"]
        started = time.time()
        logger.info("加载向量化模型 %s（device=%s）", model_name, device)
        _model = SentenceTransformer(model_name, device=device)
        # bge-m3 支持 8192，但 1024 已足够覆盖我们的块长，且省内存
        _model.max_seq_length = 1024
        _model.eval()
        logger.info("向量化模型加载完成，用时 %.1fs", time.time() - started)
        return _model


def warmup() -> None:
    """预热：启动时调用，把首次请求的加载耗时挪到启动阶段。"""
    get_model()
    embed_query("预热")


def is_loaded() -> bool:
    return _model is not None


def embed_documents(texts: list[str]) -> list[list[float]]:
    """批量向量化文档块。不加前缀，返回已归一化的向量。"""
    if not texts:
        return []
    model = get_model()
    batch_size = int(current_app.config.get("EMBEDDING_BATCH_SIZE", 16))
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return vectors.tolist()


def embed_query(text: str) -> list[float]:
    """向量化检索问题。**必须加前缀**，见文件头部说明。"""
    model = get_model()
    vector = model.encode(
        QUERY_PREFIX + (text or ""),
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return vector.tolist()

