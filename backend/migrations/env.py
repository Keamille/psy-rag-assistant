"""Alembic 运行环境。

以 Flask 应用上下文运行，target_metadata 取自 app.extensions.db.metadata
（由 app.models 导入的 9 张表填充），因此 autogenerate 能采集到全部表结构。
"""

from __future__ import annotations

import logging
from logging.config import fileConfig

from alembic import context
from flask import current_app

from app import create_app
from app.extensions import db
from app import models

config = context.config

if config.config_file_name is not None:
    try:
        fileConfig(config.config_file_name)
    except Exception:  # noqa: BLE001 - 日志配置缺失不应阻止迁移
        pass

logger = logging.getLogger("alembic.env")

target_metadata = db.metadata


def _get_engine():
    """优先使用 Flask 配置里的连接串，其次回退到 alembic.ini。"""
    app = current_app._get_current_object()
    url = app.config.get("SQLALCHEMY_DATABASE_URI")
    if not url:
        url = config.get_main_option("sqlalchemy.url")

    # Flask-SQLAlchemy 3.x 通过 app.extensions 暴露引擎
    try:
        from app.extensions import db as _db

        with app.app_context():
            return _db.engine
    except Exception:  # noqa: BLE001
        from sqlalchemy import create_engine

        return create_engine(url, future=True)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = _get_engine()
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite 改表必须走 batch 模式
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


def run_migrations_with_app() -> None:
    app = create_app()
    with app.app_context():
        if context.is_offline_mode():
            run_migrations_offline()
        else:
            run_migrations_online()


run_migrations_with_app()

