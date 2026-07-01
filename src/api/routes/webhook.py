import uuid
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session
from src.db.session import get_db
from src.queue.jobs import process_review_job
from src.queue.redis_client import get_review_queue
from src.services.review_task_service import create_review_task
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
    )
    
    initial_state = {
        "mr_id": mr_id,
        "project_id": project_id,
        "diff_content": diff_content,
        "mr_url": mr_url
    }

    job = get_review_queue().enqueue(process_review_job, thread_id, initial_state)
    return {"status": "queued", "thread_id": thread_id, "job_id": job.id}
