from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from src.api.globals import pending_reviews
from src.api.server import app
from src.db.base import Base
from src.db.session import get_db
from src.models import AgentReview, ApprovalRecord, AuditLog, GitLabCommentRecord, ReviewKnowledge, ReviewTask


client = TestClient(app)


def build_test_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def override_db(session_factory):
    def _get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db


def clear_override_db():
    app.dependency_overrides.pop(get_db, None)


def build_graph_mock(final_comment: str = "AI 生成的评论"):
    graph = Mock()
    paused_state = SimpleNamespace(next=("human_review",), values={})
    finished_state = SimpleNamespace(
        next=(),
        values={
            "project_id": "1234",
            "mr_id": "42",
            "final_comment": final_comment,
        },
    )
    graph.get_state.side_effect = [paused_state, finished_state]
    return graph


def test_resume_approve_posts_final_comment():
    session_factory = build_test_session()
    override_db(session_factory)
    db = session_factory()
    db.add(ReviewTask(thread_id="thread-approve", project_id="1234", mr_iid="42", status="waiting_human", final_comment="AI 生成的评论"))
    db.commit()
    db.close()
    pending_reviews["thread-approve"] = {"mr_id": "42"}
    graph = build_graph_mock()

    try:
        with patch("src.api.routes.approval.graph", graph), patch("src.tools.gitlab_client.post_mr_comment") as post_comment:
            res = client.post(
                "/api/resume",
                json={"thread_id": "thread-approve", "decision": "approve"},
                headers={"X-Operator": "alice"},
            )
    finally:
        clear_override_db()

    assert res.status_code == 200
    assert res.json()["comment_posted"] is True
    graph.update_state.assert_called_once_with(
        {"configurable": {"thread_id": "thread-approve"}},
        {"human_decision": "approve"},
    )
    post_comment.assert_called_once_with("1234", "42", "AI 生成的评论")
    assert "thread-approve" not in pending_reviews

    db = session_factory()
    task = db.query(ReviewTask).filter_by(thread_id="thread-approve").one()
    record = db.query(ApprovalRecord).filter_by(thread_id="thread-approve").one()
    comment_record = db.query(GitLabCommentRecord).filter_by(thread_id="thread-approve").one()
    audit_log = db.query(AuditLog).filter_by(resource_id="thread-approve").one()
    assert task.status == "completed"
    assert record.decision == "approve"
    assert record.operator == "alice"
    assert record.comment_posted is True
    assert comment_record.source == "approve"
    assert comment_record.success is True
    assert audit_log.actor == "alice"
    assert audit_log.action == "review.approve"
    db.close()


def test_resume_reject_finishes_without_posting_comment():
    session_factory = build_test_session()
    override_db(session_factory)
    db = session_factory()
    db.add(ReviewTask(thread_id="thread-reject", project_id="1234", mr_iid="42", status="waiting_human", final_comment="AI 生成的评论"))
    db.commit()
    db.close()
    pending_reviews["thread-reject"] = {"mr_id": "42"}
    graph = build_graph_mock()

    try:
        with patch("src.api.routes.approval.graph", graph), patch("src.tools.gitlab_client.post_mr_comment") as post_comment:
            res = client.post("/api/resume", json={"thread_id": "thread-reject", "decision": "reject"})
    finally:
        clear_override_db()

    assert res.status_code == 200
    assert res.json()["comment_posted"] is False
    graph.update_state.assert_called_once_with(
        {"configurable": {"thread_id": "thread-reject"}},
        {"human_decision": "reject"},
    )
    post_comment.assert_not_called()
    assert "thread-reject" not in pending_reviews

    db = session_factory()
    task = db.query(ReviewTask).filter_by(thread_id="thread-reject").one()
    record = db.query(ApprovalRecord).filter_by(thread_id="thread-reject").one()
    assert task.status == "rejected"
    assert record.decision == "reject"
    assert record.comment_posted is False
    db.close()


