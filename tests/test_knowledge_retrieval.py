from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from src.db.base import Base
from src.models import ReviewKnowledge
from src.services import knowledge_retrieval_service


def build_test_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def test_retrieve_relevant_knowledge_matches_diff_keywords(monkeypatch):
    session_factory = build_test_session()
    db = session_factory()
    db.add_all(
        [
            ReviewKnowledge(
                issue_type="sql_injection",
                risk="HIGH",
                title="SQL 注入风险",
                description="登录接口拼接 SQL，应该使用参数化查询。",
                suggestion="改为参数化查询。",
                source_agent="security",
                created_by="alice",
            ),
            ReviewKnowledge(
                issue_type="naming",
                risk="LOW",
                description="变量命名不清晰。",
                source_agent="quality",
                created_by="alice",
            ),
        ]
    )
    db.commit()
    db.close()
    monkeypatch.setattr(knowledge_retrieval_service, "SessionLocal", session_factory)

    items = knowledge_retrieval_service.retrieve_relevant_knowledge(
        "cursor.execute('SELECT * FROM users WHERE name=' + username)",
        agent_name="security",
    )

    assert len(items) == 1
    assert items[0]["issue_type"] == "sql_injection"
    assert items[0]["risk"] == "HIGH"


def test_retrieve_relevant_knowledge_skips_disabled_items(monkeypatch):
    session_factory = build_test_session()
    db = session_factory()
    db.add(
        ReviewKnowledge(
            issue_type="sql_injection",
            risk="HIGH",
            title="已禁用 SQL 注入经验",
            description="登录接口拼接 SQL，应该使用参数化查询。",
            suggestion="改为参数化查询。",
            source_agent="security",
            is_active=False,
            created_by="alice",
        )
    )
    db.commit()
    db.close()
    monkeypatch.setattr(knowledge_retrieval_service, "SessionLocal", session_factory)

    items = knowledge_retrieval_service.retrieve_relevant_knowledge(
        "cursor.execute('SELECT * FROM users WHERE name=' + username)",
        agent_name="security",
    )

    assert items == []


def test_format_knowledge_prompt_includes_review_experience():
    prompt = knowledge_retrieval_service.format_knowledge_prompt(
        [
            {
                "issue_type": "sql_injection",
                "risk": "HIGH",
                "title": "SQL 注入风险",
                "description": "拼接 SQL。",
                "suggestion": "使用参数化查询。",
            }
        ]
    )

    assert "历史审查经验" in prompt
    assert "SQL 注入风险" in prompt
    assert "使用参数化查询" in prompt
