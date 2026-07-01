from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.models.agent_review import AgentReview
from src.models.approval_record import ApprovalRecord
from src.models.audit_log import AuditLog
from src.models.gitlab_comment_record import GitLabCommentRecord
from src.models.review_knowledge import ReviewKnowledge
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
    initial_state: dict[str, Any] | None = None,
) -> ReviewTask:
    now = datetime.now(timezone.utc)
    task = ReviewTask(
        thread_id=thread_id,
        project_id=project_id,
        mr_iid=mr_iid,
        mr_url=mr_url,
        source_branch=source_branch,
        target_branch=target_branch,
        title=title,
        status=status,
        initial_state=initial_state,
        queued_at=now if status == "queued" else None,
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
    if status == "queued":
        task.queued_at = datetime.now(timezone.utc)
        task.failed_at = None
    if status == "running":
        task.started_at = datetime.now(timezone.utc)
        task.failed_at = None
    if status in {"completed", "rejected"}:
        task.completed_at = datetime.now(timezone.utc)
    if status == "failed":
        task.failed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(task)
    return task


def mark_task_queued(
    db: Session,
    thread_id: str,
    *,
    job_id: str,
    initial_state: dict[str, Any] | None = None,
    increment_retry: bool = False,
) -> ReviewTask | None:
    task = get_review_task_by_thread_id(db, thread_id)
    if task is None:
        return None

    task.status = "queued"
    task.job_id = job_id
    task.error_message = None
    task.queued_at = datetime.now(timezone.utc)
    task.failed_at = None
    task.completed_at = None
    if initial_state is not None:
        task.initial_state = initial_state
    if increment_retry:
        task.retry_count += 1

    db.commit()
    db.refresh(task)
    return task


def mark_task_running(db: Session, thread_id: str) -> ReviewTask | None:
    return update_task_status(db, thread_id, "running", error_message=None)


def mark_task_failed(db: Session, thread_id: str, error_message: str) -> ReviewTask | None:
    return update_task_status(db, thread_id, "failed", error_message=error_message)


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
    task.error_message = None
    if status in {"completed", "rejected"}:
        task.completed_at = datetime.now(timezone.utc)
    if status == "failed":
        task.failed_at = datetime.now(timezone.utc)

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


def record_gitlab_comment_result(
    db: Session,
    *,
    thread_id: str,
    project_id: str,
    mr_iid: str,
    comment_body: str | None,
    source: str,
    success: bool,
    error_message: str | None = None,
) -> GitLabCommentRecord | None:
    task = get_review_task_by_thread_id(db, thread_id)
    if task is None:
        return None

    record = GitLabCommentRecord(
        task_id=task.id,
        thread_id=thread_id,
        project_id=project_id,
        mr_iid=mr_iid,
        comment_body=comment_body,
        source=source,
        success=success,
        error_message=error_message,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_latest_failed_gitlab_comment_record(db: Session, thread_id: str) -> GitLabCommentRecord | None:
    return db.scalar(
        select(GitLabCommentRecord)
        .where(GitLabCommentRecord.thread_id == thread_id, GitLabCommentRecord.success.is_(False))
        .order_by(GitLabCommentRecord.posted_at.desc(), GitLabCommentRecord.id.desc())
    )


def record_audit_log(
    db: Session,
    *,
    actor: str | None,
    action: str,
    resource_type: str,
    resource_id: str,
    detail: dict[str, Any] | None = None,
) -> AuditLog:
    log = AuditLog(
        actor=actor or "anonymous",
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def list_audit_logs(
    db: Session,
    *,
    resource_id: str | None = None,
    action: str | None = None,
    actor: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    query = select(AuditLog)
    if resource_id:
        query = query.where(AuditLog.resource_id == resource_id)
    if action:
        query = query.where(AuditLog.action == action)
    if actor:
        query = query.where(AuditLog.actor == actor)

    logs = db.scalars(query.order_by(AuditLog.created_at.desc()).limit(limit)).all()
    return [serialize_audit_log(log) for log in logs]


def create_review_knowledge(
    db: Session,
    *,
    issue_type: str,
    risk: str,
    description: str,
    title: str | None = None,
    suggestion: str | None = None,
    source_task_id: int | None = None,
    source_thread_id: str | None = None,
    source_agent: str | None = None,
    tags: list[str] | None = None,
    created_by: str | None = None,
) -> ReviewKnowledge:
    knowledge = ReviewKnowledge(
        issue_type=issue_type,
        risk=risk,
        title=title,
        description=description,
        suggestion=suggestion,
        source_task_id=source_task_id,
        source_thread_id=source_thread_id,
        source_agent=source_agent,
        tags=tags,
        created_by=created_by or "anonymous",
    )
    db.add(knowledge)
    db.commit()
    db.refresh(knowledge)
    return knowledge


def list_review_knowledge(
    db: Session,
    *,
    issue_type: str | None = None,
    risk: str | None = None,
    source_thread_id: str | None = None,
    source_agent: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    query = select(ReviewKnowledge)
    if issue_type:
        query = query.where(ReviewKnowledge.issue_type == issue_type)
    if risk:
        query = query.where(ReviewKnowledge.risk == risk)
    if source_thread_id:
        query = query.where(ReviewKnowledge.source_thread_id == source_thread_id)
    if source_agent:
        query = query.where(ReviewKnowledge.source_agent == source_agent)

    items = db.scalars(query.order_by(ReviewKnowledge.created_at.desc()).limit(limit)).all()
    return [serialize_review_knowledge(item) for item in items]


def create_knowledge_from_review_task(
    db: Session,
    *,
    thread_id: str,
    created_by: str | None = None,
    tags: list[str] | None = None,
) -> list[ReviewKnowledge] | None:
    task = get_review_task_by_thread_id(db, thread_id)
    if task is None:
        return None

    created: list[ReviewKnowledge] = []
    for review in task.agent_reviews:
        for issue in review.issues or []:
            if not isinstance(issue, dict):
                continue
            description = _pick_issue_text(issue, "description", "detail", "message", "reason")
            title = _pick_issue_text(issue, "title", "name", "summary", "type")
            suggestion = _pick_issue_text(issue, "suggestion", "fix", "recommendation", "advice")
            issue_type = _pick_issue_text(issue, "type", "category", "rule", "title") or review.agent_name
            risk = str(issue.get("risk") or issue.get("severity") or review.risk or task.final_risk_level or "MEDIUM").upper()

            if not description and not title:
                continue
            if not title and description:
                title = build_title_from_description(description)

            created.append(
                ReviewKnowledge(
                    issue_type=issue_type[:128],
                    risk=risk[:16],
                    title=title,
                    description=description or title or "未提供问题描述",
                    suggestion=suggestion,
                    source_task_id=task.id,
                    source_thread_id=task.thread_id,
                    source_agent=review.agent_name,
                    tags=tags,
                    created_by=created_by or "anonymous",
                )
            )

    if not created:
        return []

    db.add_all(created)
    db.commit()
    for item in created:
        db.refresh(item)
    return created


def _pick_issue_text(issue: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = issue.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def build_title_from_description(description: str, *, max_length: int = 60) -> str:
    normalized = " ".join(description.split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[:max_length].rstrip() + "..."


def list_pending_reviews(db: Session) -> dict[str, dict[str, Any]]:
    tasks = db.scalars(
        select(ReviewTask)
        .where(ReviewTask.status == "waiting_human")
        .order_by(ReviewTask.created_at.desc())
    ).all()
    return {task.thread_id: serialize_review_task(task) for task in tasks}


def list_review_history(
    db: Session,
    limit: int = 50,
    *,
    status: str | None = None,
    risk: str | None = None,
    project_id: str | None = None,
) -> list[dict[str, Any]]:
    query = select(ReviewTask)
    if status:
        query = query.where(ReviewTask.status == status)
    if risk:
        query = query.where(ReviewTask.final_risk_level == risk)
    if project_id:
        query = query.where(ReviewTask.project_id == project_id)

    tasks = db.scalars(query.order_by(ReviewTask.created_at.desc()).limit(limit)).all()
    return [serialize_review_task(task) for task in tasks]


def get_review_detail(db: Session, thread_id: str) -> dict[str, Any] | None:
    task = get_review_task_by_thread_id(db, thread_id)
    if task is None:
        return None

    detail = serialize_review_task(task)
    diff_content = (task.initial_state or {}).get("diff_content") if task.initial_state else None
    detail["diff_summary"] = summarize_diff_content(diff_content)
    detail["agent_reviews"] = [serialize_agent_review(review) for review in task.agent_reviews]
    detail["approval_records"] = [serialize_approval_record(record) for record in task.approval_records]
    detail["gitlab_comment_records"] = [
        serialize_gitlab_comment_record(record) for record in task.gitlab_comment_records
    ]
    detail["knowledge_entries"] = [serialize_review_knowledge(item) for item in task.knowledge_entries]
    detail["audit_logs"] = list_audit_logs(db, resource_id=thread_id, limit=50)
    return detail


def summarize_diff_content(diff_content: str | None) -> dict[str, Any]:
    if not diff_content:
        return {"files": [], "file_count": 0, "additions": 0, "deletions": 0, "preview": ""}

    files: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    additions = 0
    deletions = 0

    for line in diff_content.splitlines():
        if line.startswith("# File: "):
            current = {"path": line.removeprefix("# File: ").strip(), "additions": 0, "deletions": 0}
            files.append(current)
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            additions += 1
            if current is not None:
                current["additions"] += 1
        elif line.startswith("-"):
            deletions += 1
            if current is not None:
                current["deletions"] += 1

    return {
        "files": files,
        "file_count": len(files),
        "additions": additions,
        "deletions": deletions,
        "preview": diff_content[:2000],
    }


def serialize_agent_review(review: AgentReview) -> dict[str, Any]:
    return {
        "agent_name": review.agent_name,
        "risk": review.risk,
        "issues": review.issues,
        "raw_response": review.raw_response,
        "error_message": review.error_message,
        "latency_ms": review.latency_ms,
        "token_usage": review.token_usage,
        "model_name": review.model_name,
        "created_at": review.created_at.isoformat() if review.created_at else None,
    }


def serialize_approval_record(record: ApprovalRecord) -> dict[str, Any]:
    return {
        "decision": record.decision,
        "operator": record.operator,
        "original_comment": record.original_comment,
        "modified_comment": record.modified_comment,
        "comment_posted": record.comment_posted,
        "decided_at": record.decided_at.isoformat() if record.decided_at else None,
    }


def serialize_gitlab_comment_record(record: GitLabCommentRecord) -> dict[str, Any]:
    return {
        "project_id": record.project_id,
        "mr_iid": record.mr_iid,
        "comment_body": record.comment_body,
        "source": record.source,
        "success": record.success,
        "error_message": record.error_message,
        "posted_at": record.posted_at.isoformat() if record.posted_at else None,
    }


def serialize_audit_log(log: AuditLog) -> dict[str, Any]:
    return {
        "actor": log.actor,
        "action": log.action,
        "resource_type": log.resource_type,
        "resource_id": log.resource_id,
        "detail": log.detail,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def serialize_review_knowledge(item: ReviewKnowledge) -> dict[str, Any]:
    return {
        "id": item.id,
        "issue_type": item.issue_type,
        "risk": item.risk,
        "title": item.title,
        "description": item.description,
        "suggestion": item.suggestion,
        "source_task_id": item.source_task_id,
        "source_thread_id": item.source_thread_id,
        "source_agent": item.source_agent,
        "tags": item.tags,
        "created_by": item.created_by,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


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
        "job_id": task.job_id,
        "retry_count": task.retry_count,
        "final_risk_level": task.final_risk_level,
        "summary_report": task.summary_report,
        "final_comment": task.final_comment,
        "approval_decision": approval.decision if approval else None,
        "comment_posted": approval.comment_posted if approval else None,
        "error_message": task.error_message,
        "queued_at": task.queued_at.isoformat() if task.queued_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "failed_at": task.failed_at.isoformat() if task.failed_at else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }
