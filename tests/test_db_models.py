from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from src.db.base import Base
from src.models import (
    AgentReview,
    ApprovalRecord,
    AuditLog,
    GitLabCommentRecord,
    ReviewDiffFile,
    ReviewKnowledge,
    ReviewPackage,
    ReviewPlan,
    ReviewTask,
)


def test_enterprise_core_tables_are_registered():
    tables = Base.metadata.tables

    assert "review_tasks" in tables
    assert "agent_reviews" in tables
    assert "approval_records" in tables
    assert "audit_logs" in tables
    assert "gitlab_comment_records" in tables
    assert "review_knowledge" in tables
    assert "review_diff_files" in tables
    assert "review_plans" in tables
    assert "review_packages" in tables


def test_review_task_core_columns():
    columns = ReviewTask.__table__.columns

    assert columns["thread_id"].unique is True
    assert columns["project_id"].index is True
    assert columns["status"].index is True
    assert columns["job_id"].index is True
    assert columns["final_risk_level"].index is True
    assert "initial_state" in columns
    assert "retry_count" in columns
    assert "queued_at" in columns
    assert "started_at" in columns
    assert "failed_at" in columns


def test_agent_review_and_approval_foreign_keys():
    agent_fk = next(iter(AgentReview.__table__.columns["task_id"].foreign_keys))
    agent_package_fk = next(iter(AgentReview.__table__.columns["package_id"].foreign_keys))
    approval_fk = next(iter(ApprovalRecord.__table__.columns["task_id"].foreign_keys))
    comment_fk = next(iter(GitLabCommentRecord.__table__.columns["task_id"].foreign_keys))
    knowledge_fk = next(iter(ReviewKnowledge.__table__.columns["source_task_id"].foreign_keys))
    diff_file_fk = next(iter(ReviewDiffFile.__table__.columns["task_id"].foreign_keys))
    plan_fk = next(iter(ReviewPlan.__table__.columns["task_id"].foreign_keys))
    package_task_fk = next(iter(ReviewPackage.__table__.columns["task_id"].foreign_keys))
    package_plan_fk = next(iter(ReviewPackage.__table__.columns["plan_id"].foreign_keys))

    assert str(agent_fk.column) == "review_tasks.id"
    assert str(agent_package_fk.column) == "review_packages.id"
    assert str(approval_fk.column) == "review_tasks.id"
    assert str(comment_fk.column) == "review_tasks.id"
    assert str(knowledge_fk.column) == "review_tasks.id"
    assert str(diff_file_fk.column) == "review_tasks.id"
    assert str(plan_fk.column) == "review_tasks.id"
    assert str(package_task_fk.column) == "review_tasks.id"
    assert str(package_plan_fk.column) == "review_plans.id"


def test_agent_review_package_columns():
    columns = AgentReview.__table__.columns

    assert columns["package_id"].index is True
    assert columns["package_key"].index is True
    assert "file_paths" in columns
    assert "risk_domains" in columns


def test_models_compile_for_postgresql():
    dialect = postgresql.dialect()

    for table in [
        ReviewTask.__table__,
        AgentReview.__table__,
        ApprovalRecord.__table__,
        AuditLog.__table__,
        GitLabCommentRecord.__table__,
        ReviewKnowledge.__table__,
        ReviewDiffFile.__table__,
        ReviewPlan.__table__,
        ReviewPackage.__table__,
    ]:
        sql = str(CreateTable(table).compile(dialect=dialect))
        assert f"CREATE TABLE {table.name}" in sql
