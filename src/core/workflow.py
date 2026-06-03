from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from src.core.state import ReviewState
import sqlite3

# 引入真实的 Agent
from src.agents.orchestrator import orchestrator
from src.agents.quality import quality_agent
from src.agents.security import security_agent
from src.agents.architecture import architecture_agent

def summary_agent(state: ReviewState):
    """
    汇总与风险评级
    """
    reviews = state.get("reviews", [])
    risks = [r.get("risk", "LOW") for r in reviews]
    
    final_risk = "LOW"
    if "HIGH" in risks:
        final_risk = "HIGH"
    elif "MEDIUM" in risks:
        final_risk = "MEDIUM"
        
    return {
        "final_risk_level": final_risk,
        "summary_report": "Phase 1 Mock Summary",
        "final_comment": "Mock final comment"
    }

def human_review(state: ReviewState):
    """
    人类审批节点（HITL）
    图在进入此节点前会挂起（interrupt_before），
    等待人类在外部提供审批结果更新状态后才会恢复执行。
    """
    return {}

def route_after_summary(state: ReviewState):
    """
    汇总节点后的路由判断
    """
    if state.get("final_risk_level") == "HIGH":
        return "human_review"
    return "__end__"

# ========================
# 构建 LangGraph 图
# ========================
builder = StateGraph(ReviewState)

# 添加所有节点
builder.add_node("orchestrator", orchestrator)
builder.add_node("quality", quality_agent)
builder.add_node("security", security_agent)
builder.add_node("architecture", architecture_agent)
builder.add_node("summary", summary_agent)
builder.add_node("human_review", human_review)

# 添加边：从入口开始
builder.set_entry_point("orchestrator")

# orchestrator 并行分发到 3 个 Agent
builder.add_edge("orchestrator", "quality")
builder.add_edge("orchestrator", "security")
builder.add_edge("orchestrator", "architecture")

# 3 个 Agent 执行完毕后，统一流向 summary
builder.add_edge("quality", "summary")
builder.add_edge("security", "summary")
builder.add_edge("architecture", "summary")

# 根据 summary 输出的最终风险等级决定后续路由
builder.add_conditional_edges("summary", route_after_summary)

# human_review 完成后结束图流转
builder.add_edge("human_review", END)

# 初始化 SqliteSaver 进行状态持久化
conn = sqlite3.connect("checkpoints.db", check_same_thread=False)
memory = SqliteSaver(conn=conn)

# 编译图并注入 checkpointer，并在 human_review 节点前设置中断点
graph = builder.compile(checkpointer=memory, interrupt_before=["human_review"])

