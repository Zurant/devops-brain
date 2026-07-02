from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from src.core.workflow import graph
from src.api.globals import pending_reviews
from src.db.session import get_db
from src.services.review_task_service import (
    backfill_empty_knowledge_suggestions,
    create_knowledge_from_review_task,
    create_review_knowledge,
    get_dashboard_metrics,
    get_review_detail,
    get_latest_failed_gitlab_comment_record,
    get_review_task_by_thread_id,
    list_audit_logs,
    list_pending_reviews,
    list_review_knowledge,
    list_review_history,
    record_audit_log,
    record_gitlab_comment_result,
    record_approval_decision,
    serialize_review_knowledge,
    update_task_from_graph_state,
    update_review_knowledge,
)

router = APIRouter()

class ResumeRequest(BaseModel):
    thread_id: str
    decision: str  # approve / reject / modify
    modified_comment: Optional[str] = None


class KnowledgeCreateRequest(BaseModel):
    issue_type: str
    risk: str
    description: str
    title: Optional[str] = None
    suggestion: Optional[str] = None
    source_thread_id: Optional[str] = None
    source_agent: Optional[str] = None
    tags: list[str] | None = None


class KnowledgeUpdateRequest(BaseModel):
    issue_type: Optional[str] = None
    risk: Optional[str] = None
    description: Optional[str] = None
    title: Optional[str] = None
    suggestion: Optional[str] = None
    source_agent: Optional[str] = None
    tags: list[str] | None = None
    is_active: Optional[bool] = None


class ReviewKnowledgeCreateRequest(BaseModel):
    tags: list[str] | None = None

@router.post("/resume")
async def resume_workflow(
    req: ResumeRequest,
    db: Session = Depends(get_db),
    operator: str | None = Header(default=None, alias="X-Operator"),
):
    thread_id = req.thread_id
    decision = req.decision

    if decision not in {"approve", "reject", "modify"}:
        raise HTTPException(status_code=400, detail="decision must be approve, reject or modify")
    
    config = {"configurable": {"thread_id": thread_id}}
    
    # 检查线程是否存在
    state = graph.get_state(config)
    if not state or not state.next:
        raise HTTPException(status_code=404, detail="Thread not found or not paused")

    from src.tools.gitlab_client import post_mr_comment

    task = get_review_task_by_thread_id(db, thread_id)
    original_comment = None
    if task is not None:
        original_comment = task.final_comment
    elif thread_id in pending_reviews:
        original_comment = pending_reviews[thread_id].get("final_comment")

    state_update = {"human_decision": decision}
    if decision == "modify":
        if not req.modified_comment or not req.modified_comment.strip():
            raise HTTPException(status_code=400, detail="modified_comment is required when decision is modify")
        state_update["final_comment"] = req.modified_comment.strip()

    # 更新状态：注入人工审批结果，modify 时同步覆盖最终评论
    graph.update_state(config, state_update)
    # 继续图执行
    graph.invoke(None, config=config)
    
    # 恢复后移除 pending
    if thread_id in pending_reviews:
        del pending_reviews[thread_id]
        
    state = graph.get_state(config)
    comment_posted = False
    if not state.next:
        # approve/modify 执行回写；reject 仅结束流程，保留人工拒绝决策
        current_values = state.values
        if decision in {"approve", "modify"}:
            project_id = current_values.get("project_id", "mock")
            mr_id = current_values.get("mr_id", "mock")
            final_comment = current_values.get("final_comment", "")
            try:
                post_mr_comment(project_id, mr_id, final_comment)
                comment_posted = True
                record_gitlab_comment_result(
                    db,
                    thread_id=thread_id,
                    project_id=project_id,
                    mr_iid=mr_id,
                    comment_body=final_comment,
                    source=decision,
                    success=True,
                )
            except Exception as exc:
                record_gitlab_comment_result(
                    db,
                    thread_id=thread_id,
                    project_id=project_id,
                    mr_iid=mr_id,
                    comment_body=final_comment,
                    source=decision,
                    success=False,
                    error_message=str(exc),
                )
                raise HTTPException(status_code=502, detail=f"failed to post GitLab comment: {exc}")

        current_values = state.values
        update_task_from_graph_state(
            db,
            thread_id,
            current_values,
            status="rejected" if decision == "reject" else "completed",
        )
        record_approval_decision(
            db,
            thread_id=thread_id,
            decision=decision,
            original_comment=original_comment,
            modified_comment=req.modified_comment.strip() if req.modified_comment else None,
            comment_posted=comment_posted,
            operator=operator,
        )
        record_audit_log(
            db,
            actor=operator,
            action=f"review.{decision}",
            resource_type="review_task",
            resource_id=thread_id,
            detail={"comment_posted": comment_posted, "status": "rejected" if decision == "reject" else "completed"},
        )
        
    return {
        "status": "resumed",
        "thread_id": thread_id,
        "decision": decision,
        "comment_posted": comment_posted
    }

