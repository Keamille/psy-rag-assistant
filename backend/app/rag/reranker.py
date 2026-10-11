"""重排（开发文档 §8.6）：BAAI/bge-reranker-v2-m3（Cross-Encoder）。

**为什么需要重排，以及为什么只能对少量候选做**

向量检索是「双塔」结构：query 和文档各自编码成向量，再算相似度。
两者的编码过程互不知情，所以精度有天花板。

Cross-Encoder 把 (query, 文档) 拼在一起送进模型，让它们在注意力层里
直接交互——精度明显更高，但代价是**每一对都要跑一次完整前向**。
20 对候选就是 20 次推理；如果把 400 个分块全拿来重排，延迟会高到不可接受。

所以标准做法是两阶段：先廉价召回一批（我们取 20），再精细重排取前 5。
召回负责"不漏"，重排负责"排准"。

**全部低于阈值时返回空列表**，而不是"矮子里挑高个"。
这是刻意的：宁可让系统说"知识库里没有相关内容"，也不要拿一段不相关的资料
硬凑出回答。后者在心理场景里的伤害远大于前者。
"""

from __future__ import annotations

import logging
import threading

from flask import current_app

from app.rag.retriever import Candidate

logger = logging.getLogger(__name__)

_reranker = None
_load_lock = threading.Lock()


def is_enabled() -> bool:
    return bool(current_app.config.get("RERANK_ENABLED"))


def get_reranker():
    """惰性加载，进程内单例。加锁避免多线程重复加载。"""
    global _reranker
    if _reranker is not None:
        return _reranker
    with _load_lock:
        if _reranker is not None:
            return _reranker
        from FlagEmbedding import FlagReranker

        model_name = current_app.config["RERANK_MODEL"]
        max_length = int(current_app.config.get("RERANK_MAX_LENGTH", 384))
        logger.info("加载重排模型 %s（max_length=%d）", model_name, max_length)
        # CPU 上不用 fp16：Windows 的 CPU 推理对 fp16 支持不完整，反而更慢
        _reranker = FlagReranker(model_name, use_fp16=False, max_length=max_length)
        return _reranker


def is_loaded() -> bool:
    return _reranker is not None


def rerank(query: str, candidates: list[Candidate], top_k: int = 5) -> list[Candidate]:
    """对候选重排。关闭重排时直接截断，返回结构保持一致。"""
    if not candidates:
        return []
    if not is_enabled():
        return candidates[:top_k]

    # 先按上限截断再重排。Cross-Encoder 的成本与候选数成正比，
    # 而 RRF 已经把它们按相关性排过序了，砍掉尾部的代价很小。
    limit = int(current_app.config.get("RERANK_MAX_CANDIDATES", 10))
    candidates = candidates[:limit]

    try:
        model = get_reranker()
        scores = model.compute_score(
            [[query, candidate.content] for candidate in candidates],
            normalize=True,
        )
    except Exception as exc:  # noqa: BLE001
        # 重排失败时退回 RRF 顺序：宁可用次优排序，也不要整个问答挂掉
        logger.warning("重排失败，回退到 RRF 顺序：%s", exc)
        return candidates[:top_k]

    # compute_score 单条输入时返回标量，统一成列表
    if isinstance(scores, (int, float)):
        scores = [scores]

    threshold = float(current_app.config["RERANK_MIN_SCORE"])
    ranked = sorted(zip(candidates, scores), key=lambda pair: pair[1], reverse=True)
    kept = [candidate.with_score(float(score)) for candidate, score in ranked if score >= threshold]

    if not kept:
        logger.info("全部候选低于阈值 %.2f，判定为知识库无相关内容", threshold)
    return kept[:top_k]

