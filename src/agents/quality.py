from src.core.state import ReviewState
from src.tools.llm_client import call_llm
from src.agents import parse_agent_json
from src.services.knowledge_retrieval_service import format_knowledge_prompt, retrieve_relevant_knowledge

PROMPT_TEMPLATE = """
请作为代码质量审查专家，检查以下代码是否存在代码异味、圈复杂度过高、命名不规范、重复代码等问题。
历史经验参考：
{knowledge_context}

请必须返回如下格式的纯 JSON，不要包含其他多余解释：
{
    "agent": "quality",
    "issues": [
        {"description": "发现的代码质量问题"}
    ],
    "risk": "LOW" // 必须是 LOW, MEDIUM, HIGH 之一
}

代码变更：
{diff_content}
"""

def quality_agent(state: ReviewState):
    diff = state.get("diff_content", "")
    knowledge_context = format_knowledge_prompt(retrieve_relevant_knowledge(diff, agent_name="quality"))
    prompt = PROMPT_TEMPLATE.replace("{knowledge_context}", knowledge_context).replace("{diff_content}", diff)
    response_text = call_llm(prompt, agent_name="quality")
    result = parse_agent_json(response_text, "quality")
    return {"reviews": [result]}
