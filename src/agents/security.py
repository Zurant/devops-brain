from src.core.state import ReviewState
from src.tools.llm_client import call_llm
from src.agents import parse_agent_json
from src.agents.knowledge_context import attach_referenced_knowledge, build_agent_knowledge_context

PROMPT_TEMPLATE = """
请作为安全审计专家，检查以下代码是否存在安全漏洞，例如 SQL 注入、XSS、密钥泄露、不安全的依赖等。
历史经验参考：
{knowledge_context}

请必须返回如下格式的纯 JSON，不要包含其他多余解释：
{
    "agent": "security",
    "issues": [
        {
            "title": "问题短标题",
            "type": "sql_injection|xss|secret_leak|auth_bypass|insecure_dependency|other",
            "description": "漏洞原因、攻击面和影响",
            "suggestion": "可执行的修复建议",
            "risk": "LOW|MEDIUM|HIGH"
        }
    ],
    "risk": "LOW" // 必须是 LOW, MEDIUM, HIGH 之一
}

代码变更：
{diff_content}
"""

def security_agent(state: ReviewState):
    diff = state.get("diff_content", "")
    knowledge_context, knowledge_items = build_agent_knowledge_context(diff, agent_name="security")
    prompt = PROMPT_TEMPLATE.replace("{knowledge_context}", knowledge_context).replace("{diff_content}", diff)
    response_text = call_llm(prompt, agent_name="security")
    print("\n--- RAW LLM RESPONSE ---")
    print(response_text)
    print("------------------------\n")
    result = parse_agent_json(response_text, "security")
    attach_referenced_knowledge(result, knowledge_items)
    return {"reviews": [result]}
