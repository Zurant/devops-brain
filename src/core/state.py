from typing import TypedDict, Annotated, List, Dict, Any, Optional

# Reducer 函数：用于在并行 Agent 执行时，将各自的审查结果安全地追加到状态数组中
def merge_reviews(old_reviews: List[Dict[str, Any]], new_reviews: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return old_reviews + new_reviews

class ReviewState(TypedDict):
    """
    LangGraph 全局状态定义草案。
    所有 Agent 的输入和输出都必须严格遵守此数据结构。
    """
    # 1. 输入数据 (来自 GitLab Webhook)
    mr_id: str
    project_id: str
    diff_content: str
    mr_url: str              # MR 的 web URL，方便审批页面跳转
    review_packages: List[Dict[str, Any]]
    
    # 2. 专家 Agent 并行输出
    # 使用 Annotated 允许 Quality/Security/Architecture Agent 并行写入而不会互相覆盖
    reviews: Annotated[List[Dict[str, Any]], merge_reviews]
    
    # 3. 汇总与决策输出 (由 Summary Agent 填写)
    final_risk_level: str    # "LOW", "MEDIUM", "HIGH"
    summary_report: str
    final_comment: str       # 最终回写到 GitLab MR 的评论内容
    
    # 4. Human-in-the-Loop 状态
    # 必须为 Optional，并建议在图的入口节点初始化为 None，防止 LangGraph 报 KeyError
    human_decision: Optional[str] 
