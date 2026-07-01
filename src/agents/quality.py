from src.core.state import ReviewState
from src.tools.llm_client import call_llm
from src.agents import parse_agent_json
from src.agents.knowledge_context import attach_referenced_knowledge, build_agent_knowledge_context

PROMPT_TEMPLATE = """
请作为代码质量审查专家，检查以下代码是否存在代码异味、圈复杂度过高、命名不规范、重复代码等问题。
历史经验参考：
{knowledge_context}

请必须返回如下格式的纯 JSON，不要包含其他多余解释：
{
    "agent": "quality",
    "issues": [
        {
            "title": "问题短标题",
            "type": "complexity|duplication|naming|maintainability|other",
            "description": "问题原因和影响",
            "suggestion": "可执行的修改建议",
            "risk": "LOW|MEDIUM|HIGH"
        }
    ],
    "risk": "LOW" // 必须是 LOW, MEDIUM, HIGH 之一
}

代码变更：
{diff_content}
"""

def quality_agent(state: ReviewState):
    diff = state.get("diff_content", "")
    knowledge_context, knowledge_items = build_agent_knowledge_context(diff, agent_name="quality")
    prompt = PROMPT_TEMPLATE.replace("{knowledge_context}", knowledge_context).replace("{diff_content}", diff)
    response_text = call_llm(prompt, agent_name="quality")
    result = parse_agent_json(response_text, "quality")
    attach_referenced_knowledge(result, knowledge_items)
    return {"reviews": [result]}
