import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from src.db.session import get_db
from src.queue.jobs import process_review_job
from src.queue.redis_client import get_review_queue
from src.services.review_task_service import create_review_task, get_review_task_by_thread_id, mark_task_queued
from src.tools.gitlab_client import get_mr_changes

router = APIRouter()

@router.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def handle_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    
    # 提取字段
    mr_id = str(payload.get("object_attributes", {}).get("iid", "unknown"))
    project_id = str(payload.get("project", {}).get("id", "unknown"))
    attrs = payload.get("object_attributes", {})
    mr_url = attrs.get("url", "")
    
    diff_content = get_mr_changes(project_id, mr_id, payload=payload)
    
    thread_id = str(uuid.uuid4())

    initial_state = {
        "mr_id": mr_id,
        "project_id": project_id,
        "diff_content": diff_content,
        "mr_url": mr_url
    }

    create_review_task(
        db,
        thread_id=thread_id,
        project_id=project_id,
        mr_iid=mr_id,
        mr_url=mr_url,
        source_branch=attrs.get("source_branch"),
        target_branch=attrs.get("target_branch"),
        title=attrs.get("title"),
        status="queued",
        initial_state=initial_state,
    )

    job = get_review_queue().enqueue(process_review_job, thread_id, initial_state)
    mark_task_queued(db, thread_id, job_id=job.id, initial_state=initial_state)
    return {"status": "queued", "thread_id": thread_id, "job_id": job.id}


@router.post("/reviews/{thread_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_review(thread_id: str, db: Session = Depends(get_db)):
    task = get_review_task_by_thread_id(db, thread_id)
    if task is None:
        raise HTTPException(status_code=404, detail="review task not found")
    if task.status not in {"failed", "queued"}:
        raise HTTPException(status_code=400, detail="only failed or queued review tasks can be retried")
    if not task.initial_state:
        raise HTTPException(status_code=400, detail="review task has no initial_state for retry")

    job = get_review_queue().enqueue(process_review_job, thread_id, task.initial_state)
    mark_task_queued(db, thread_id, job_id=job.id, increment_retry=True)
    return {"status": "queued", "thread_id": thread_id, "job_id": job.id}
