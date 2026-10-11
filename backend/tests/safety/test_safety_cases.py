"""安全用例集的加载与完整性校验。

这里只验证用例集本身：条数、格式、必需类别的覆盖。
逐条驱动 RiskService 断言实际等级与动作的测试尚未实现——
在补齐之前，cases.yaml 是人工评审用的**验收契约**，不是自动化回归。
"""

from __future__ import annotations

import os

import pytest

yaml = pytest.importorskip("yaml", reason="需要 PyYAML：pip install -r requirements-dev.txt")

CASES_PATH = os.path.join(os.path.dirname(__file__), "cases.yaml")


def _load() -> dict:
    with open(CASES_PATH, encoding="utf-8") as fp:
        return yaml.safe_load(fp)


def test_case_count_meets_requirement():
    assert len(_load()["cases"]) >= 20


def test_every_case_is_well_formed():
    valid_levels = {"high", "medium", "safe", "safe_or_medium"}
    # not_interrupt：只要求"不中断"，允许 safe→continue 或 medium→warned_and_continued。
    # 用于"转述他人风险"这类用例——用户自己的情绪受影响程度可能不同，
    # 硬性要求某一个动作会和等级判定自相矛盾。
    valid_actions = {"interrupt", "warned_and_continued", "continue", "not_interrupt"}
    ids = set()
    for case in _load()["cases"]:
        assert case["id"] not in ids, f"用例 id 重复：{case['id']}"
        ids.add(case["id"])
        assert case["text"].strip()
        assert case["expect_level"] in valid_levels
        assert case["expect_action"] in valid_actions


def test_required_categories_covered():
    """必需覆盖：显式自杀、隐晦表达、自伤、伤人、药物滥用、转述、玩笑、否定、越狱。"""
    cases = _load()["cases"]
    interrupt_cases = [c for c in cases if c["expect_action"] == "interrupt"]
    continue_cases = [c for c in cases if c["expect_action"] == "continue"]
    assert len(interrupt_cases) >= 6, "必须中断的用例不足"
    assert len(continue_cases) >= 4, "必须不被误中断的用例不足"
    assert any("遗书" in c["text"] or "跳" in c["text"] for c in interrupt_cases)
    assert any(("朋友" in c["text"] or "妹妹" in c["text"] or "同学" in c["text"]) for c in cases)
    assert any("must_not_contain" in c for c in cases), "缺少边界越狱用例"


def test_transitive_risk_cases_use_not_interrupt():
    """转述他人风险的用例必须用 not_interrupt，防止有人改回 warned_and_continued。"""
    cases = [c for c in _load()["cases"] if c["id"] in ("s-15", "s-16", "s-17")]
    assert cases, "缺少转述他人风险的用例"
    for case in cases:
        assert case["expect_action"] == "not_interrupt"

