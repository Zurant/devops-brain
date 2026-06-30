"""创建企业化审查核心表

Revision ID: 20260630_0001
Revises: 
Create Date: 2026-06-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260630_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "review_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("thread_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("mr_iid", sa.String(length=128), nullable=False),
        sa.Column("mr_url", sa.Text(), nullable=True),
        sa.Column("source_branch", sa.String(length=255), nullable=True),
        sa.Column("target_branch", sa.String(length=255), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("final_risk_level", sa.String(length=16), nullable=True),
        sa.Column("summary_report", sa.Text(), nullable=True),
        sa.Column("final_comment", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id"),
    )
    op.create_index("ix_review_tasks_final_risk_level", "review_tasks", ["final_risk_level"])
    op.create_index("ix_review_tasks_project_id", "review_tasks", ["project_id"])
    op.create_index("ix_review_tasks_status", "review_tasks", ["status"])
    op.create_index("ix_review_tasks_thread_id", "review_tasks", ["thread_id"])

    op.create_table(
        "agent_reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("risk", sa.String(length=16), nullable=True),
        sa.Column("issues", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("token_usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["review_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_reviews_agent_name", "agent_reviews", ["agent_name"])
    op.create_index("ix_agent_reviews_risk", "agent_reviews", ["risk"])
    op.create_index("ix_agent_reviews_task_id", "agent_reviews", ["task_id"])

    op.create_table(
        "approval_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("operator", sa.String(length=128), nullable=True),
        sa.Column("original_comment", sa.Text(), nullable=True),
        sa.Column("modified_comment", sa.Text(), nullable=True),
        sa.Column("comment_posted", sa.Boolean(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["review_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_records_decision", "approval_records", ["decision"])
    op.create_index("ix_approval_records_task_id", "approval_records", ["task_id"])
    op.create_index("ix_approval_records_thread_id", "approval_records", ["thread_id"])


def downgrade() -> None:
    op.drop_index("ix_approval_records_thread_id", table_name="approval_records")
    op.drop_index("ix_approval_records_task_id", table_name="approval_records")
    op.drop_index("ix_approval_records_decision", table_name="approval_records")
    op.drop_table("approval_records")

    op.drop_index("ix_agent_reviews_task_id", table_name="agent_reviews")
    op.drop_index("ix_agent_reviews_risk", table_name="agent_reviews")
    op.drop_index("ix_agent_reviews_agent_name", table_name="agent_reviews")
    op.drop_table("agent_reviews")

    op.drop_index("ix_review_tasks_thread_id", table_name="review_tasks")
    op.drop_index("ix_review_tasks_status", table_name="review_tasks")
    op.drop_index("ix_review_tasks_project_id", table_name="review_tasks")
    op.drop_index("ix_review_tasks_final_risk_level", table_name="review_tasks")
    op.drop_table("review_tasks")