def test_resume_modify_posts_modified_comment():
    session_factory = build_test_session()
    override_db(session_factory)
    db = session_factory()
    db.add(ReviewTask(thread_id="thread-modify", project_id="1234", mr_iid="42", status="waiting_human", final_comment="AI 生成的评论"))
    db.commit()
    db.close()
    pending_reviews["thread-modify"] = {"mr_id": "42"}
    graph = build_graph_mock(final_comment="人工修改后的评论")

    try:
        with patch("src.api.routes.approval.graph", graph), patch("src.tools.gitlab_client.post_mr_comment") as post_comment:
            res = client.post(
                "/api/resume",
                json={
                    "thread_id": "thread-modify",
                    "decision": "modify",
                    "modified_comment": "人工修改后的评论",
                },
            )
    finally:
        clear_override_db()

    assert res.status_code == 200
    assert res.json()["comment_posted"] is True
    graph.update_state.assert_called_once_with(
        {"configurable": {"thread_id": "thread-modify"}},
        {"human_decision": "modify", "final_comment": "人工修改后的评论"},
    )
    post_comment.assert_called_once_with("1234", "42", "人工修改后的评论")
    assert "thread-modify" not in pending_reviews

    db = session_factory()
    task = db.query(ReviewTask).filter_by(thread_id="thread-modify").one()
    record = db.query(ApprovalRecord).filter_by(thread_id="thread-modify").one()
    comment_record = db.query(GitLabCommentRecord).filter_by(thread_id="thread-modify").one()
    assert task.status == "completed"
    assert task.final_comment == "人工修改后的评论"
    assert record.decision == "modify"
    assert record.modified_comment == "人工修改后的评论"
    assert comment_record.comment_body == "人工修改后的评论"
    assert comment_record.source == "modify"
    db.close()


def test_resume_modify_requires_modified_comment():
    session_factory = build_test_session()
    override_db(session_factory)
    graph = build_graph_mock()

    try:
        with patch("src.api.routes.approval.graph", graph):
            res = client.post("/api/resume", json={"thread_id": "thread-modify-invalid", "decision": "modify"})
    finally:
        clear_override_db()

    assert res.status_code == 400
    assert res.json()["detail"] == "modified_comment is required when decision is modify"


def test_resume_rejects_invalid_decision():
    session_factory = build_test_session()
    override_db(session_factory)
    graph = build_graph_mock()

    try:
        with patch("src.api.routes.approval.graph", graph):
            res = client.post("/api/resume", json={"thread_id": "thread-invalid", "decision": "skip"})
    finally:
        clear_override_db()

    assert res.status_code == 400
    assert res.json()["detail"] == "decision must be approve, reject or modify"


def test_pending_and_history_read_from_database():
    session_factory = build_test_session()
    override_db(session_factory)
    db = session_factory()
    waiting = ReviewTask(
        thread_id="thread-waiting",
        project_id="1234",
        mr_iid="42",
        status="waiting_human",
        final_risk_level="HIGH",
        final_comment="待审批评论",
    )
    done = ReviewTask(
        thread_id="thread-done",
        project_id="1234",
        mr_iid="43",
        status="completed",
        final_risk_level="LOW",
        final_comment="已完成评论",
    )
    db.add_all([waiting, done])
    db.commit()
    db.add(ApprovalRecord(task_id=done.id, thread_id="thread-done", decision="approve", comment_posted=True))
    db.commit()
    db.close()

    try:
        pending_res = client.get("/api/pending")
        history_res = client.get("/api/history")
    finally:
        clear_override_db()

    assert pending_res.status_code == 200
    assert "thread-waiting" in pending_res.json()
    assert "thread-done" not in pending_res.json()
    assert history_res.status_code == 200
    history = history_res.json()
    assert {item["thread_id"] for item in history} == {"thread-waiting", "thread-done"}
    assert next(item for item in history if item["thread_id"] == "thread-done")["approval_decision"] == "approve"


def test_history_supports_enterprise_filters():
    session_factory = build_test_session()
    override_db(session_factory)
    db = session_factory()
    db.add_all(
        [
            ReviewTask(
                thread_id="thread-high-waiting",
                project_id="1234",
                mr_iid="42",
                status="waiting_human",
                final_risk_level="HIGH",
            ),
            ReviewTask(
                thread_id="thread-low-completed",
                project_id="1234",
                mr_iid="43",
                status="completed",
                final_risk_level="LOW",
            ),
            ReviewTask(
                thread_id="thread-high-other-project",
                project_id="5678",
                mr_iid="44",
                status="completed",
                final_risk_level="HIGH",
            ),
        ]
    )
    db.commit()
    db.close()

    try:
        status_res = client.get("/api/history?status=completed")
        risk_project_res = client.get("/api/history?risk=HIGH&project_id=1234")
    finally:
        clear_override_db()

    assert status_res.status_code == 200
    assert {item["thread_id"] for item in status_res.json()} == {
        "thread-low-completed",
        "thread-high-other-project",
    }
    assert risk_project_res.status_code == 200
    assert [item["thread_id"] for item in risk_project_res.json()] == ["thread-high-waiting"]


