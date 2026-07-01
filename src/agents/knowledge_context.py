from typing import Any

from src.services.knowledge_retrieval_service import format_knowledge_prompt, retrieve_relevant_knowledge


def build_agent_knowledge_context(diff_content: str, *, agent_name: str) -> tuple[str, list[dict[str, Any]]]:
    knowledge_items = retrieve_relevant_knowledge(diff_content, agent_name=agent_name)
    return format_knowledge_prompt(knowledge_items), knowledge_items


def attach_referenced_knowledge(review: dict[str, Any], knowledge_items: list[dict[str, Any]]) -> dict[str, Any]:
    if knowledge_items:
        review["referenced_knowledge"] = [
            {
                "id": item.get("id"),
                "title": item.get("title") or item.get("issue_type") or "未命名经验",
                "issue_type": item.get("issue_type"),
                "risk": item.get("risk"),
                "source_agent": item.get("source_agent"),
                "suggestion": item.get("suggestion"),
            }
            for item in knowledge_items
        ]
    return review
