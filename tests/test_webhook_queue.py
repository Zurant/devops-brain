from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from src.api.server import app
from src.db.session import get_db
from src.models import GitLabCommentRecord, ReviewTask
from src.services.review_orchestrator import run_review_job
from tests.test_approval_api import build_test_session, clear_override_db, override_db


client = TestClient(app)


def test_webhook_enqueues_review_task():
    session_factory = build_test_session()
    override_db(session_factory)
    queue = Mock()
    queue.enqueue.return_value = SimpleNamespace(id="job-123")

    try:
        with patch("src.api.routes.webhook.get_review_queue", return_value=queue), patch(
            "src.api.routes.webhook.get_mr_changes", return_value="mock diff"
        ):
            res = client.post(
                "/api/webhook",
                json={
                    "project": {"id": 1234},
                    "object_attributes": {
                        "iid": 42,
                        "url": "http://gitlab.local/demo/-/merge_requests/42",
                        "source_branch": "feature/demo",
                        "target_branch": "main",
                        "title": "Demo MR",
                    },
                },
            )
    finally:
        clear_override_db()

    assert res.status_code == 202
    body = res.json()
    assert body["status"] == "queued"
    assert body["job_id"] == "job-123"
    queue.enqueue.assert_called_once()

    db = session_factory()
    task = db.query(ReviewTask).filter_by(thread_id=body["thread_id"]).one()
    assert task.status == "queued"
    assert task.job_id == "job-123"
    assert task.project_id == "1234"
    assert task.mr_iid == "42"
    assert task.initial_state["diff_content"] == "mock diff"
    assert task.queued_at is not None
    db.close()


def test_review_job_updates_task_to_waiting_human():
    session_factory = build_test_session()
    db = session_factory()
    db.add(ReviewTask(thread_id="queued-thread", project_id="1234", mr_iid="42", status="queued"))
    db.commit()

    graph = Mock()
    graph.get_state.return_value = SimpleNamespace(
        next=("human_review",),
        values={
            "mr_id": "42",
            "project_id": "1234",
            "mr_url": "http://gitlab.local/demo/-/merge_requests/42",
            "final_risk_level": "HIGH",
            "summary_report": "高风险摘要",
            "final_comment": "高风险评论",
            "reviews": [],
        },
    )

    try:
        with patch("src.services.review_orchestrator.graph", graph):
            result = run_review_job(db, thread_id="queued-thread", initial_state={"mr_id": "42"})
    finally:
        db.close()

    assert result == {"status": "paused", "thread_id": "queued-thread"}
    db = session_factory()
    task = db.query(ReviewTask).filter_by(thread_id="queued-thread").one()
    assert task.status == "waiting_human"
    assert task.final_risk_level == "HIGH"
    assert task.final_comment == "高风险评论"
    assert task.started_at is not None
    db.close()


def test_review_job_marks_task_failed_on_exception():
    session_factory = build_test_session()
    db = session_factory()
    db.add(ReviewTask(thread_id="failed-thread", project_id="1234", mr_iid="42", status="queued"))
    db.commit()

    graph = Mock()
    graph.invoke.side_effect = RuntimeError("模型调用失败")

    try:
        with patch("src.services.review_orchestrator.graph", graph):
            try:
                run_review_job(db, thread_id="failed-thread", initial_state={"mr_id": "42"})
            except RuntimeError:
                pass
    finally:
        db.close()

    db = session_factory()
    task = db.query(ReviewTask).filter_by(thread_id="failed-thread").one()
    assert task.status == "failed"
    assert task.error_message == "模型调用失败"
    assert task.failed_at is not None
    assert task.completed_at is None
    db.close()


def test_review_job_records_auto_gitlab_comment():
    session_factory = build_test_session()
    db = session_factory()
    db.add(ReviewTask(thread_id="auto-comment-thread", project_id="1234", mr_iid="42", status="queued"))
    db.commit()

    graph = Mock()
    graph.get_state.return_value = SimpleNamespace(
        next=(),
        values={
            "mr_id": "42",
            "project_id": "1234",
            "final_comment": "自动评论",
            "reviews": [],
        },
    )

    try:
        with patch("src.services.review_orchestrator.graph", graph), patch(
            "src.services.review_orchestrator.post_mr_comment"
        ) as post_comment:
            result = run_review_job(db, thread_id="auto-comment-thread", initial_state={"mr_id": "42"})
    finally:
        db.close()

    assert result == {"status": "completed", "thread_id": "auto-comment-thread"}
    post_comment.assert_called_once_with("1234", "42", "自动评论")

    db = session_factory()
    task = db.query(ReviewTask).filter_by(thread_id="auto-comment-thread").one()
    comment_record = db.query(GitLabCommentRecord).filter_by(thread_id="auto-comment-thread").one()
    assert task.status == "completed"
    assert comment_record.source == "auto"
    assert comment_record.success is True
    db.close()


def test_retry_failed_review_enqueues_saved_initial_state():
    session_factory = build_test_session()
    override_db(session_factory)
    db = session_factory()
    db.add(
        ReviewTask(
            thread_id="retry-thread",
            project_id="1234",
            mr_iid="42",
            status="failed",
            retry_count=1,
            initial_state={"mr_id": "42", "project_id": "1234", "diff_content": "saved diff"},
            error_message="上次失败",
        )
    )
    db.commit()
    db.close()

    queue = Mock()
    queue.enqueue.return_value = SimpleNamespace(id="retry-job-1")

    try:
        with patch("src.api.routes.webhook.get_review_queue", return_value=queue):
            res = client.post("/api/reviews/retry-thread/retry")
    finally:
        clear_override_db()

    assert res.status_code == 202
    assert res.json() == {"status": "queued", "thread_id": "retry-thread", "job_id": "retry-job-1"}
    queue.enqueue.assert_called_once()
    _, args, _ = queue.enqueue.mock_calls[0]
    assert args[1] == "retry-thread"
    assert args[2]["diff_content"] == "saved diff"

    db = session_factory()
    task = db.query(ReviewTask).filter_by(thread_id="retry-thread").one()
    assert task.status == "queued"
    assert task.job_id == "retry-job-1"
    assert task.retry_count == 2
    assert task.error_message is None
    db.close()
