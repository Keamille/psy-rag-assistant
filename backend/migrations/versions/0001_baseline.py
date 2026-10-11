"""基线迁移：不含任何 DDL。

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-04

作用是让 `alembic upgrade head` 有一个可到达的 HEAD，从而保证 docker-compose
的启动链不会因为"没有迁移可跑"而失败。真正的建表迁移是它的下游 revision。
"""

from alembic import op  # noqa: F401  (后续迁移会用)

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

