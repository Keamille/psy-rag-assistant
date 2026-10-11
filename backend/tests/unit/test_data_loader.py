"""内置数据文件的结构与排序校验。"""

from __future__ import annotations

import os

import pytest

from app import data_loader


def test_hotlines_sorted_by_priority():
    data = data_loader.load_hotlines("CN")
    assert data["region"] == "CN"
    assert data["verified_at"]
    priorities = [item["priority"] for item in data["items"]]
    assert priorities == sorted(priorities)
    assert all(item["is_active"] for item in data["items"])
    assert {"12356", "120", "110"} <= {item["phone"] for item in data["items"]}


def test_hotlines_unknown_region_raises():
    with pytest.raises(KeyError):
        data_loader.load_hotlines("NOT_A_REGION")


def test_risk_lexicon_shape():
    lexicon = data_loader.load_risk_lexicon()
    assert lexicon["version"]
    assert lexicon["high"] and lexicon["medium"]
    for level in ("high", "medium"):
        for entry in lexicon[level]:
            assert entry["term"]
            assert "regex" in entry
            assert isinstance(entry.get("negation_prefixes", []), list)


def test_base_knowledge_files_present():
    """内置语料必须齐 12 篇，且每篇有标题层级供切分器使用。"""
    knowledge_dir = os.path.join(data_loader.DATA_DIR, "base_knowledge")
    files = sorted(f for f in os.listdir(knowledge_dir) if f.endswith(".md"))
    assert len(files) == 12, f"内置语料应为 12 篇，实际 {len(files)} 篇：{files}"

    for filename in files:
        with open(os.path.join(knowledge_dir, filename), encoding="utf-8") as fp:
            text = fp.read()
        assert text.startswith("# "), f"{filename} 缺少 H1 标题"
        assert "\n## " in text, f"{filename} 缺少二级标题，切分器无法按层级分段"
        assert len(text) >= 300, f"{filename} 内容过短（{len(text)} 字符）"

