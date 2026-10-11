"""蓝图注册。所有接口统一挂在 /api/v1 下。"""

from __future__ import annotations

from flask import Flask

API_PREFIX = "/api/v1"


def register_blueprints(app: Flask) -> None:
    from app.api.v1.admin_config import bp as admin_config_bp
    from app.api.v1.admin_crisis import bp as admin_crisis_bp
    from app.api.v1.admin_documents import bp as admin_documents_bp
    from app.api.v1.admin_stats import bp as admin_stats_bp
    from app.api.v1.admin_tasks import bp as admin_tasks_bp
    from app.api.v1.auth import bp as auth_bp
    from app.api.v1.conversations import bp as conversations_bp
    from app.api.v1.system import bp as system_bp
    from app.api.v1.users import bp as users_bp

    app.register_blueprint(system_bp, url_prefix=API_PREFIX)
    app.register_blueprint(auth_bp, url_prefix=f"{API_PREFIX}/auth")
    app.register_blueprint(users_bp, url_prefix=f"{API_PREFIX}/users")
    app.register_blueprint(conversations_bp, url_prefix=f"{API_PREFIX}/conversations")
    app.register_blueprint(admin_documents_bp, url_prefix=f"{API_PREFIX}/admin/documents")
    app.register_blueprint(admin_tasks_bp, url_prefix=f"{API_PREFIX}/admin/tasks")
    app.register_blueprint(admin_config_bp, url_prefix=f"{API_PREFIX}/admin/config")
    app.register_blueprint(admin_crisis_bp, url_prefix=f"{API_PREFIX}/admin/crisis-events")
    app.register_blueprint(admin_stats_bp, url_prefix=f"{API_PREFIX}/admin/stats")


__all__ = ["register_blueprints", "API_PREFIX"]

