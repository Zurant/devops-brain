"""创建审查计划和审查包表

Revision ID: 20260701_0008
Revises: 20260701_0007
Create Date: 2026-07-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260701_0008"
down_revision: Union[str, None] = "20260701_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "review_plans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("mr_type", sa.String(length=64), nullable=False),
        sa.Column("review_strategy", sa.String(length=64), nullable=False),
        sa.Column("approval_policy", sa.String(length=64), nullable=False),
        sa.Column("required_agents", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("risk_domains", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("file_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_changes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("package_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_large_mr", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("plan_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["review_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_plans_task_id", "review_plans", ["task_id"])
    op.create_index("ix_review_plans_mr_type", "review_plans", ["mr_type"])
    op.create_index("ix_review_plans_review_strategy", "review_plans", ["review_strategy"])
    op.create_index("ix_review_plans_approval_policy", "review_plans", ["approval_policy"])

    op.create_table(
        "review_packages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("package_key", sa.String(length=255), nullable=False),
        sa.Column("package_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("directory", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=64), nullable=True),
        sa.Column("risk_domains", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("file_paths", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("selected_agents", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("additions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("deletions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_changes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("priority", sa.Integer(), server_default="50", nullable=False),
        sa.Column("requires_human", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("package_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["review_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["review_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_packages_task_id", "review_packages", ["task_id"])
    op.create_index("ix_review_packages_plan_id", "review_packages", ["plan_id"])
    op.create_index("ix_review_packages_package_key", "review_packages", ["package_key"])
    op.create_index("ix_review_packages_package_type", "review_packages", ["package_type"])
    op.create_index("ix_review_packages_language", "review_packages", ["language"])


def downgrade() -> None:
    op.drop_index("ix_review_packages_language", table_name="review_packages")
    op.drop_index("ix_review_packages_package_type", table_name="review_packages")
    op.drop_index("ix_review_packages_package_key", table_name="review_packages")
    op.drop_index("ix_review_packages_plan_id", table_name="review_packages")
    op.drop_index("ix_review_packages_task_id", table_name="review_packages")
    op.drop_table("review_packages")

    op.drop_index("ix_review_plans_approval_policy", table_name="review_plans")
    op.drop_index("ix_review_plans_review_strategy", table_name="review_plans")
    op.drop_index("ix_review_plans_mr_type", table_name="review_plans")
    op.drop_index("ix_review_plans_task_id", table_name="review_plans")
    op.drop_table("review_plans")