def test_review_detail_returns_audit_records():
    session_factory = build_test_session()
    override_db(session_factory)
    db = session_factory()
    task = ReviewTask(
        thread_id="thread-detail",
        project_id="1234",
        mr_iid="42",
        status="completed",
        final_risk_level="MEDIUM",
        final_comment="最终评论",
        initial_state={
            "diff_content": "# File: src/app.py\n@@\n-old_call()\n+new_call()\n+audit_log()\n# File: README.md\n@@\n-old\n+new"
        },
    )
    db.add(task)
    db.commit()
    db.add_all(
        [
            AgentReview(task_id=task.id, agent_name="security", risk="HIGH", issues=[{"title": "SQL 注入"}]),
            ApprovalRecord(task_id=task.id, thread_id="thread-detail", decision="approve", comment_posted=True),
            GitLabCommentRecord(
                task_id=task.id,
                thread_id="thread-detail",
                project_id="1234",
                mr_iid="42",
                comment_body="最终评论",
                source="approve",
                success=True,
            ),
            AuditLog(
                actor="alice",
                action="review.approve",
                resource_type="review_task",
                resource_id="thread-detail",
                detail={"comment_posted": True},
            ),
            ReviewKnowledge(
                issue_type="SQL 注入",
                risk="HIGH",
                title="参数拼接 SQL",
                description="发现字符串拼接 SQL",
                suggestion="使用参数化查询",
                source_task_id=task.id,
                source_thread_id="thread-detail",
                source_agent="security",
                created_by="alice",
            ),
        ]
    )
    db.commit()
    db.close()

    try:
        res = client.get("/api/reviews/thread-detail")
    finally:
        clear_override_db()

    assert res.status_code == 200
    body = res.json()
    assert body["thread_id"] == "thread-detail"
    assert body["diff_summary"]["file_count"] == 2
    assert body["diff_summary"]["additions"] == 3
    assert body["diff_summary"]["deletions"] == 2
    assert body["diff_summary"]["files"][0]["path"] == "src/app.py"
    assert body["agent_reviews"][0]["agent_name"] == "security"
    assert body["approval_records"][0]["decision"] == "approve"
    assert body["gitlab_comment_records"][0]["success"] is True
    assert body["knowledge_entries"][0]["issue_type"] == "SQL 注入"
    assert body["audit_logs"][0]["actor"] == "alice"


def test_audit_logs_can_be_queried():
    session_factory = build_test_session()
    override_db(session_factory)
    db = session_factory()
    db.add_all(
        [
            AuditLog(actor="alice", action="review.approve", resource_type="review_task", resource_id="thread-a", detail={}),
            AuditLog(actor="bob", action="review.reject", resource_type="review_task", resource_id="thread-b", detail={}),
        ]
    )
    db.commit()
    db.close()

    try:
        res = client.get("/api/audit-logs?actor=alice")
    finally:
        clear_override_db()

    assert res.status_code == 200
    assert [item["resource_id"] for item in res.json()] == ["thread-a"]


def test_knowledge_can_be_created_and_queried():
    session_factory = build_test_session()
    override_db(session_factory)

    try:
        create_res = client.post(
            "/api/knowledge",
            json={
                "issue_type": "SQL 注入",
                "risk": "HIGH",
                "title": "参数拼接 SQL",
                "description": "发现用户输入直接拼接 SQL。",
                "suggestion": "改为参数化查询。",
                "tags": ["security"],
            },
            headers={"X-Operator": "alice"},
        )
        query_res = client.get("/api/knowledge?risk=HIGH")
    finally:
        clear_override_db()

    assert create_res.status_code == 200
    assert create_res.json()["created_by"] == "alice"
    assert create_res.json()["issue_type"] == "SQL 注入"
    assert query_res.status_code == 200
    assert query_res.json()[0]["suggestion"] == "改为参数化查询。"

    db = session_factory()
    audit_log = db.query(AuditLog).filter_by(action="knowledge.create").one()
    assert audit_log.actor == "alice"
    db.close()


