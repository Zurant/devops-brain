from src.core.state import ReviewState
from src.tools.llm_client import call_llm
from src.agents import parse_agent_json

PROMPT_TEMPLATE = """
请作为架构合规专家，检查以下代码是否符合 SOLID 原则，是否存在分层违规或过度耦合的问题。
请必须返回如下格式的纯 JSON，不要包含其他多余解释：
{
    "agent": "architecture",
    "issues": [
        {"description": "发现的架构合规问题"}
    ],
    "risk": "LOW" // 必须是 LOW, MEDIUM, HIGH 之一
}

代码变更：
{diff_content}
"""

def architecture_agent(state: ReviewState):
    diff = state.get("diff_content", "")
    prompt = PROMPT_TEMPLATE.replace("{diff_content}", diff)
    response_text = call_llm(prompt, agent_name="architecture")
    result = parse_agent_json(response_text, "architecture")
    return {"reviews": [result]}
