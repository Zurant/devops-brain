"""创建 GitLab 评论回写记录表

Revision ID: 20260701_0003
Revises: 20260701_0002
Create Date: 2026-07-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260701_0003"
down_revision: Union[str, None] = "20260701_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gitlab_comment_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("mr_iid", sa.String(length=128), nullable=False),
        sa.Column("comment_body", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["review_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gitlab_comment_records_project_id", "gitlab_comment_records", ["project_id"])
    op.create_index("ix_gitlab_comment_records_source", "gitlab_comment_records", ["source"])
    op.create_index("ix_gitlab_comment_records_success", "gitlab_comment_records", ["success"])
    op.create_index("ix_gitlab_comment_records_task_id", "gitlab_comment_records", ["task_id"])
    op.create_index("ix_gitlab_comment_records_thread_id", "gitlab_comment_records", ["thread_id"])


def downgrade() -> None:
    op.drop_index("ix_gitlab_comment_records_thread_id", table_name="gitlab_comment_records")
    op.drop_index("ix_gitlab_comment_records_task_id", table_name="gitlab_comment_records")
    op.drop_index("ix_gitlab_comment_records_success", table_name="gitlab_comment_records")
    op.drop_index("ix_gitlab_comment_records_source", table_name="gitlab_comment_records")
    op.drop_index("ix_gitlab_comment_records_project_id", table_name="gitlab_comment_records")
    op.drop_table("gitlab_comment_records")
