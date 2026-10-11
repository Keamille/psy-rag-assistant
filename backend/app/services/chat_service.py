"""对话编排（开发文档 §4.3 时序图 / §7.6 事件协议）。

一次请求的完整流程与事件序：

    meta →(risk)? → delta* → sources → done / error

**顺序上的两条硬约束，不要调换：**

1. **风险判定必须在生成之前。** 一旦高危用户先看到一段温和的 AI 安慰，
   伤害就已经造成了——事后再打断也补不回来。
2. **风险中断时不产生任何 delta。** 前端据此判断"这是一次中断而不是一次
   被截断的回答"。如果先吐了几个字再中断，界面会显示成"回答到一半没了"。
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Iterator

from flask import current_app, g

from app.core.clock import utcnow
from app.core.errors import ErrorCode
from app.data_loader import load_hotlines
from app.extensions import db
from app.models import AuditLog, Conversation, CrisisEvent, Message
from app.models.conversations import STATUS_PAUSED
from app.models.messages import ROLE_ASSISTANT, ROLE_SYSTEM_CARD, ROLE_USER
from app.rag import prompt as prompt_module
from app.rag import reranker, retriever
from app.services import conversation_service, memory_service
from app.services.llm_client import LLMUnavailable, build_client
from app.services.risk_service import LEVEL_HIGH, LEVEL_MEDIUM, RiskService

logger = logging.getLogger(__name__)

# 引用编号 [1] [2]，用于生成后的合法性校验
CITATION = re.compile(r"\[(\d+)\]")


def sse(event: str, data: dict) -> str:
    """把事件格式化为 SSE 帧。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class ChatService:
    def __init__(self, user_id: int, conversation: Conversation) -> None:
        self.user_id = user_id
        self.conversation = conversation
        self.llm = build_client()
        self.risk = RiskService(llm=self.llm)

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------

    def stream_reply(self, text: str, client_msg_id: str | None) -> Iterator[str]:
        started = time.monotonic()

        # 落库走 conversation_service，复用它的归属校验与幂等逻辑
        user_message, created = conversation_service.append_user_message(
            conversation_id=self.conversation.id,
            user_id=self.user_id,
            text=text,
            client_msg_id=client_msg_id,
        )
        yield sse(
            "meta",
            {
                "conversation_id": self.conversation.id,
                "user_message_id": user_message.id,
                "client_msg_id": client_msg_id,
                # created=False 表示这是一次重发，命中了幂等
                "created": created,
            },
        )

        hotlines = self._hotlines()

        # ---- 风险判定：必须在生成之前 ----
        verdict = self.risk.check(text)
        if verdict.level in (LEVEL_HIGH, LEVEL_MEDIUM):
            self._record_crisis_event(user_message, verdict)
            yield sse("risk", verdict.to_payload(hotlines))

            if verdict.level == LEVEL_HIGH:
                assistant_message = self._persist_crisis_message(verdict)
                self._lock_conversation(verdict)
                # 刻意不发任何 delta：见文件头部第 2 条
                yield sse(
                    "done",
                    {
                        "assistant_message_id": assistant_message.id,
                        "finish_reason": "crisis_interrupt",
                        "usage": None,
                        "latency_ms": int((time.monotonic() - started) * 1000),
                    },
                )
                return

        # ---- 检索 ----
        context = memory_service.build_context(self.conversation)
        sources: list[retriever.Candidate] = []
        try:
            candidates = retriever.hybrid_search(text, top_k=current_app.config["TOP_K_RETRIEVE"])
            sources = reranker.rerank(text, candidates, top_k=current_app.config["TOP_K_RERANK"])
        except Exception as exc:  # noqa: BLE001
            # 检索失败不该让整个回答失败：退化成"没有资料"，模型会据此说明
            # 知识库里没有相关内容，而不是编造
            logger.warning("检索失败，本轮按无资料处理：%s", exc)

        messages = prompt_module.build_messages(
            user_text=text,
            summary=context.get("summary"),
            recent_turns=context.get("recent_turns"),
            chunks=sources,
        )

        # ---- 生成 ----
        parts: list[str] = []
        usage: dict | None = None
        try:
            for piece in self.llm.stream_chat(messages):
                if piece.type == "delta":
                    parts.append(piece.text)
                    yield sse("delta", {"text": piece.text})
                elif piece.type == "usage":
                    usage = piece.usage
        except LLMUnavailable as exc:
            logger.warning("生成失败：%s", exc)
            yield sse(
                "error",
                {
                    "code": exc.code,
                    "message": str(exc),
                    # 超时与不可用都可以重试——第二次可能就通了
                    "retryable": True,
                },
            )
            return

        answer, used_sources = self._strip_invalid_citations("".join(parts), sources)
        assistant_message = self._persist_assistant_message(
            answer, used_sources, usage, started
        )

        yield sse(
            "sources",
            {"items": [c.to_payload(i + 1) for i, c in enumerate(used_sources)]},
        )
        yield sse(
            "done",
            {
                "assistant_message_id": assistant_message.id,
                "finish_reason": "stop",
                "usage": usage,
                "latency_ms": int((time.monotonic() - started) * 1000),
            },
        )

        # ---- 摘要刷新放在 done 之后 ----
        # 用户已经拿到完整回答，此时多花一两秒没有体感损失；
        # 放在生成之前则会增加首字延迟，放在异步队列里又会出现
        # "下一轮开始时摘要还没写好"的尴尬窗口。
        try:
            if memory_service.needs_summary(self.conversation):
                memory_service.refresh_summary(self.conversation, self.llm)
        except Exception as exc:  # noqa: BLE001
            logger.warning("摘要刷新失败（不影响本轮回答）：%s", exc)

    # ------------------------------------------------------------------
    # 引用校验
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_invalid_citations(
        answer: str, sources: list[retriever.Candidate]
    ) -> tuple[str, list[retriever.Candidate]]:
        """剔除越界引用编号，并返回真正被引用到的来源。

        模型确实会编造不存在的编号（例如只检索到 3 条却写 [7]）。
        直接展示会让用户点开发现"什么都没有"，比不显示引用更伤可信度。

        返回被引用的来源而不是全部来源，是为了让前端的来源列表
        **只展示回答里真正用到的资料**——列一堆没被用到的片段同样是噪音。
        """
        total = len(sources)
        referenced: list[int] = []
        for match in CITATION.finditer(answer or ""):
            index = int(match.group(1))
            if 1 <= index <= total and index not in referenced:
                referenced.append(index)

        if total and not referenced:
            # 一条合法引用都没有：说明回答没真正依据资料。
            # 不抛错，但记下来——这个比例就是"幻觉引用率"的观测量。
            logger.info("本次回答未引用任何检索片段（共 %d 条候选）", total)

        ordered = [sources[i - 1] for i in referenced]
        return answer or "", ordered

    # ------------------------------------------------------------------
    # 落库与辅助
    # ------------------------------------------------------------------

    def _hotlines(self) -> list[dict]:
        try:
            return load_hotlines(current_app.config["HOTLINE_REGION"])["items"]
        except Exception as exc:  # noqa: BLE001
            logger.warning("求助资源加载失败：%s", exc)
            return []

    def _record_crisis_event(self, user_message: Message, verdict) -> None:  # noqa: ANN001
        """写危机事件。只保留命中句前后各 60 字，避免整段对话留痕。"""
        radius = int(
            (load_risk_windows() or {}).get("snippet_radius", 60)
        )
        content = user_message.content or ""
        term = (verdict.matched_terms or [""])[0]
        if term and term in content:
            index = content.find(term)
            start = max(0, index - radius)
            snippet = content[start: index + len(term) + radius]
        else:
            snippet = content[: radius * 2]

        db.session.add(
            CrisisEvent(
                user_id=self.user_id,
                conversation_id=self.conversation.id,
                message_id=user_message.id,
                level=verdict.level,
                source=verdict.source,
                matched_terms=",".join(verdict.matched_terms or [])[:255] or None,
                snippet=snippet,
                action_taken=verdict.action,
            )
        )
        db.session.commit()

    def _persist_crisis_message(self, verdict) -> Message:  # noqa: ANN001
        """把资源卡片作为一条 system_card 消息落库。

        这样做是为了刷新页面后用户仍能看到求助信息——
        如果只推事件不落库，重新打开会话就什么都找不到了。
        """
        card = (verdict.to_payload([]).get("card") or {})
        content = "\n\n".join(
            part for part in (card.get("title"), card.get("body")) if part
        )
        message = Message(
            conversation_id=self.conversation.id,
            role=ROLE_SYSTEM_CARD,
            content=content or "已触发安全中断，请查看求助资源。",
            risk_level=verdict.level,
        )
        db.session.add(message)
        db.session.commit()
        return message

    def _lock_conversation(self, verdict) -> None:  # noqa: ANN001
        """高危中断后锁定会话，需用户确认安全才能恢复（开发文档 §10.3）。"""
        self.conversation.status = STATUS_PAUSED
        self.conversation.crisis_level = verdict.level
        self.conversation.updated_at = utcnow()
        db.session.add(
            AuditLog(
                actor_id=self.user_id,
                action="crisis_interrupt",
                target_type="conversation",
                target_id=self.conversation.id,
                detail_json=json.dumps(
                    {"level": verdict.level, "source": verdict.source},
                    ensure_ascii=False,
                ),
                request_id=getattr(g, "request_id", None),
            )
        )
        db.session.commit()

    def _persist_assistant_message(
        self,
        answer: str,
        sources: list[retriever.Candidate],
        usage: dict | None,
        started: float,
    ) -> Message:
        message = Message(
            conversation_id=self.conversation.id,
            role=ROLE_ASSISTANT,
            content=answer,
            prompt_tokens=(usage or {}).get("prompt_tokens"),
            completion_tokens=(usage or {}).get("completion_tokens"),
            latency_ms=int((time.monotonic() - started) * 1000),
            model=current_app.config["LLM_MODEL"],
            sources_json=json.dumps(
                [c.to_payload(i + 1) for i, c in enumerate(sources)],
                ensure_ascii=False,
            )
            if sources
            else None,
        )
        db.session.add(message)
        self.conversation.updated_at = utcnow()
        db.session.commit()
        return message


def load_risk_windows() -> dict:
    from app.data_loader import load_risk_lexicon

    try:
        return load_risk_lexicon().get("windows", {})
    except Exception:  # noqa: BLE001
        return {}


__all__ = ["ChatService", "sse", "LEVEL_HIGH", "LEVEL_MEDIUM", "ROLE_USER"]

