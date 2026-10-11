"""大模型统一客户端（开发文档 §7.7 的降级策略 / §6.7 的超时重试）。

抽象成 OpenAI 兼容协议，云端（DeepSeek / 通义 / 智谱）与本地 Ollama
走同一套 `/chat/completions`，切换只改 LLM_PROVIDER 与 LLM_BASE_URL。

两种调用形态分开是有原因的，不要合并：

  complete_json  —— 非流式、要严格 JSON、要求低温、超时很短。
                    用于风险确认、查询重写、会话摘要。这些调用**不能慢**，
                    因为它们卡在用户可见的链路上。
  stream_chat    —— 流式、逐块返回、超时很长。
                    用于真正的对话生成，首字延迟直接决定体感。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Iterator

import httpx
from flask import current_app

from app.core.errors import ErrorCode

logger = logging.getLogger(__name__)

# 重试只针对这些情况：网络抖动、限流、服务端错误。
# 4xx（除了 429）说明请求本身有问题，重试没有意义。
RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


@dataclass
class StreamPiece:
    """流式返回的一段。type 取 delta / usage / done。"""

    type: str
    text: str = ""
    usage: dict | None = None


class LLMUnavailable(Exception):
    """模型服务不可用。code 取 ErrorCode 里的 4001（不可用）或 4002（超时）。"""

    def __init__(self, code: int, message: str):
        self.code = code
        super().__init__(message)


class LLMClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: int = 120,
        temperature: float = 0.4,
        max_tokens: int = 1200,
        max_retries: int = 2,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries

    # ------------------------------------------------------------------
    # 内部：请求头与错误分类
    # ------------------------------------------------------------------

    @property
    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _payload(self, messages: list[dict], **overrides) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        payload.update(overrides)
        return payload

    def _raise_for_status(self, status_code: int, body: str) -> None:
        if status_code == 401 or status_code == 403:
            # 密钥问题重试再多次也没用，直接报不可用并提示配置
            raise LLMUnavailable(
                ErrorCode.LLM_UNAVAILABLE,
                f"模型服务鉴权失败（HTTP {status_code}），请检查 LLM_API_KEY",
            )
        raise LLMUnavailable(
            ErrorCode.LLM_UNAVAILABLE,
            f"模型服务返回 HTTP {status_code}：{body[:200]}",
        )

    # ------------------------------------------------------------------
    # 非流式：要 JSON 的短输出场景
    # ------------------------------------------------------------------

    def complete_json(
        self,
        prompt: str,
        temperature: float = 0.0,
        timeout: int | None = None,
        max_tokens: int = 200,
        system: str | None = None,
    ) -> str:
        """返回模型输出的原始文本。调用方负责 json.loads。

        **刻意不做 json 解析**：解析失败时调用方需要的是"这次确认失败了"这个事实，
        而不是一个被吞掉的异常。风险判定的超时/失败分支就依赖这个区别。
        """
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = self._payload(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
        wait = timeout or self.timeout
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=wait) as client:
                    resp = client.post(
                        f"{self.base_url}/chat/completions",
                        headers=self._headers,
                        json=payload,
                    )
                if resp.status_code >= 400:
                    if resp.status_code in RETRYABLE_STATUS and attempt < self.max_retries:
                        last_error = LLMUnavailable(
                            ErrorCode.LLM_UNAVAILABLE, f"HTTP {resp.status_code}"
                        )
                        self._sleep(attempt)
                        continue
                    self._raise_for_status(resp.status_code, resp.text)

                data = resp.json()
                return data["choices"][0]["message"]["content"] or ""
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt < self.max_retries:
                    self._sleep(attempt)
                    continue
                raise LLMUnavailable(
                    ErrorCode.LLM_TIMEOUT, f"模型调用超时（{wait}s）"
                ) from exc
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    self._sleep(attempt)
                    continue
                raise LLMUnavailable(
                    ErrorCode.LLM_UNAVAILABLE, f"模型服务不可达：{exc}"
                ) from exc

        raise LLMUnavailable(ErrorCode.LLM_UNAVAILABLE, f"模型调用失败：{last_error}")

    # ------------------------------------------------------------------
    # 流式：对话生成
    # ------------------------------------------------------------------

    def stream_chat(self, messages: list[dict]) -> Iterator[StreamPiece]:
        """逐块产出模型输出。失败时抛 LLMUnavailable。

        只在**开始阶段**重试：一旦已经有内容吐给用户了，重试会导致
        重复输出前半段，所以中途断开只报错、不重试。
        """
        payload = self._payload(messages, stream=True)

        for attempt in range(self.max_retries + 1):
            emitted = False
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers=self._headers,
                        json=payload,
                    ) as resp:
                        if resp.status_code >= 400:
                            body = resp.read().decode("utf-8", errors="ignore")
                            if resp.status_code in RETRYABLE_STATUS and attempt < self.max_retries:
                                self._sleep(attempt)
                                continue
                            self._raise_for_status(resp.status_code, body)

                        for piece in self._iter_sse_lines(resp):
                            if piece.type == "delta" and piece.text:
                                emitted = True
                            yield piece
                        return
            except httpx.TimeoutException as exc:
                if emitted or attempt >= self.max_retries:
                    raise LLMUnavailable(
                        ErrorCode.LLM_TIMEOUT, f"模型调用超时（{self.timeout}s）"
                    ) from exc
                self._sleep(attempt)
            except httpx.HTTPError as exc:
                if emitted or attempt >= self.max_retries:
                    raise LLMUnavailable(
                        ErrorCode.LLM_UNAVAILABLE, f"模型服务不可达：{exc}"
                    ) from exc
                self._sleep(attempt)

    def _iter_sse_lines(self, resp: httpx.Response) -> Iterator[StreamPiece]:
        """解析 OpenAI 兼容的 `data: {...}` 流。

        两条容易漏的规则：
          - `data: [DONE]` 是结束标记，不是 JSON
          - 有些服务在最后一个 chunk 里才带 usage（且此时 choices 为空数组）
        """
        for raw in resp.iter_lines():
            if not raw:
                continue
            line = raw.strip()
            if line.startswith("data:"):
                line = line[5:].strip()
            if not line or line == "[DONE]":
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue

            if chunk.get("usage"):
                yield StreamPiece("usage", usage=chunk["usage"])

            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            text = delta.get("content")
            if text:
                yield StreamPiece("delta", text=text)

        yield StreamPiece("done")

    @staticmethod
    def _sleep(attempt: int) -> None:
        """指数退避：0.5s、1s、2s……"""
        time.sleep(0.5 * (2**attempt))


def build_client(**overrides) -> LLMClient:
    """按当前应用配置构造客户端。测试可传 overrides 覆盖任意字段。"""
    config = current_app.config
    params = {
        "base_url": config["LLM_BASE_URL"],
        "api_key": config["LLM_API_KEY"],
        "model": config["LLM_MODEL"],
        "timeout": config["LLM_TIMEOUT"],
        "temperature": config["LLM_TEMPERATURE"],
        "max_tokens": config["LLM_MAX_TOKENS"],
        "max_retries": config["LLM_MAX_RETRIES"],
    }
    params.update(overrides)
    return LLMClient(**params)

