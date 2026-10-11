"""结构化 JSON 日志。

红线：日志中不得出现用户消息原文、密码、令牌。
需要定位问题时只记录 length / hash / request_id。
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from flask import Flask, g, has_request_context, request


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if has_request_context():
            payload["request_id"] = getattr(g, "request_id", None)
            payload["method"] = request.method
            payload["path"] = request.path
        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(app: Flask) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    level = str(app.config.get("LOG_LEVEL", "INFO")).upper()
    app.logger.handlers = [handler]
    app.logger.setLevel(level)
    app.logger.propagate = False

    for name in ("werkzeug", "sqlalchemy.engine"):
        logging.getLogger(name).setLevel(logging.WARNING)


__all__ = ["configure_logging", "JsonFormatter"]

