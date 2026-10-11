"""配置类。所有环境相关参数一律读环境变量，代码内不硬编码密钥。"""

from __future__ import annotations

import os
from datetime import timedelta

from dotenv import load_dotenv

# 依次尝试加载：项目根 .env（compose 场景由 env_file 注入，这里主要服务本地开发）
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))
load_dotenv()


def _env_bool(key: str, default: str = "0") -> bool:
    return os.getenv(key, default).strip().lower() in {"1", "true", "yes", "on"}


def _env_list(key: str, default: str = "") -> list[str]:
    raw = os.getenv(key, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


class BaseConfig:
    # ---------- 基础 ----------
    APP_ENV = os.getenv("APP_ENV", "development")
    APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
    SECRET_KEY = os.getenv("APP_SECRET_KEY", "dev-only-secret-key-change-me")
    APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8080")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    JSON_AS_ASCII = False

    # ---------- 鉴权 ----------
    JWT_SECRET_KEY = os.getenv("JWT_SECRET", "dev-only-jwt-secret-change-me")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=int(os.getenv("JWT_ACCESS_MINUTES", "30")))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=int(os.getenv("JWT_REFRESH_DAYS", "14")))
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_ERROR_MESSAGE_KEY = "message"

    # ---------- 数据层 ----------
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # ---------- 中间件 ----------
    REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    REDIS_TIMEOUT = float(os.getenv("REDIS_TIMEOUT", "2"))
    CHROMA_HOST = os.getenv("CHROMA_HOST", "").strip()
    CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
    CHROMA_PATH = os.getenv("CHROMA_PATH", "./data/chroma")
    CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "psy_knowledge_v1")

    # ---------- 大模型 ----------
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai_compat")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
    LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "120"))
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.4"))
    LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1200"))
    LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))

    # ---------- 检索与向量化 ----------
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cpu")
    # 模型权重缓存目录。相对路径按**仓库根目录**解析，见 create_app 里的处理。
    # 不要直接用 HF_HOME：相对路径会被 huggingface 按当前工作目录解析，
    # 从 backend/ 启动时就找不到 models/ 了。
    MODEL_CACHE_DIR = os.getenv("MODEL_CACHE_DIR", "models/hf-cache")
    EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "16"))
    RERANK_ENABLED = _env_bool("RERANK_ENABLED", "1")
    RERANK_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
    RERANK_MIN_SCORE = float(os.getenv("RERANK_MIN_SCORE", "0.35"))
    # 送进 Cross-Encoder 的候选数上限。这一项直接决定检索延迟：
    # CPU 推理下每对 (query, 片段) 约 0.4–0.7 秒，
    # 20 个候选就是 9–14 秒，远超可接受的首字延迟。
    RERANK_MAX_CANDIDATES = int(os.getenv("RERANK_MAX_CANDIDATES", "6"))
    # 输入截断长度。中文按 1 字 ≈ 1.5 token 估，420 字的块约 280 token，
    # 取 384 基本不截断内容，但比默认 512 快约 25%。
    RERANK_MAX_LENGTH = int(os.getenv("RERANK_MAX_LENGTH", "384"))
    TOP_K_RETRIEVE = int(os.getenv("TOP_K_RETRIEVE", "20"))
    TOP_K_RERANK = int(os.getenv("TOP_K_RERANK", "5"))
    RRF_K = int(os.getenv("RRF_K", "60"))
    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "420"))
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "60"))
    QUERY_REWRITE_ENABLED = _env_bool("QUERY_REWRITE_ENABLED", "1")
    PRELOAD_MODELS = _env_bool("PRELOAD_MODELS", "0")

    # ---------- 安全 ----------
    RISK_RULE_ENABLED = _env_bool("RISK_RULE_ENABLED", "1")
    RISK_MODEL_CONFIRM = _env_bool("RISK_MODEL_CONFIRM", "1")
    RISK_CONFIRM_TIMEOUT = int(os.getenv("RISK_CONFIRM_TIMEOUT", "3"))
    HOTLINE_REGION = os.getenv("HOTLINE_REGION", "CN")
    DISCLAIMER_VERSION = os.getenv("DISCLAIMER_VERSION", "v1.0")

    # ---------- 配额与留存 ----------
    MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024
    DAILY_MESSAGE_QUOTA = int(os.getenv("DAILY_MESSAGE_QUOTA", "200"))
    MESSAGE_RATE_PER_MINUTE = int(os.getenv("MESSAGE_RATE_PER_MINUTE", "20"))
    CONVERSATION_RETENTION_DAYS = int(os.getenv("CONVERSATION_RETENTION_DAYS", "180"))
    CRISIS_RETENTION_DAYS = int(os.getenv("CRISIS_RETENTION_DAYS", "365"))

    # ---------- 跨域 ----------
    CORS_ORIGINS = _env_list("CORS_ORIGINS", "http://localhost:5173")

    # ---------- 分页 ----------
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100

    # ---------- 版本管理 ----------
    # 知情同意书版本与服务端展示给前端的免责声明版本必须是同一个值，
    # 否则会出现"前端让用户同意 v1.0、后端校验 v2.0"这种永远失败的注册。
    # 因此这里从 DISCLAIMER_VERSION（读环境变量）派生，只保留一个真实来源。
    CONSENT_VERSION = DISCLAIMER_VERSION



