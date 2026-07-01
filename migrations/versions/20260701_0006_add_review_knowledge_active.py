"""为历史审查经验增加启用状态

Revision ID: 20260701_0006
Revises: 20260701_0005
Create Date: 2026-07-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260701_0006"
down_revision: Union[str, None] = "20260701_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "review_knowledge",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_review_knowledge_is_active", "review_knowledge", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_review_knowledge_is_active", table_name="review_knowledge")
    op.drop_column("review_knowledge", "is_active")
