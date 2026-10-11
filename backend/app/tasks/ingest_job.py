"""文档入库任务（RQ 入口）。

worker 容器执行：`python -m rq.cli worker --url ... ingest`

任务体本身很薄——真正的逻辑在 `services/document_service.run_ingest` 里。
这样拆是为了让入库流程**可以被同步调用**：测试里直接调 run_ingest 就能验证
整条链路，不需要起一个 worker 再等它跑完。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def ingest_document(document_id: int, task_id: str | None = None) -> dict:
    """RQ 任务入口。异常在 run_ingest 内部已经消化，这里只负责拿应用上下文。"""
    from app import create_app
    from app.services.document_service import run_ingest

    app = create_app()
    with app.app_context():
        logger.info("开始处理文档入库 document_id=%s task_id=%s", document_id, task_id)
        return run_ingest(document_id, task_id=task_id)

