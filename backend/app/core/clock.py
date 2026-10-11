"""时间工具。

为什么需要它：Python 3.12 起 `datetime.utcnow()` 已被标记为废弃，
而 SQLite 的 `CURRENT_TIMESTAMP` 返回的是**朴素 UTC 时间**（不带时区）。
为了让 Python 侧写入的时间与数据库默认值语义一致，这里统一返回朴素 UTC。
"""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """返回当前的朴素 UTC 时间（naive datetime）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


__all__ = ["utcnow"]

