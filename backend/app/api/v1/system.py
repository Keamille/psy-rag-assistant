"""系统与元信息接口（开发文档 §7.8）：存活/就绪探针、运行期配置、求助资源。"""

from __future__ import annotations

import json
import os
import time

import httpx
from flask import Blueprint, current_app, request
from sqlalchemy import text

from app.core.response import fail, ok
from app.data_loader import load_hotlines
from app.extensions import db, redis_store

bp = Blueprint("system", __name__)


@bp.get("/health")
def health():
    """存活探针：只证明进程活着，不检查依赖。"""
    return ok({"status": "ok", "service": "psy-rag-assistant", "env": current_app.config["APP_ENV"]})


def _probe_database() -> dict:
    started = time.perf_counter()
    try:
        db.session.execute(text("SELECT 1"))
        return {"status": "ok", "latency_ms": round((time.perf_counter() - started) * 1000)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "down", "error": str(exc)[:200]}


def _probe_redis() -> dict:
    started = time.perf_counter()
    healthy, error = redis_store.ping()
    if healthy:
        return {"status": "ok", "latency_ms": round((time.perf_counter() - started) * 1000)}
    return {"status": "degraded", "error": (error or "")[:200]}


def _probe_chroma() -> dict:
    host = current_app.config.get("CHROMA_HOST", "")
    if not host:
        try:
            import chromadb  # noqa: F401

            return {
                "status": "ok",
                "mode": "embedded",
                "path": current_app.config.get("CHROMA_PATH"),
            }
        except ImportError:
            return {"status": "degraded", "mode": "embedded", "error": "chromadb 未安装"}

    url = f"http://{host}:{current_app.config['CHROMA_PORT']}/api/v1/heartbeat"
    started = time.perf_counter()
    try:
        # trust_env=False：httpx 默认会读取系统代理，把 localhost 请求也塞进代理，
        # 结果是明明 Chroma 活着却探测到 502。
        # 探针必须绕过代理——这和 rag/chroma_http.py 里的处理是同一个原因。
        with httpx.Client(timeout=2.0, trust_env=False) as client:
            resp = client.get(url)
        return {
            "status": "ok" if resp.status_code < 500 else "degraded",
            "mode": "http",
            "latency_ms": round((time.perf_counter() - started) * 1000),
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "degraded", "mode": "http", "error": str(exc)[:200]}


def _probe_embedding() -> dict:
    model = current_app.config["EMBEDDING_MODEL"]
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return {
            "status": "degraded",
            "model": model,
            "loaded": False,
            "error": "sentence-transformers 未安装，无法计算向量",
        }
    from app.rag import embedder

    return {"status": "ok", "model": model, "loaded": embedder.is_loaded()}


def _probe_llm(deep: bool = False) -> dict:
    provider = current_app.config["LLM_PROVIDER"]
    base_url = current_app.config["LLM_BASE_URL"]
    model = current_app.config["LLM_MODEL"]
    if provider == "openai_compat" and not current_app.config["LLM_API_KEY"]:
        return {"status": "unconfigured", "provider": provider, "model": model, "error": "未配置 LLM_API_KEY"}
    if not deep:
        # 默认不做真实调用，避免每次探针都产生费用与延迟；需要时用 /ready?deep=1
        return {"status": "configured", "provider": provider, "model": model, "base_url": base_url}

    started = time.perf_counter()
    try:
        resp = httpx.get(f"{base_url.rstrip('/')}/models", timeout=5.0)
        latency = round((time.perf_counter() - started) * 1000)
        if resp.status_code < 400:
            return {"status": "ok", "provider": provider, "model": model, "latency_ms": latency}
        return {"status": "degraded", "provider": provider, "http_status": resp.status_code}
    except Exception as exc:  # noqa: BLE001
        return {"status": "degraded", "provider": provider, "error": str(exc)[:200]}


@bp.get("/ready")
def ready():
    """依赖就绪探针。

    默认只做廉价检查；`?deep=1` 时会真实请求 LLM 的 /models 端点。
    数据库不可用视为致命（返回 503），其余依赖降级时仍返回 200——
    向量库或 Redis 掉线只影响对应能力，不应让整个容器被判定为不健康。
    """
    deep = request.args.get("deep", "0") == "1"
    checks = {
        "database": _probe_database(),
        "redis": _probe_redis(),
        "chroma": _probe_chroma(),
        "embedding": _probe_embedding(),
        "llm": _probe_llm(deep=deep),
    }
    if checks["database"]["status"] != "ok":
        return fail(9001, "数据库不可用", 503, data=checks)
    return ok(checks)


@bp.get("/meta/hotlines")
def meta_hotlines():
    region = request.args.get("region", current_app.config["HOTLINE_REGION"])
    try:
        return ok(load_hotlines(region))
    except KeyError:
        return fail(1001, f"没有区域 {region} 的求助资源配置", 400)


@bp.get("/meta/config")
def meta_config():
    disclaimer_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "disclaimer.md"
    )
    try:
        with open(disclaimer_path, encoding="utf-8") as fp:
            disclaimer_markdown = fp.read()
    except OSError:
        disclaimer_markdown = ""

    return ok(
        {
            "disclaimer_version": current_app.config["DISCLAIMER_VERSION"],
            "disclaimer_markdown": disclaimer_markdown,
            "max_message_length": 4000,
            "features": {
                "rag": True,
                "crisis_intervention": True,
                "conversation_memory": True,
                "scale_assessment": False,
                "voice_input": False,
            },
            "hotline_region": current_app.config["HOTLINE_REGION"],
        }
    )


@bp.get("/meta/build")
def meta_build():
    """服务信息：版本与当前启用的能力。

    报告版本与能力开关，用于排查（例如确认重排是否真的开启了）。
    不要在这里加"哪些功能还没做好"之类的进度信息——使用者看到待办清单
    会以为系统不可用。
    """
    return ok(
        {
            "name": "psy-rag-assistant",
            "version": current_app.config.get("APP_VERSION", "1.0.0"),
            "env": current_app.config.get("APP_ENV"),
            "features": {
                "rag": True,
                "rerank": bool(current_app.config["RERANK_ENABLED"]),
                "crisis_intervention": True,
                "conversation_memory": True,
            },
        }
    )

