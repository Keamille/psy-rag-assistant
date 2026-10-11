"""极简 Chroma HTTP 客户端。

**为什么不用官方 chromadb 客户端**

pip 的 `chromadb-client==0.5.23` 初始化时调用 `/api/v1/auth/identity`，
而 `chromadb/chroma:0.5.23` 服务端只提供 `/api/v2/auth/identity`——
版本号相同但 API 版本对不上，`HttpClient()` 直接抛 `ValueError`，
且异常信息是空的（客户端把原因吞掉了）。

我们只用 5 个操作（建集合、写入、查询、删除、计数），不值得为版本对齐买单。
这里直接用 httpx 打 v1 REST 接口，出错时能看到服务端返回的原文。
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Docker Desktop 的端口转发偶发 502（容器是健康的，日志里根本看不到这次请求）。
# 这种瞬时故障重试一次就好，不重试会让入库任务莫名其妙地失败。
RETRYABLE_STATUS = {502, 503, 504}
RETRY_TIMES = 3
RETRY_DELAY = 1.0


class ChromaError(RuntimeError):
    """Chroma 调用失败。带上服务端返回的原文，避免又一次「空异常」。"""


class ChromaHTTP:
    def __init__(self, host: str, port: int, timeout: float = 30.0):
        self.base = f"http://{host}:{port}/api/v1"
        self.timeout = timeout
        self._collection_ids: dict[str, str] = {}
        # **必须 trust_env=False**：httpx 默认会读取系统代理（Windows 的 Internet 选项），
        # 把发往 localhost 的请求也塞进代理，而代理到不了本地容器，
        # 表现为稳定的 HTTP 502 —— 而 curl 不受影响，所以极易误判成 Docker 端口转发故障。
        # Chroma 永远是本地或内网地址，绝不该走代理。
        # 注意：LLM 客户端保持默认（trust_env=True），因为访问公网模型服务可能正需要系统代理。
        self._client = httpx.Client(timeout=timeout, trust_env=False)

    # ------------------------------------------------------------------
    # 底层请求
    # ------------------------------------------------------------------

    def _post(self, path: str, payload: dict | None = None) -> Any:
        url = f"{self.base}{path}"
        last_error = ""
        for attempt in range(RETRY_TIMES):
            try:
                resp = self._client.post(url, json=payload or {})
            except httpx.HTTPError as exc:
                last_error = f"无法连接：{exc}"
                self._wait(attempt)
                continue

            if resp.status_code in RETRYABLE_STATUS and attempt < RETRY_TIMES - 1:
                last_error = f"HTTP {resp.status_code}"
                self._wait(attempt)
                continue
            if resp.status_code >= 400:
                raise ChromaError(
                    f"Chroma 返回 HTTP {resp.status_code}（{url}）：{resp.text[:300]}"
                )
            if not resp.content:
                return None
            try:
                return resp.json()
            except ValueError:
                return resp.text
        raise ChromaError(f"Chroma 请求失败（{url}）：{last_error}")

    def _get(self, path: str) -> Any:
        url = f"{self.base}{path}"
        last_error = ""
        for attempt in range(RETRY_TIMES):
            try:
                resp = self._client.get(url)
            except httpx.HTTPError as exc:
                last_error = f"无法连接：{exc}"
                self._wait(attempt)
                continue
            if resp.status_code in RETRYABLE_STATUS and attempt < RETRY_TIMES - 1:
                last_error = f"HTTP {resp.status_code}"
                self._wait(attempt)
                continue
            if resp.status_code >= 400:
                raise ChromaError(
                    f"Chroma 返回 HTTP {resp.status_code}（{url}）：{resp.text[:300]}"
                )
            return resp.json() if resp.content else None
        raise ChromaError(f"Chroma 请求失败（{url}）：{last_error}")

    @staticmethod
    def _wait(attempt: int) -> None:
        time.sleep(RETRY_DELAY * (attempt + 1))

    def heartbeat(self) -> int | None:
        """探活。服务器不可达时返回 None 而不是抛异常，供 /ready 使用。"""
        try:
            data = self._get("/heartbeat")
            return int(data.get("nanosecond heartbeat")) if isinstance(data, dict) else None
        except ChromaError:
            return None

    # ------------------------------------------------------------------
    # 集合
    # ------------------------------------------------------------------

    def get_or_create_collection(self, name: str, metadata: dict | None = None) -> str:
        """返回 collection_id。

        结果缓存在实例上：collection_id 在一次进程生命周期内不会变，
        每次操作都查一遍是纯浪费（而且 upsert 是高频调用）。
        """
        if name in self._collection_ids:
            return self._collection_ids[name]

        # 先按名字查一次。不要直接 POST 建集合——Chroma 要求 metadata 是
        # **非空 dict**，传 {} 会被拒绝（"Expected metadata to be a non-empty dict"）。
        # 先查后建既避开了这个限制，也避免了重复建集合。
        try:
            info = self._get(f"/collections/{name}")
            if isinstance(info, dict) and info.get("id"):
                self._collection_ids[name] = str(info["id"])
                return self._collection_ids[name]
        except ChromaError:
            pass

        info = self._post(
            "/collections",
            {
                "name": name,
                # 必须有内容，见上面的说明
                "metadata": metadata or {"hnsw:space": "cosine"},
                "get_or_create": True,
            },
        )
        self._collection_ids[name] = str(info["id"])
        return self._collection_ids[name]

    # ------------------------------------------------------------------
    # 向量读写
    # ------------------------------------------------------------------

    def upsert(
        self,
        collection_id: str,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        if not ids:
            return
        self._post(
            f"/collections/{collection_id}/upsert",
            {
                "ids": ids,
                "embeddings": embeddings,
                "documents": documents,
                "metadatas": metadatas,
            },
        )

    def query(
        self,
        collection_id: str,
        query_embedding: list[float],
        n_results: int,
        where: dict | None = None,
        include: list[str] | None = None,
    ) -> dict:
        """向量检索。返回 Chroma 的原始结构（嵌套一层列表）。"""
        return self._post(
            f"/collections/{collection_id}/query",
            {
                "query_embeddings": [query_embedding],
                "n_results": n_results,
                "where": where,
                "include": include or ["documents", "metadatas", "distances"],
            },
        )

    def get(
        self,
        collection_id: str,
        where: dict | None = None,
        include: list[str] | None = None,
        limit: int | None = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "where": where,
            "include": include if include is not None else [],
        }
        if limit is not None:
            payload["limit"] = limit
        return self._post(f"/collections/{collection_id}/get", payload)

    def delete(
        self,
        collection_id: str,
        where: dict | None = None,
        ids: list[str] | None = None,
    ) -> None:
        payload: dict[str, Any] = {}
        if where:
            payload["where"] = where
        if ids:
            payload["ids"] = ids
        if not payload:
            # 空条件会让服务端拒绝；这里主动拦住，避免"以为删了其实没删"
            raise ChromaError("delete 必须提供 where 或 ids，拒绝无条件的全量删除")
        self._post(f"/collections/{collection_id}/delete", payload)

    def count(self, collection_id: str) -> int:
        result = self._post(f"/collections/{collection_id}/count")
        return int(result) if result is not None else 0

