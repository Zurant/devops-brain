from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from src.db.base import Base
from src.models import AgentReview, ApprovalRecord, ReviewTask


def test_enterprise_core_tables_are_registered():
    tables = Base.metadata.tables

    assert "review_tasks" in tables
    assert "agent_reviews" in tables
    assert "approval_records" in tables


def test_review_task_core_columns():
    columns = ReviewTask.__table__.columns

    assert columns["thread_id"].unique is True
    assert columns["project_id"].index is True
    assert columns["status"].index is True
    assert columns["final_risk_level"].index is True


def test_agent_review_and_approval_foreign_keys():
    agent_fk = next(iter(AgentReview.__table__.columns["task_id"].foreign_keys))
    approval_fk = next(iter(ApprovalRecord.__table__.columns["task_id"].foreign_keys))

    assert str(agent_fk.column) == "review_tasks.id"
    assert str(approval_fk.column) == "review_tasks.id"


def test_models_compile_for_postgresql():
    dialect = postgresql.dialect()

    for table in [ReviewTask.__table__, AgentReview.__table__, ApprovalRecord.__table__]:
        sql = str(CreateTable(table).compile(dialect=dialect))
        assert f"CREATE TABLE {table.name}" in sql
