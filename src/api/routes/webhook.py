import uuid
from fastapi import APIRouter, Request
from src.core.workflow import graph
from src.api.globals import pending_reviews

router = APIRouter()

@router.post("/webhook")
async def handle_webhook(request: Request):
    payload = await request.json()
    
    # 提取字段
    mr_id = str(payload.get("object_attributes", {}).get("iid", "unknown"))
    project_id = str(payload.get("project", {}).get("id", "unknown"))
    mr_url = payload.get("object_attributes", {}).get("url", "")
    
    # 模拟提取 diff
    diff_content = "mock diff content"
    if "changes" in payload:
        diff_content = "\n".join([c.get("diff", "") for c in payload.get("changes", [])])
    
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    initial_state = {
        "mr_id": mr_id,
        "project_id": project_id,
        "diff_content": diff_content,
        "mr_url": mr_url
    }
    
    # 启动图
    graph.invoke(initial_state, config=config)
    
    # 检查状态是否中断
    state = graph.get_state(config)
    if state.next and ("human_review" in state.next or "summary:edges" in state.next):
        # 进入 pending 状态
        current_values = state.values
        pending_reviews[thread_id] = {
            "mr_url": mr_url,
            "risk_level": current_values.get("final_risk_level"),
            "summary_report": current_values.get("summary_report")
        }
        return {"status": "pending_human_review", "thread_id": thread_id}
        
    return {"status": "completed", "thread_id": thread_id}