@router.get("/pending")
async def get_pending_reviews(db: Session = Depends(get_db)):
    db_pending = list_pending_reviews(db)
    return {**pending_reviews, **db_pending}


@router.get("/history")
async def get_review_history(
    limit: int = 50,
    status: str | None = None,
    risk: str | None = None,
    project_id: str | None = None,
    db: Session = Depends(get_db),
):
    return list_review_history(db, limit=limit, status=status, risk=risk, project_id=project_id)


@router.get("/reviews/{thread_id}")
async def get_review_task_detail(thread_id: str, db: Session = Depends(get_db)):
    detail = get_review_detail(db, thread_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="review task not found")
    return detail


@router.get("/dashboard")
async def get_dashboard(db: Session = Depends(get_db)):
    return get_dashboard_metrics(db)


@router.post("/reviews/{thread_id}/comments/retry")
async def retry_gitlab_comment(
    thread_id: str,
    db: Session = Depends(get_db),
    operator: str | None = Header(default=None, alias="X-Operator"),
):
    failed_record = get_latest_failed_gitlab_comment_record(db, thread_id)
    if failed_record is None:
        raise HTTPException(status_code=404, detail="failed GitLab comment record not found")

    from src.tools.gitlab_client import post_mr_comment

    try:
        post_mr_comment(failed_record.project_id, failed_record.mr_iid, failed_record.comment_body or "")
        record_gitlab_comment_result(
            db,
            thread_id=thread_id,
            project_id=failed_record.project_id,
            mr_iid=failed_record.mr_iid,
            comment_body=failed_record.comment_body,
            source="retry",
            success=True,
        )
        record_audit_log(
            db,
            actor=operator,
            action="gitlab_comment.retry",
            resource_type="review_task",
            resource_id=thread_id,
            detail={"success": True, "project_id": failed_record.project_id, "mr_iid": failed_record.mr_iid},
        )
    except Exception as exc:
        record_gitlab_comment_result(
            db,
            thread_id=thread_id,
            project_id=failed_record.project_id,
            mr_iid=failed_record.mr_iid,
            comment_body=failed_record.comment_body,
            source="retry",
            success=False,
            error_message=str(exc),
        )
        record_audit_log(
            db,
            actor=operator,
            action="gitlab_comment.retry",
            resource_type="review_task",
            resource_id=thread_id,
            detail={"success": False, "error_message": str(exc)},
        )
        raise HTTPException(status_code=502, detail=f"failed to post GitLab comment: {exc}")

    return {"status": "comment_posted", "thread_id": thread_id}


