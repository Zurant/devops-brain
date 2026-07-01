"""创建历史审查经验库表

Revision ID: 20260701_0005
Revises: 20260701_0004
Create Date: 2026-07-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from src.db.types import PortableJSONB


revision: str = "20260701_0005"
down_revision: Union[str, None] = "20260701_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "review_knowledge",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("issue_type", sa.String(length=128), nullable=False),
        sa.Column("risk", sa.String(length=16), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("suggestion", sa.Text(), nullable=True),
        sa.Column("source_task_id", sa.Integer(), nullable=True),
        sa.Column("source_thread_id", sa.String(length=64), nullable=True),
        sa.Column("source_agent", sa.String(length=64), nullable=True),
        sa.Column("tags", PortableJSONB(), nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_task_id"], ["review_tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_knowledge_created_by", "review_knowledge", ["created_by"])
    op.create_index("ix_review_knowledge_issue_type", "review_knowledge", ["issue_type"])
    op.create_index("ix_review_knowledge_risk", "review_knowledge", ["risk"])
    op.create_index("ix_review_knowledge_source_agent", "review_knowledge", ["source_agent"])
    op.create_index("ix_review_knowledge_source_task_id", "review_knowledge", ["source_task_id"])
    op.create_index("ix_review_knowledge_source_thread_id", "review_knowledge", ["source_thread_id"])


def downgrade() -> None:
    op.drop_index("ix_review_knowledge_source_thread_id", table_name="review_knowledge")
    op.drop_index("ix_review_knowledge_source_task_id", table_name="review_knowledge")
    op.drop_index("ix_review_knowledge_source_agent", table_name="review_knowledge")
    op.drop_index("ix_review_knowledge_risk", table_name="review_knowledge")
    op.drop_index("ix_review_knowledge_issue_type", table_name="review_knowledge")
    op.drop_index("ix_review_knowledge_created_by", table_name="review_knowledge")
    op.drop_table("review_knowledge")
