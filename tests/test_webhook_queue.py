from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from src.api.server import app
from src.db.session import get_db
from src.models import ReviewTask
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
    assert task.project_id == "1234"
    assert task.mr_iid == "42"
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
    db.close()