@router.get("/audit-logs")
async def get_audit_logs(
    resource_id: str | None = None,
    action: str | None = None,
    actor: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    return list_audit_logs(db, resource_id=resource_id, action=action, actor=actor, limit=limit)


@router.get("/knowledge")
async def get_review_knowledge(
    issue_type: str | None = None,
    risk: str | None = None,
    source_thread_id: str | None = None,
    source_agent: str | None = None,
    is_active: bool | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    return list_review_knowledge(
        db,
        issue_type=issue_type,
        risk=risk,
        source_thread_id=source_thread_id,
        source_agent=source_agent,
        is_active=is_active,
        limit=limit,
    )


@router.post("/knowledge")
async def create_knowledge(
    req: KnowledgeCreateRequest,
    db: Session = Depends(get_db),
    operator: str | None = Header(default=None, alias="X-Operator"),
):
    if not req.issue_type.strip():
        raise HTTPException(status_code=400, detail="issue_type is required")
    if req.risk not in {"LOW", "MEDIUM", "HIGH"}:
        raise HTTPException(status_code=400, detail="risk must be LOW, MEDIUM or HIGH")
    if not req.description.strip():
        raise HTTPException(status_code=400, detail="description is required")

    task = get_review_task_by_thread_id(db, req.source_thread_id) if req.source_thread_id else None
    knowledge = create_review_knowledge(
        db,
        issue_type=req.issue_type.strip(),
        risk=req.risk,
        title=req.title.strip() if req.title else None,
        description=req.description.strip(),
        suggestion=req.suggestion.strip() if req.suggestion else None,
        source_task_id=task.id if task else None,
        source_thread_id=req.source_thread_id,
        source_agent=req.source_agent,
        tags=req.tags,
        created_by=operator,
    )
    record_audit_log(
        db,
        actor=operator,
        action="knowledge.create",
        resource_type="review_knowledge",
        resource_id=str(knowledge.id),
        detail={"source_thread_id": req.source_thread_id, "issue_type": req.issue_type, "risk": req.risk},
    )
    return serialize_review_knowledge(knowledge)


@router.post("/knowledge/suggestions/backfill")
async def backfill_knowledge_suggestions(
    db: Session = Depends(get_db),
    operator: str | None = Header(default=None, alias="X-Operator"),
):
    updated = backfill_empty_knowledge_suggestions(db)
    record_audit_log(
        db,
        actor=operator,
        action="knowledge.backfill_suggestion",
        resource_type="review_knowledge",
        resource_id="bulk",
        detail={"updated_count": len(updated), "knowledge_ids": [item.id for item in updated]},
    )
    return {
        "status": "updated",
        "updated_count": len(updated),
        "items": [serialize_review_knowledge(item) for item in updated],
    }


@router.patch("/knowledge/{knowledge_id}")
async def update_knowledge(
    knowledge_id: int,
    req: KnowledgeUpdateRequest,
    db: Session = Depends(get_db),
    operator: str | None = Header(default=None, alias="X-Operator"),
):
    if req.issue_type is not None and not req.issue_type.strip():
        raise HTTPException(status_code=400, detail="issue_type cannot be empty")
    if req.risk is not None and req.risk not in {"LOW", "MEDIUM", "HIGH"}:
        raise HTTPException(status_code=400, detail="risk must be LOW, MEDIUM or HIGH")
    if req.description is not None and not req.description.strip():
        raise HTTPException(status_code=400, detail="description cannot be empty")

    knowledge = update_review_knowledge(
        db,
        knowledge_id,
        issue_type=req.issue_type.strip() if req.issue_type is not None else None,
        risk=req.risk,
        title=req.title.strip() if req.title is not None else None,
        description=req.description.strip() if req.description is not None else None,
        suggestion=req.suggestion.strip() if req.suggestion is not None else None,
        source_agent=req.source_agent.strip() if req.source_agent is not None else None,
        tags=req.tags,
        is_active=req.is_active,
    )
    if knowledge is None:
        raise HTTPException(status_code=404, detail="review knowledge not found")

    record_audit_log(
        db,
        actor=operator,
        action="knowledge.update",
        resource_type="review_knowledge",
        resource_id=str(knowledge.id),
        detail=req.model_dump(exclude_unset=True),
    )
    return serialize_review_knowledge(knowledge)


@router.post("/reviews/{thread_id}/knowledge")
async def create_review_knowledge_from_task(
    thread_id: str,
    req: ReviewKnowledgeCreateRequest | None = None,
    db: Session = Depends(get_db),
    operator: str | None = Header(default=None, alias="X-Operator"),
):
    created = create_knowledge_from_review_task(
        db,
        thread_id=thread_id,
        created_by=operator,
        tags=req.tags if req else None,
    )
    if created is None:
        raise HTTPException(status_code=404, detail="review task not found")

    record_audit_log(
        db,
        actor=operator,
        action="knowledge.create_from_review",
        resource_type="review_task",
        resource_id=thread_id,
        detail={"created_count": len(created), "tags": req.tags if req else None},
    )
    return {
        "status": "created",
        "thread_id": thread_id,
        "created_count": len(created),
        "items": [serialize_review_knowledge(item) for item in created],
    }
