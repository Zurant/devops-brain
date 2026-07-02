from src.core.state import ReviewState
from src.tools.llm_client import call_llm
from src.agents import parse_agent_json
from src.agents.knowledge_context import attach_referenced_knowledge, build_agent_knowledge_context
from src.agents.quality import attach_package_metadata, review_packages_for_agent


AGENT_NAME = "architecture"

PROMPT_TEMPLATE = """
请作为架构合规专家，检查以下代码是否符合 SOLID 原则，是否存在分层违规或过度耦合的问题。
历史经验参考：
{knowledge_context}

请必须返回如下格式的纯 JSON，不要包含其他多余解释：
{
    "agent": "architecture",
    "issues": [
        {
            "title": "问题短标题",
            "type": "layer_violation|coupling|solid_violation|dependency_direction|other",
            "description": "架构问题原因和长期影响",
            "suggestion": "可执行的架构调整建议",
            "risk": "LOW|MEDIUM|HIGH"
        }
    ],
    "risk": "LOW" // 必须是 LOW, MEDIUM, HIGH 之一
}

代码变更：
{diff_content}
"""

def architecture_agent(state: ReviewState):
    package_reviews = review_packages_for_agent(state, AGENT_NAME)
    if state.get("review_packages") is not None and not package_reviews:
        return {"reviews": []}
    if package_reviews:
        return {"reviews": [review_package(package) for package in package_reviews]}

    diff = state.get("diff_content", "")
    knowledge_context, knowledge_items = build_agent_knowledge_context(diff, agent_name=AGENT_NAME)
    prompt = PROMPT_TEMPLATE.replace("{knowledge_context}", knowledge_context).replace("{diff_content}", diff)
    response_text = call_llm(prompt, agent_name=AGENT_NAME)
    result = parse_agent_json(response_text, AGENT_NAME)
    attach_referenced_knowledge(result, knowledge_items)
    return {"reviews": [result]}


def review_package(package: dict) -> dict:
    diff = package.get("diff_content", "")
    knowledge_context, knowledge_items = build_agent_knowledge_context(diff, agent_name=AGENT_NAME)
    prompt = PROMPT_TEMPLATE.replace("{knowledge_context}", knowledge_context).replace("{diff_content}", diff)
    response_text = call_llm(prompt, agent_name=AGENT_NAME)
    result = parse_agent_json(response_text, AGENT_NAME)
    attach_referenced_knowledge(result, knowledge_items)
    attach_package_metadata(result, package)
    return result
