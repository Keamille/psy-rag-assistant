"""内置数据文件（求助资源、风险词典）的加载与缓存。

文件位于 app/data/ 下，随镜像一起发布。
"""

from __future__ import annotations

import json
import os
from functools import lru_cache

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _load_json(filename: str) -> dict:
    path = os.path.join(DATA_DIR, filename)
    with open(path, encoding="utf-8") as fp:
        return json.load(fp)


@lru_cache(maxsize=8)
def load_hotlines(region: str = "CN") -> dict:
    """返回指定区域的求助资源。

    结构：{"region": "CN", "verified_at": "2026-10-04", "items": [...]}
    """
    payload = _load_json("hotlines.json")
    if region not in payload:
        raise KeyError(region)
    block = payload[region]
    items = [item for item in block.get("items", []) if item.get("is_active", True)]
    items.sort(key=lambda item: item.get("priority", 100))
    return {
        "region": region,
        "verified_at": block.get("verified_at"),
        "notice": block.get("notice", ""),
        "items": items,
    }


@lru_cache(maxsize=1)
def load_risk_lexicon() -> dict:
    """返回风险词典原始结构（high / medium / context_rules / windows）。"""
    return _load_json("risk_lexicon.json")


def clear_cache() -> None:
    load_hotlines.cache_clear()
    load_risk_lexicon.cache_clear()


__all__ = ["load_hotlines", "load_risk_lexicon", "clear_cache", "DATA_DIR"]

