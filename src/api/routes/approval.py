from fastapi import APIRouter
from pydantic import BaseModel
from src.core.workflow import graph
from src.api.globals import pending_reviews

router = APIRouter()

class ResumeRequest(BaseModel):
    thread_id: str
    decision: str  # approve / reject / modify

@router.post("/resume")
async def resume_workflow(req: ResumeRequest):
    thread_id = req.thread_id
    decision = req.decision
    
    config = {"configurable": {"thread_id": thread_id}}
    
    # 检查线程是否存在
    state = graph.get_state(config)
    if not state or not state.next:
        return {"error": "Thread not found or not paused"}
        
    from src.tools.gitlab_client import post_mr_comment
    # 更新状态：注入 human_decision
    graph.update_state(config, {"human_decision": decision})
    # 继续图执行
    graph.invoke(None, config=config)
    
    # 恢复后移除 pending
    if thread_id in pending_reviews:
        del pending_reviews[thread_id]
        
    state = graph.get_state(config)
    if not state.next:
        # 流程结束，执行回写
        current_values = state.values
        post_mr_comment(current_values.get("project_id", "mock"), current_values.get("mr_id", "mock"), current_values.get("final_comment", ""))
        
    return {"status": "resumed", "thread_id": thread_id, "decision": decision}

@router.get("/pending")
async def get_pending_reviews():
    return pending_reviews
