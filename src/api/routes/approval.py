from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from src.core.workflow import graph
from src.api.globals import pending_reviews
from src.db.session import get_db
from src.services.review_task_service import (
    get_review_detail,
    get_latest_failed_gitlab_comment_record,
    get_review_task_by_thread_id,
    list_pending_reviews,
    list_review_history,
    record_gitlab_comment_result,
    record_approval_decision,
    update_task_from_graph_state,
)

router = APIRouter()

class ResumeRequest(BaseModel):
    thread_id: str
    decision: str  # approve / reject / modify
    modified_comment: Optional[str] = None

@router.post("/resume")
async def resume_workflow(req: ResumeRequest, db: Session = Depends(get_db)):
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
async def get_review_history(limit: int = 50, db: Session = Depends(get_db)):
    return list_review_history(db, limit=limit)


@router.get("/reviews/{thread_id}")
async def get_review_task_detail(thread_id: str, db: Session = Depends(get_db)):
    detail = get_review_detail(db, thread_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="review task not found")
    return detail


@router.post("/reviews/{thread_id}/comments/retry")
async def retry_gitlab_comment(thread_id: str, db: Session = Depends(get_db)):
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
        raise HTTPException(status_code=502, detail=f"failed to post GitLab comment: {exc}")

    return {"status": "comment_posted", "thread_id": thread_id}
