from src.core.state import ReviewState
from src.tools.llm_client import call_llm
from src.agents import parse_agent_json

PROMPT_TEMPLATE = """
请作为安全审计专家，检查以下代码是否存在安全漏洞，例如 SQL 注入、XSS、密钥泄露、不安全的依赖等。
请必须返回如下格式的纯 JSON，不要包含其他多余解释：
{
    "agent": "security",
    "issues": [
        {"description": "发现的安全漏洞"}
    ],
    "risk": "LOW" // 必须是 LOW, MEDIUM, HIGH 之一
}

代码变更：
{diff_content}
"""

def security_agent(state: ReviewState):
    diff = state.get("diff_content", "")
    prompt = PROMPT_TEMPLATE.replace("{diff_content}", diff)
    response_text = call_llm(prompt, agent_name="security")
    result = parse_agent_json(response_text, "security")
    return {"reviews": [result]}