def test_review_issues_can_be_promoted_to_knowledge():
    session_factory = build_test_session()
    override_db(session_factory)
    db = session_factory()
    task = ReviewTask(thread_id="thread-knowledge", project_id="1234", mr_iid="42", status="completed", final_risk_level="HIGH")
    db.add(task)
    db.commit()
    db.add_all(
        [
            AgentReview(
                task_id=task.id,
                agent_name="security",
                risk="HIGH",
                issues=[
                    {
                        "title": "SQL 注入风险",
                        "type": "sql_injection",
                        "description": "登录接口拼接 SQL。",
                        "suggestion": "使用参数化查询。",
                    }
                ],
            ),
            AgentReview(task_id=task.id, agent_name="quality", risk="LOW", issues=[]),
        ]
    )
    db.commit()
    db.close()

    try:
        res = client.post(
            "/api/reviews/thread-knowledge/knowledge",
            json={"tags": ["人工确认"]},
            headers={"X-Operator": "bob"},
        )
    finally:
        clear_override_db()

    assert res.status_code == 200
    body = res.json()
    assert body["created_count"] == 1
    assert body["items"][0]["issue_type"] == "sql_injection"
    assert body["items"][0]["created_by"] == "bob"

    db = session_factory()
    knowledge = db.query(ReviewKnowledge).filter_by(source_thread_id="thread-knowledge").one()
    audit_log = db.query(AuditLog).filter_by(resource_id="thread-knowledge").one()
    assert knowledge.source_agent == "security"
    assert knowledge.tags == ["人工确认"]
    assert audit_log.action == "knowledge.create_from_review"
    db.close()


def test_review_knowledge_title_falls_back_to_description():
    session_factory = build_test_session()
    override_db(session_factory)
    db = session_factory()
    task = ReviewTask(thread_id="thread-description-only", project_id="1234", mr_iid="42", status="completed")
    db.add(task)
    db.commit()
    db.add(
        AgentReview(
            task_id=task.id,
            agent_name="quality",
            risk="MEDIUM",
            issues=[{"description": "这个函数承担了过多职责，后续维护成本较高，建议拆分。"}],
        )
    )
    db.commit()
    db.close()

    try:
        res = client.post("/api/reviews/thread-description-only/knowledge")
    finally:
        clear_override_db()

    assert res.status_code == 200
    item = res.json()["items"][0]
    assert item["title"] == "这个函数承担了过多职责，后续维护成本较高，建议拆分。"
    assert item["description"] == "这个函数承担了过多职责，后续维护成本较高，建议拆分。"


def test_resume_records_failed_gitlab_comment():
    session_factory = build_test_session()
    override_db(session_factory)
    db = session_factory()
    db.add(ReviewTask(thread_id="thread-post-fail", project_id="1234", mr_iid="42", status="waiting_human", final_comment="AI 生成的评论"))
    db.commit()
    db.close()
    pending_reviews["thread-post-fail"] = {"mr_id": "42"}
    graph = build_graph_mock()

    try:
        with patch("src.api.routes.approval.graph", graph), patch(
            "src.tools.gitlab_client.post_mr_comment", side_effect=RuntimeError("GitLab 不可用")
        ):
            res = client.post("/api/resume", json={"thread_id": "thread-post-fail", "decision": "approve"})
    finally:
        clear_override_db()

    assert res.status_code == 502
    db = session_factory()
    record = db.query(GitLabCommentRecord).filter_by(thread_id="thread-post-fail").one()
    assert record.success is False
    assert record.error_message == "GitLab 不可用"
    db.close()


def test_retry_failed_gitlab_comment_posts_again():
    session_factory = build_test_session()
    override_db(session_factory)
    db = session_factory()
    task = ReviewTask(thread_id="thread-comment-retry", project_id="1234", mr_iid="42", status="completed")
    db.add(task)
    db.commit()
    db.add(
        GitLabCommentRecord(
            task_id=task.id,
            thread_id="thread-comment-retry",
            project_id="1234",
            mr_iid="42",
            comment_body="待重试评论",
            source="approve",
            success=False,
            error_message="上次失败",
        )
    )
    db.commit()
    db.close()

    try:
        with patch("src.tools.gitlab_client.post_mr_comment") as post_comment:
            res = client.post("/api/reviews/thread-comment-retry/comments/retry", headers={"X-Operator": "alice"})
    finally:
        clear_override_db()

    assert res.status_code == 200
    assert res.json() == {"status": "comment_posted", "thread_id": "thread-comment-retry"}
    post_comment.assert_called_once_with("1234", "42", "待重试评论")

    db = session_factory()
    records = db.query(GitLabCommentRecord).filter_by(thread_id="thread-comment-retry").order_by(GitLabCommentRecord.id).all()
    assert len(records) == 2
    assert records[-1].source == "retry"
    assert records[-1].success is True
    audit_log = db.query(AuditLog).filter_by(resource_id="thread-comment-retry").one()
    assert audit_log.actor == "alice"
    assert audit_log.action == "gitlab_comment.retry"
    db.close()
