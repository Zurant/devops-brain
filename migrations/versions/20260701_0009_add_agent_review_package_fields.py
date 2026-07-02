"""为 Agent 审查结果增加审查包关联

Revision ID: 20260701_0009
Revises: 20260701_0008
Create Date: 2026-07-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260701_0009"
down_revision: Union[str, None] = "20260701_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_reviews", sa.Column("package_id", sa.Integer(), nullable=True))
    op.add_column("agent_reviews", sa.Column("package_key", sa.String(length=255), nullable=True))
    op.add_column("agent_reviews", sa.Column("file_paths", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("agent_reviews", sa.Column("risk_domains", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_foreign_key(
        "fk_agent_reviews_package_id_review_packages",
        "agent_reviews",
        "review_packages",
        ["package_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_agent_reviews_package_id", "agent_reviews", ["package_id"])
    op.create_index("ix_agent_reviews_package_key", "agent_reviews", ["package_key"])


def downgrade() -> None:
    op.drop_index("ix_agent_reviews_package_key", table_name="agent_reviews")
    op.drop_index("ix_agent_reviews_package_id", table_name="agent_reviews")
    op.drop_constraint("fk_agent_reviews_package_id_review_packages", "agent_reviews", type_="foreignkey")
    op.drop_column("agent_reviews", "risk_domains")
    op.drop_column("agent_reviews", "file_paths")
    op.drop_column("agent_reviews", "package_key")
    op.drop_column("agent_reviews", "package_id")
