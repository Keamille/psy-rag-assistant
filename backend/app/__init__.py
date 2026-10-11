"""应用工厂。"""

from __future__ import annotations

import os

from flask import Flask

from app.config import load_config
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.request_id import register_request_id
from app.extensions import cors, db, jwt, migrate, redis_store


def _ensure_sqlite_dir(app: Flask) -> None:
    """SQLite 文件所在目录不存在时，SQLAlchemy 会直接报错，这里提前创建。

    注意：Flask-SQLAlchemy 3.x 会把**相对路径**解析到 app.instance_path 下
    （不是当前工作目录），所以这里必须按同一规则换算，否则会出现在
    另一个目录建了文件夹、真正连接时仍然 "unable to open database file"。
    """
    uri: str = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not uri.startswith("sqlite:///"):
        return
    path = uri.replace("sqlite:///", "", 1)
    if not path or path.startswith(":memory:"):
        return
    if path.startswith("/") and os.name == "nt":
        # Windows 下绝对路径写法 sqlite:///D:/x/y.db 会被解析成 /D:/x/y.db
        path = path.lstrip("/")
    if not os.path.isabs(path):
        os.makedirs(app.instance_path, exist_ok=True)
        path = os.path.join(app.instance_path, path)
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def _configure_model_cache(app: Flask) -> None:
    """把模型缓存目录解析成绝对路径并写回环境变量。

    必须在任何模型加载之前执行。做两件事：

    1. 相对路径按**仓库根目录**（backend 的上一级）解析，而不是当前工作目录——
       否则从 backend/ 启动时会去找 backend/models/，从仓库根启动时才对。
    2. 同时设置 HF_HOME 与 HF_HUB_CACHE：
       HF_HOME 决定 HF_HOME/hub 这一层，HF_HUB_CACHE 直接指向 models--* 所在目录。
       两个都设置，无论 huggingface_hub 的哪个版本优先读哪个变量都能命中。
    """
    raw = app.config.get("MODEL_CACHE_DIR") or ""
    if not raw:
        return
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    cache_dir = raw if os.path.isabs(raw) else os.path.join(repo_root, raw)
    os.makedirs(cache_dir, exist_ok=True)
    os.environ["HF_HOME"] = cache_dir
    os.environ["HF_HUB_CACHE"] = os.path.join(cache_dir, "hub")

    # .env 里把 HF_ENDPOINT 留空表示"走官方源"。但空字符串会留在 environ 里，
    # huggingface_hub 可能把它当成一个非法端点去请求，所以这里显式删掉。
    if not os.environ.get("HF_ENDPOINT", "").strip():
        os.environ.pop("HF_ENDPOINT", None)
        # 光删环境变量不够：huggingface_hub 在**导入时**就把 HF_ENDPOINT 读进
        # constants.ENDPOINT 了。空串会拼出 "/BAAI/bge-m3/resolve/..." 这种
        # 缺少 scheme 与 host 的地址，导致检索与重排**静默降级**——
        # 表面仍能问答，但答案没经过语义检索。
        try:
            import huggingface_hub.constants as hf_constants

            if not (hf_constants.ENDPOINT or "").strip():
                hf_constants.ENDPOINT = "https://huggingface.co"
        except Exception:  # noqa: BLE001
            # 没装 huggingface_hub 时跳过（只影响模型缓存目录的配置）
            pass


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(load_config(config_name))

    configure_logging(app)
    _ensure_sqlite_dir(app)
    _configure_model_cache(app)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})
    redis_store.init_app(app)

    register_request_id(app)
    register_error_handlers(app)

    # 令牌黑名单校验：注销后让旧令牌立即失效
    from app.core.security import register_jwt_blocklist

    register_jwt_blocklist(jwt)

    from app.api import register_blueprints

    register_blueprints(app)

    # 模型预热：真正加载 BGE 权重。默认关闭（PRELOAD_MODELS=0），
    # 因为两个模型常驻约 4.6GB，开发期没必要。任何异常都不应阻止进程启动。
    if app.config.get("PRELOAD_MODELS"):
        try:
            from app.rag.embedder import warmup

            warmup()
        except Exception as exc:  # noqa: BLE001 - 启动阶段必须容错
            app.logger.warning("模型预热跳过：%s", exc)

    app.logger.info(
        "应用初始化完成 env=%s provider=%s",
        app.config.get("APP_ENV"),
        app.config.get("LLM_PROVIDER"),
    )
    return app


__all__ = ["create_app"]

