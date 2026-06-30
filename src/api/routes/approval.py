from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from src.core.workflow import graph
from src.api.globals import pending_reviews
from src.db.session import get_db
from src.services.review_task_service import (
    get_review_task_by_thread_id,
    list_pending_reviews,
    list_review_history,
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
            post_mr_comment(
                current_values.get("project_id", "mock"),
                current_values.get("mr_id", "mock"),
                current_values.get("final_comment", "")
            )
            comment_posted = True

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
