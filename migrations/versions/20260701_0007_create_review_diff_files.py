"""创建文件级 diff 分析表

Revision ID: 20260701_0007
Revises: 20260701_0006
Create Date: 2026-07-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260701_0007"
down_revision: Union[str, None] = "20260701_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "review_diff_files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("old_path", sa.Text(), nullable=True),
        sa.Column("new_path", sa.Text(), nullable=True),
        sa.Column("change_type", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=64), nullable=False),
        sa.Column("extension", sa.String(length=32), nullable=True),
        sa.Column("directory", sa.Text(), nullable=True),
        sa.Column("additions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("deletions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_changes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("risk_domains", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_large_file", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("analysis_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["review_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_diff_files_task_id", "review_diff_files", ["task_id"])
    op.create_index("ix_review_diff_files_change_type", "review_diff_files", ["change_type"])
    op.create_index("ix_review_diff_files_language", "review_diff_files", ["language"])
    op.create_index("ix_review_diff_files_extension", "review_diff_files", ["extension"])


def downgrade() -> None:
    op.drop_index("ix_review_diff_files_extension", table_name="review_diff_files")
    op.drop_index("ix_review_diff_files_language", table_name="review_diff_files")
    op.drop_index("ix_review_diff_files_change_type", table_name="review_diff_files")
    op.drop_index("ix_review_diff_files_task_id", table_name="review_diff_files")
    op.drop_table("review_diff_files")
