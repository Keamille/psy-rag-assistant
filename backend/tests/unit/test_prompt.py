"""Prompt 常量与开发文档附录 D 的一致性检查。"""

from __future__ import annotations

from app.rag import prompt


def test_system_prompt_contains_boundaries():
    text = prompt.SYSTEM_PROMPT
    # 边界规则是安全底线，缺失即视为回归
    for keyword in ("不是医生", "不做诊断", "药物建议", "不能替代专业治疗"):
        assert keyword in text, f"system Prompt 缺少关键边界词：{keyword}"


def test_risk_confirm_prompt_requires_json():
    text = prompt.RISK_CONFIRM_PROMPT
    assert "{text}" in text
    assert '"level"' in text
    assert "high|medium|safe" in text

