from src.core.state import ReviewState
from src.tools.llm_client import call_llm
from src.agents import parse_agent_json
from src.agents.knowledge_context import attach_referenced_knowledge, build_agent_knowledge_context


AGENT_NAME = "quality"

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
    package_reviews = review_packages_for_agent(state, AGENT_NAME)
    if state.get("review_packages") is not None and not package_reviews:
        return {"reviews": []}
    if package_reviews:
        return {"reviews": [review_package(package, AGENT_NAME) for package in package_reviews]}

    diff = state.get("diff_content", "")
    knowledge_context, knowledge_items = build_agent_knowledge_context(diff, agent_name=AGENT_NAME)
    prompt = PROMPT_TEMPLATE.replace("{knowledge_context}", knowledge_context).replace("{diff_content}", diff)
    response_text = call_llm(prompt, agent_name=AGENT_NAME)
    result = parse_agent_json(response_text, AGENT_NAME)
    attach_referenced_knowledge(result, knowledge_items)
    return {"reviews": [result]}


def review_packages_for_agent(state: ReviewState, agent_name: str) -> list[dict]:
    packages = state.get("review_packages") or []
    return [package for package in packages if agent_name in package.get("selected_agents", [])]


def review_package(package: dict, agent_name: str) -> dict:
    diff = package.get("diff_content", "")
    knowledge_context, knowledge_items = build_agent_knowledge_context(diff, agent_name=agent_name)
    prompt = PROMPT_TEMPLATE.replace("{knowledge_context}", knowledge_context).replace("{diff_content}", diff)
    response_text = call_llm(prompt, agent_name=agent_name)
    result = parse_agent_json(response_text, agent_name)
    attach_referenced_knowledge(result, knowledge_items)
    attach_package_metadata(result, package)
    return result


def attach_package_metadata(result: dict, package: dict) -> None:
    result["package_id"] = package.get("package_id")
    result["package_key"] = package.get("package_key")
    result["package_title"] = package.get("title")
    result["package_type"] = package.get("package_type")
    result["file_paths"] = package.get("file_paths", [])
    result["risk_domains"] = package.get("risk_domains", [])
