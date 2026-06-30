import uuid
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from src.core.workflow import graph
from src.api.globals import pending_reviews
from src.db.session import get_db
from src.services.review_task_service import create_review_task, update_task_from_graph_state

router = APIRouter()

@router.post("/webhook")
async def handle_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    
    # 提取字段
    mr_id = str(payload.get("object_attributes", {}).get("iid", "unknown"))
    project_id = str(payload.get("project", {}).get("id", "unknown"))
    attrs = payload.get("object_attributes", {})
    mr_url = attrs.get("url", "")
    
    # 拉取真实 diff
    from src.tools.gitlab_client import get_mr_changes
    diff_content = get_mr_changes(project_id, mr_id, payload=payload)
    
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    create_review_task(
        db,
        thread_id=thread_id,
        project_id=project_id,
        mr_iid=mr_id,
        mr_url=mr_url,
        source_branch=attrs.get("source_branch"),
        target_branch=attrs.get("target_branch"),
        title=attrs.get("title"),
    )
    
    initial_state = {
        "mr_id": mr_id,
        "project_id": project_id,
        "diff_content": diff_content,
        "mr_url": mr_url
    }
    
    # 启动图
    graph.invoke(initial_state, config=config)
    
    from src.tools.gitlab_client import post_mr_comment
    
    # 检查状态是否中断
    state = graph.get_state(config)
    if state.next and ("human_review" in state.next or "summary:edges" in state.next):
        # 进入 pending 状态
        current_values = state.values
        pending_reviews[thread_id] = {
            "mr_id": current_values.get("mr_id"),
            "project_id": current_values.get("project_id"),
            "mr_url": current_values.get("mr_url"),
            "final_risk_level": current_values.get("final_risk_level"),
            "summary_report": current_values.get("summary_report"),
            "final_comment": current_values.get("final_comment")
        }
        update_task_from_graph_state(db, thread_id, current_values, status="waiting_human")
        return {"status": "paused", "thread_id": thread_id}
    else:
        # LOW risk，图正常结束，执行回写
        current_values = state.values
        post_mr_comment(current_values.get("project_id", "mock"), current_values.get("mr_id", "mock"), current_values.get("final_comment", ""))
        update_task_from_graph_state(db, thread_id, current_values, status="completed")
        return {"status": "completed", "thread_id": thread_id}
