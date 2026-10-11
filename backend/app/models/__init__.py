"""SQLAlchemy 数据模型（开发文档 §5.2 的 9 张表）。

**这个文件里的 import 不是可有可无的。**
Alembic 的 `target_metadata` 取自 `db.metadata`，而只有被 import 过的模型类
才会注册到 metadata 上。漏掉任何一行 import，`--autogenerate` 就会静默地
生成一个空迁移（`upgrade()` 里只有 `pass`），而不是报错。

模块名与表名对齐（users.py ↔ users 表），便于互相查找。
"""

from __future__ import annotations

from app.extensions import db

from .audit_logs import AuditLog
from .conversation_summaries import ConversationSummary
from .conversations import Conversation
from .crisis_events import CrisisEvent
from .hotline_resources import HotlineResource
from .knowledge_chunks import KnowledgeChunk
from .knowledge_documents import KnowledgeDocument
from .messages import Message
from .users import User

__all__ = [
    "db",
    # 9 张表，缺一不可
    "User",
    "Conversation",
    "Message",
    "ConversationSummary",
    "KnowledgeDocument",
    "KnowledgeChunk",
    "CrisisEvent",
    "AuditLog",
    "HotlineResource",
]
