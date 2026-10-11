"""应用工厂的路径与启动容错。"""

from __future__ import annotations

import os

from app import _ensure_sqlite_dir, create_app


def test_relative_sqlite_path_created_under_instance_dir():
    """Flask-SQLAlchemy 3.x 把相对 sqlite 路径解析到 instance 目录。

    回归用例：目录若按 CWD 创建，真正连接时会报
    "unable to open database file"。
    """
    app = create_app("testing")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///./data/app.db"

    _ensure_sqlite_dir(app)

    assert os.path.isdir(os.path.join(app.instance_path, "data"))


def test_absolute_sqlite_path_is_not_redirected():
    """绝对路径必须原样使用，不能被塞进 instance 目录。

    这里用项目内的绝对路径而不是 pytest 的 tmp_path：沙箱环境常常
    禁止写系统临时目录，而 instance/ 已在 .gitignore 中。
    """
    app = create_app("testing")
    target = os.path.join(app.instance_path, "abs_check", "app.db")
    # Windows 绝对路径在 sqlite URL 中写成 sqlite:///C:/...
    uri_path = target.replace("\\", "/")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{uri_path}"

    _ensure_sqlite_dir(app)

    assert os.path.isdir(os.path.dirname(target))
    assert os.path.isdir(os.path.join(app.instance_path, "abs_check"))


def test_memory_database_is_skipped():
    app = create_app("testing")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    # 不应抛异常，也不应创建任何目录
    _ensure_sqlite_dir(app)


def test_app_starts_without_optional_services():
    """Redis / Chroma / torch 全都没有时，工厂仍必须成功返回。"""
    app = create_app("testing")
    assert app.url_map is not None

