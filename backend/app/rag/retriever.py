"""混合检索（开发文档 §8.5）：向量召回 + BM25 召回 → RRF 融合。

**为什么必须混合**

单用向量检索会漏掉两类查询：
  - 专有名词与术语（"PHQ-9"、"CBT"、"5-4-3-2-1"）——向量模型对这些
    低频词的表示不稳定，而 BM25 靠精确词匹配，一打一个准；
  - 用户复述知识库里的原话——BM25 的直接命中比语义近似更可靠。

反过来，单用 BM25 会漏掉换了个说法的同义表达。两者互补，不是二选一。

**为什么用 RRF 而不是加权分数**

向量相似度在 0~1 之间，BM25 分数没有上界（可以到几十）。要加权就得先归一化，
而归一化系数在不同语料、不同查询上都会漂移，等于每换一批文档就要重新调参。
RRF 只用**排名**，`Σ 1/(k + rank)`，天然免疫量纲差异。
代价是丢掉了"第一名领先第二名多少"这个信息，但这个损失远小于调参的麻烦。
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

from flask import current_app

from app.extensions import db, redis_store
from app.rag import embedder

logger = logging.getLogger(__name__)

BM25_VERSION_KEY = "bm25:version"

# 中文停用词。只收极高频的功能词，不追求完备——
# 停用词表越长，误删实词的风险越高。
STOPWORDS = {
    "的", "了", "和", "是", "在", "我", "有", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "那", "什么", "怎么", "the", "a", "an",
    "of", "to", "and", "in", "is", "it", "that", "this",
}


@dataclass
class Candidate:
    chunk_id: int
    content: str
    title: str = ""
    section_path: str = ""
    page: int | None = None
    document_id: int | None = None
    score: float | None = None
    rank_vector: int | None = None
    rank_bm25: int | None = None
    metadata: dict = field(default_factory=dict)

    def with_score(self, score: float) -> "Candidate":
        self.score = score
        return self

    def to_payload(self, index: int) -> dict:
        """SSE sources 事件的单个引用对象（开发文档 §7.2 / §8.8）。"""
        return {
            "index": index,
            "document_title": self.title,
            "section_path": self.section_path,
            "page": self.page,
            # 展示原文片段而不是模型转述，用户才能自己核对
            "snippet": self.content[:300],
            "score": round(self.score, 4) if self.score is not None else None,
        }


# ---------------------------------------------------------------------------
# BM25 索引
# ---------------------------------------------------------------------------


class _BM25Index:
    """进程内 BM25 索引。

    为什么不用 Redis 缓存序列化好的索引：BM25 索引里存着全部分块的正文，
    序列化后体积比原表还大，而且反序列化（pickle）本身就慢。
    这个规模（几百到几千块）重建只要几十毫秒，直接在进程内重建更简单可靠。
    Redis 只用来存**版本号**，让其它进程知道索引过期了。
    """

    def __init__(self) -> None:
        self.version: int | None = None
        self.chunk_ids: list[int] = []
        self.bm25 = None

    def build(self) -> None:
        import jieba
        from rank_bm25 import BM25Okapi

        from app.models import KnowledgeChunk

        rows = (
            db.session.query(KnowledgeChunk.id, KnowledgeChunk.content)
            .filter(KnowledgeChunk.is_active.is_(True))
            .all()
        )
        self.chunk_ids = [row.id for row in rows]
        if not rows:
            self.bm25 = None
            self.version = _current_version()
            return

        tokenized = [_tokenize(row.content, jieba) for row in rows]
        self.bm25 = BM25Okapi(tokenized)
        self.version = _current_version()
        logger.info("BM25 索引重建完成：%d 个分块", len(rows))


_index = _BM25Index()
_index_lock = threading.Lock()


def _tokenize(text: str, jieba_module=None) -> list[str]:
    if jieba_module is None:
        import jieba as jieba_module  # type: ignore[no-redef]

    return [
        token
        for token in jieba_module.lcut_for_search(text or "")
        if token.strip() and token not in STOPWORDS
    ]


def _current_version() -> int:
    """从 Redis 读索引版本号。Redis 不可用时返回 0（相当于永不失效）。"""
    value = redis_store.get_json(BM25_VERSION_KEY)
    if isinstance(value, int):
        return value
    return 0


def bump_bm25_version() -> None:
    """文档入库/删除后调用，通知各进程重建索引。"""
    current = _current_version()
    redis_store.set_json(BM25_VERSION_KEY, current + 1)


def warmup_bm25(app=None) -> None:  # noqa: ANN001
    """启动时预热。失败不阻断启动——检索时会懒加载重建。"""
    try:
        _ensure_index()
    except Exception as exc:  # noqa: BLE001
        logger.warning("BM25 预热失败（将在首次检索时重建）：%s", exc)


def _ensure_index() -> _BM25Index:
    if _index.bm25 is None or _index.version != _current_version():
        with _index_lock:
            if _index.bm25 is None or _index.version != _current_version():
                _index.build()
    return _index


# ---------------------------------------------------------------------------
# 融合与检索
# ---------------------------------------------------------------------------


def rrf_fuse(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    """倒数排名融合。

    rankings 是每路的 chunk_id 有序列表（最相关在前）。
    k 起平滑作用：k 越大，靠前与靠后的名次差异被压得越平；
    k 越小，头部名次越重要。60 是论文里的常用默认值。
    """
    scores: dict[int, float] = {}
    for ranking in rankings:
        for position, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + position)
    return dict(sorted(scores.items(), key=lambda item: item[1], reverse=True))


def hybrid_search(query: str, top_k: int = 20) -> list[Candidate]:
    """混合召回 + RRF 融合，返回融合后的候选（尚未重排）。"""
    from app.rag import indexer

    vector_ids: list[int] = []
    try:
        hits = indexer.search(
            embedder.embed_query(query), top_k=top_k, where={"is_active": True}
        )
        for hit in hits:
            chunk_id = hit["metadata"].get("chunk_id")
            if isinstance(chunk_id, int) and chunk_id > 0:
                vector_ids.append(chunk_id)
    except Exception as exc:  # noqa: BLE001
        # 向量库挂了不该让整个问答失败：退化成纯 BM25，并在日志里告警
        logger.warning("向量召回失败，本次退化为纯 BM25：%s", exc)

    bm25_ids = _bm25_search(query, top_k)

    fused = rrf_fuse([vector_ids, bm25_ids], k=current_app.config["RRF_K"])
    candidates = load_candidates(list(fused.keys())[: top_k * 2])

    # 打上各路排名，便于排查"某个块是靠哪一路召回的"
    vector_rank = {cid: i for i, cid in enumerate(vector_ids, 1)}
    bm25_rank = {cid: i for i, cid in enumerate(bm25_ids, 1)}
    for candidate in candidates:
        candidate.rank_vector = vector_rank.get(candidate.chunk_id)
        candidate.rank_bm25 = bm25_rank.get(candidate.chunk_id)
        candidate.score = fused.get(candidate.chunk_id)
    return candidates


def _bm25_search(query: str, top_k: int) -> list[int]:
    index = _ensure_index()
    if index.bm25 is None or not index.chunk_ids:
        return []

    tokens = _tokenize(query)
    if not tokens:
        return []

    scores = index.bm25.get_scores(tokens)
    ranked_positions = sorted(
        range(len(scores)), key=lambda i: scores[i], reverse=True
    )[:top_k]
    # 分数为 0 表示一个词都没命中，这种结果放进融合只会稀释排名
    return [index.chunk_ids[i] for i in ranked_positions if scores[i] > 0]


def load_candidates(chunk_ids: list[int]) -> list[Candidate]:
    """按 chunk_id 装载候选，保持传入顺序。"""
    if not chunk_ids:
        return []

    from app.models import KnowledgeChunk

    rows = KnowledgeChunk.query.filter(KnowledgeChunk.id.in_(chunk_ids)).all()
    by_id = {row.id: row for row in rows}

    candidates: list[Candidate] = []
    for chunk_id in chunk_ids:
        row = by_id.get(chunk_id)
        if row is None:
            # 向量库里有、业务表里没有 —— 说明某次删除只删了一边。
            # 静默跳过并告警，比抛异常好：不影响本次问答，但留下排查线索。
            logger.warning("分块 %s 在业务表中不存在（向量与业务表可能不同步）", chunk_id)
            continue
        document = getattr(row, "document", None)
        candidates.append(
            Candidate(
                chunk_id=row.id,
                content=row.content,
                title=getattr(document, "title", "") or "",
                section_path=row.section_path or "",
                page=row.page,
                document_id=row.document_id,
            )
        )
    return candidates

