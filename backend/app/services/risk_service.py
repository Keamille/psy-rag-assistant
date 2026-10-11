"""风险识别与处置（开发文档 §10.2）。

**双通道为什么是必要的**

规则层（词典）与模型层各自会漏，而且漏的地方不一样：

  规则层擅长显式表达（"不想活了""割腕"），但对隐晦表达无能为力——
  "希望睡过去不要醒"这种句子一个敏感词都没有；
  模型层擅长理解语义，但会**过度敏感**——引用影视情节、转述朋友的困扰、
  说"笑死我了"，都可能被判成风险。

所以两者不是二选一，而是串起来用：规则层负责"不漏"，
模型层负责"把规则层抓到的误报摘掉，同时补上隐晦表达"。

**失败时为什么必须保守**

模型确认调用超时或返回不可解析时，按**规则层的结果**执行。
这个方向的错误代价是不对称的：多拦一次只是打扰用户，
漏拦一次可能是一次不可挽回的伤害。安全功能的设计原则是——
宁可误报，不可漏报。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from flask import current_app

from app.data_loader import load_risk_lexicon

logger = logging.getLogger(__name__)

LEVEL_SAFE = "safe"
LEVEL_MEDIUM = "medium"
LEVEL_HIGH = "high"

CARD_TEMPLATES = {
    LEVEL_HIGH: {
        "title": "我很在意你刚才说的话",
        "body": (
            "你刚才提到的内容让我有些担心。接下来我先不给建议，"
            "请你先联系下面的专业渠道，他们能真正帮到你。"
        ),
        "confirm_text": "我目前是安全的，继续对话",
    },
    LEVEL_MEDIUM: {
        "title": "想先确认一下你的状态",
        "body": "你描述的这些感受值得认真对待。如果你愿意，可以联系下面的渠道聊聊。",
        "confirm_text": "我目前是安全的，继续对话",
    },
}


@dataclass
class RiskVerdict:
    level: str
    source: str  # rule | model | both
    matched_terms: list[str] = field(default_factory=list)
    reason: str = ""
    is_quotation: bool = False

    @property
    def action(self) -> str:
        if self.level == LEVEL_HIGH:
            return "interrupt"
        if self.level == LEVEL_MEDIUM:
            return "warned_and_continued"
        # safe 对应 continue，不能用"非高危就告警"这种二分
        return "continue"

    def to_payload(self, hotlines: list[dict]) -> dict:
        return {
            "level": self.level,
            "source": self.source,
            "matched_terms": self.matched_terms,
            "action": self.action,
            "card": CARD_TEMPLATES.get(self.level),
            "hotlines": hotlines,
        }


class RiskService:
    def __init__(self, lexicon: dict | None = None, llm=None, settings=None) -> None:  # noqa: ANN001
        self.lexicon = lexicon if lexicon is not None else load_risk_lexicon()
        self.llm = llm
        self.settings = settings or current_app.config
        self._compiled = _compile_lexicon(self.lexicon)

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def check(self, text: str) -> RiskVerdict:
        text = text or ""
        rule_hit = self._scan_rules(text) if self.settings.get("RISK_RULE_ENABLED") else None
        confirm_enabled = bool(self.settings.get("RISK_MODEL_CONFIRM"))

        # 规则没命中，且模型确认被关掉 —— 只能判 safe
        if rule_hit is None and not confirm_enabled:
            return RiskVerdict(LEVEL_SAFE, "rule", [], "规则未命中且未启用模型确认")

        # 规则没命中：只有开了模型确认，才值得花一次调用去捞隐晦表达
        if rule_hit is None:
            model = self._model_confirm(text)
            if model and model.get("level") in (LEVEL_MEDIUM, LEVEL_HIGH):
                return RiskVerdict(
                    model["level"],
                    "model",
                    [],
                    model.get("reason", ""),
                    bool(model.get("is_quotation")),
                )
            return RiskVerdict(LEVEL_SAFE, "model", [], (model or {}).get("reason", ""))

        # 规则命中：必须送模型确认
        if not confirm_enabled:
            return RiskVerdict(rule_hit["level"], "rule", rule_hit["terms"], "未启用模型确认")

        model = self._model_confirm(text)
        if model is None:
            # 超时/解析失败 → 保守处置，按规则层等级执行
            logger.warning("风险模型确认不可用，按规则层结果保守处置 level=%s", rule_hit["level"])
            return RiskVerdict(
                rule_hit["level"], "rule", rule_hit["terms"], "模型确认不可用，保守处置"
            )

        # 模型判定为引用/转述时，以模型的等级为准，而不是取两者最大值：
        # "我妹妹说她想自杀"这类转述句会被规则层按"自杀"抓成 high，
        # 取最大值会让来求助"怎么帮朋友"的用户被打断，恰好帮不到他。
        # is_quotation 是"这不是说话者本人的风险"的明确断言，应覆盖关键词匹配。
        # 仍非静默放行——事件照记，供人工复核。
        if model.get("is_quotation"):
            return RiskVerdict(
                model.get("level", LEVEL_SAFE),
                "both",
                rule_hit["terms"],
                model.get("reason", "判定为引用或转述语境"),
                True,
            )

        level = LEVEL_HIGH if LEVEL_HIGH in (rule_hit["level"], model.get("level")) else LEVEL_MEDIUM
        return RiskVerdict(level, "both", rule_hit["terms"], model.get("reason", ""))

    # ------------------------------------------------------------------
    # 规则层
    # ------------------------------------------------------------------

    def _scan_rules(self, text: str) -> dict | None:
        for level in (LEVEL_HIGH, LEVEL_MEDIUM):
            for entry in self._compiled.get(level, []):
                pattern = entry["pattern"]
                matched = pattern.search(text) if pattern else (entry["term"] in text)
                if not matched:
                    continue
                if self._is_negated(text, entry):
                    # "我不想死""我从来没想过自杀"——命中了词但对语义是反的。
                    # 这里只做跳过，最终判定交给模型层，不在规则层直接判 safe。
                    continue
                return {"level": level, "terms": [entry["term"]]}
        return None

    @staticmethod
    def _is_negated(text: str, entry: dict) -> bool:
        lookback = int(entry.get("negation_lookback", 4))
        term = entry["term"]
        for prefix in entry.get("negation_prefixes", []):
            if prefix + term in text:
                return True
        # 兜底：词前若干字符内出现否定词
        index = text.find(term)
        if index > 0:
            window = text[max(0, index - lookback):index]
            if any(neg in window for neg in ("不", "没", "别", "没有")):
                return True
        return False

    # ------------------------------------------------------------------
    # 模型层
    # ------------------------------------------------------------------

    def _model_confirm(self, text: str) -> dict | None:
        """返回模型判定结果；任何失败都返回 None（由调用方保守处置）。"""
        if self.llm is None:
            return None
        timeout = int(self.settings.get("RISK_CONFIRM_TIMEOUT", 3))
        try:
            from app.rag import prompt as prompt_module

            raw = self.llm.complete_json(
                prompt_module.RISK_CONFIRM_PROMPT.format(text=text),
                temperature=0.0,
                timeout=timeout,
                max_tokens=200,
            )
            return _extract_json(raw)
        except Exception as exc:  # noqa: BLE001
            logger.info("风险模型确认失败（将保守处置）：%s", exc)
            return None


def _extract_json(raw: str) -> dict | None:
    """从模型输出里抠出 JSON。

    很多模型会裹一层 ```json 代码块或加一句前言，直接 json.loads 会失败。
    先试整体解析，再退一步用正则找第一个 {...}。
    """
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _compile_lexicon(lexicon: dict) -> dict:
    """把词典里的 regex 字符串编译成 Pattern，并补齐默认字段。"""
    windows = lexicon.get("windows", {}) or {}
    default_lookback = int(windows.get("negation_lookback", 4))

    compiled: dict[str, list[dict]] = {}
    for level in (LEVEL_HIGH, LEVEL_MEDIUM):
        entries: list[dict] = []
        for raw in lexicon.get(level, []) or []:
            pattern = None
            if raw.get("regex"):
                try:
                    pattern = re.compile(raw["regex"])
                except re.error as exc:  # noqa: BLE001
                    logger.warning("风险词典里的正则无法编译（已跳过该项）：%s", exc)
            entries.append(
                {
                    "term": raw["term"],
                    "pattern": pattern,
                    "negation_prefixes": raw.get("negation_prefixes", []) or [],
                    "negation_lookback": default_lookback,
                }
            )
        compiled[level] = entries
    return compiled


def get_risk_service(llm=None) -> RiskService:  # noqa: ANN001
    return RiskService(llm=llm)

