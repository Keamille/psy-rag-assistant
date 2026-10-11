"""后台任务进度（开发文档 §7.7）。权限：admin。"""

from __future__ import annotations

from flask import Blueprint

from app.core.errors import ApiError, ErrorCode
from app.core.response import ok
from app.core.security import admin_required
from app.services import document_service

bp = Blueprint("admin_tasks", __name__)


@bp.get("/<task_id>")
@admin_required
def get_task(task_id: str):
    """查询入库任务进度。

    进度存在 Redis 里，TTL 一天。任务太老或 Redis 重启过就会查不到——
    这种情况返回 404 而不是空对象，让前端能明确区分"没有这个任务"
    和"任务还在排队"。
    """
    payload = document_service.get_task(task_id)
    if payload is None:
        raise ApiError(
            ErrorCode.NOT_FOUND,
            "任务不存在或已过期（进度信息保留 24 小时）",
            404,
        )
    return ok(data=payload)