class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    PRELOAD_MODELS = False
    # 密钥长度需 >= 32 字节，否则 PyJWT 会对 HS256 发出 InsecureKeyLengthWarning
    SECRET_KEY = "testing-secret-key-for-unit-tests-only-32b"
    JWT_SECRET_KEY = "testing-jwt-secret-key-for-unit-tests-only-32b"
    # 测试用最便宜的合法 argon2 参数（memory_cost 最低 8 KiB）。
    # 生产环境不要设置这一项，用 argon2 库的默认值。
    ARGON2_PARAMS = {"time_cost": 1, "memory_cost": 8, "parallelism": 1}
    # 测试环境不应依赖真实 Redis。这里指向一个确定没人监听的端口，
    # 并把超时压到 50ms——否则每次限流/黑名单调用都要等满默认的 2 秒超时，
    # 整套测试会被拖到两分钟以上。
    REDIS_URL = "redis://127.0.0.1:6399/0"
    REDIS_TIMEOUT = 0.05

    # ---- 以下四项让测试**完全不产生外部调用** ----
    # 必须显式覆盖，否则 BaseConfig 会从 .env 读到真实配置：
    # LLM_API_KEY 是真 key，测试会真的去调 DeepSeek（既慢又花钱）；
    # RISK_MODEL_CONFIRM 开着会让每条消息多一次模型调用；
    # RERANK_ENABLED 开着会加载 2.3GB 的重排模型。
    # 指向一个保留端口（9/discard）确保连接立刻失败，而不是等待超时。
    LLM_API_KEY = "testing-key-never-used"
    LLM_BASE_URL = "http://127.0.0.1:9/v1"
    LLM_MAX_RETRIES = 0
    RISK_MODEL_CONFIRM = False
    RERANK_ENABLED = False
    QUERY_REWRITE_ENABLED = False
    # 空字符串会让 indexer 立刻抛 ChromaError，检索随即降级为纯 BM25。
    # 不这样设的话，测试会去连 .env 里配置的真实 Chroma 容器，
    # 测试就变成了"依赖外部服务"。
    CHROMA_HOST = ""


class ProductionConfig(BaseConfig):
    DEBUG = False


_CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def load_config(name: str | None = None):
    """按名称取配置类；未指定时读 APP_ENV，缺省 development。"""
    key = name or os.getenv("APP_ENV", "development")
    return _CONFIGS.get(key, DevelopmentConfig)

