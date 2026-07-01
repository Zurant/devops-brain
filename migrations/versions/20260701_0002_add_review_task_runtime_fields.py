"""增加审查任务运行状态字段

Revision ID: 20260701_0002
Revises: 20260630_0001
Create Date: 2026-07-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from src.db.types import PortableJSONB


revision: str = "20260701_0002"
down_revision: Union[str, None] = "20260630_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("review_tasks", sa.Column("job_id", sa.String(length=64), nullable=True))
    op.add_column("review_tasks", sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("review_tasks", sa.Column("initial_state", PortableJSONB(), nullable=True))
    op.add_column("review_tasks", sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("review_tasks", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("review_tasks", sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_review_tasks_job_id", "review_tasks", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_review_tasks_job_id", table_name="review_tasks")
    op.drop_column("review_tasks", "failed_at")
    op.drop_column("review_tasks", "started_at")
    op.drop_column("review_tasks", "queued_at")
    op.drop_column("review_tasks", "initial_state")
    op.drop_column("review_tasks", "retry_count")
    op.drop_column("review_tasks", "job_id")
