from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.models.agent_review import AgentReview
from src.models.approval_record import ApprovalRecord
from src.models.review_task import ReviewTask


def create_review_task(
    db: Session,
    *,
    thread_id: str,
    project_id: str,
    mr_iid: str,
    mr_url: str | None = None,
    source_branch: str | None = None,
    target_branch: str | None = None,
    title: str | None = None,
    status: str = "running",
) -> ReviewTask:
    task = ReviewTask(
        thread_id=thread_id,
        project_id=project_id,
        mr_iid=mr_iid,
        mr_url=mr_url,
        source_branch=source_branch,
        target_branch=target_branch,
        title=title,
        status=status,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def update_task_status(
    db: Session,
    thread_id: str,
    status: str,
    *,
    error_message: str | None = None,
) -> ReviewTask | None:
    task = get_review_task_by_thread_id(db, thread_id)
    if task is None:
        return None

    task.status = status
    task.error_message = error_message
    task.updated_at = datetime.now(timezone.utc)
    if status in {"completed", "rejected", "failed"}:
        task.completed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(task)
    return task


def get_review_task_by_thread_id(db: Session, thread_id: str) -> ReviewTask | None:
    return db.scalar(select(ReviewTask).where(ReviewTask.thread_id == thread_id))


def replace_agent_reviews(db: Session, task: ReviewTask, reviews: list[dict[str, Any]] | None) -> None:
    db.execute(delete(AgentReview).where(AgentReview.task_id == task.id))
    for review in reviews or []:
        db.add(
            AgentReview(
                task_id=task.id,
                agent_name=str(review.get("agent", "unknown")),
                risk=review.get("risk"),
                issues=review.get("issues"),
                raw_response=review.get("raw_response"),
                error_message=review.get("error"),
                token_usage=review.get("token_usage"),
                model_name=review.get("model"),
            )
        )


def update_task_from_graph_state(db: Session, thread_id: str, values: dict[str, Any], *, status: str) -> ReviewTask | None:
    task = get_review_task_by_thread_id(db, thread_id)
    if task is None:
        return None

    task.status = status
    task.final_risk_level = values.get("final_risk_level")
    task.summary_report = values.get("summary_report")
    task.final_comment = values.get("final_comment")
    task.updated_at = datetime.now(timezone.utc)
    if status in {"completed", "rejected", "failed"}:
        task.completed_at = datetime.now(timezone.utc)

    replace_agent_reviews(db, task, values.get("reviews"))
    db.commit()
    db.refresh(task)
    return task


def record_approval_decision(
    db: Session,
    *,
    thread_id: str,
    decision: str,
    original_comment: str | None,
    modified_comment: str | None,
    comment_posted: bool,
    operator: str | None = None,
) -> ApprovalRecord | None:
    task = get_review_task_by_thread_id(db, thread_id)
    if task is None:
        return None

    record = ApprovalRecord(
        task_id=task.id,
        thread_id=thread_id,
        decision=decision,
        operator=operator,
        original_comment=original_comment,
        modified_comment=modified_comment,
        comment_posted=comment_posted,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_pending_reviews(db: Session) -> dict[str, dict[str, Any]]:
    tasks = db.scalars(
        select(ReviewTask)
        .where(ReviewTask.status == "waiting_human")
        .order_by(ReviewTask.created_at.desc())
    ).all()
    return {task.thread_id: serialize_review_task(task) for task in tasks}


def list_review_history(db: Session, limit: int = 50) -> list[dict[str, Any]]:
    tasks = db.scalars(select(ReviewTask).order_by(ReviewTask.created_at.desc()).limit(limit)).all()
    return [serialize_review_task(task) for task in tasks]


def serialize_review_task(task: ReviewTask) -> dict[str, Any]:
    approval = task.approval_records[-1] if task.approval_records else None
    return {
        "thread_id": task.thread_id,
        "mr_id": task.mr_iid,
        "project_id": task.project_id,
        "mr_url": task.mr_url,
        "source_branch": task.source_branch,
        "target_branch": task.target_branch,
        "title": task.title,
        "status": task.status,
        "final_risk_level": task.final_risk_level,
        "summary_report": task.summary_report,
        "final_comment": task.final_comment,
        "approval_decision": approval.decision if approval else None,
        "comment_posted": approval.comment_posted if approval else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }
