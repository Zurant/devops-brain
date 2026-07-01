from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select

from src.db.session import SessionLocal
from src.models.review_knowledge import ReviewKnowledge
from src.services.review_task_service import serialize_review_knowledge


def retrieve_relevant_knowledge(
    diff_content: str,
    *,
    agent_name: str,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """按关键词召回历史经验；数据库不可用时不影响审查主流程。"""
    keywords = extract_keywords(diff_content)
    if not keywords:
        return []

    try:
        with SessionLocal() as db:
            candidates = db.scalars(
                select(ReviewKnowledge)
                .where(
                    ReviewKnowledge.is_active.is_(True),
                    (ReviewKnowledge.source_agent == agent_name)
                    | (ReviewKnowledge.source_agent.is_(None))
                    | (ReviewKnowledge.risk == "HIGH")
                )
                .order_by(ReviewKnowledge.created_at.desc())
                .limit(100)
            ).all()
    except Exception:
        return []

    scored: list[tuple[int, ReviewKnowledge]] = []
    for item in candidates:
        score = score_knowledge_item(item, keywords, agent_name)
        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [serialize_review_knowledge(item) for _, item in scored[:limit]]


def extract_keywords(text: str, *, limit: int = 40) -> set[str]:
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", text.lower())
    stop_words = {
        "file",
        "src",
        "def",
        "class",
        "return",
        "import",
        "from",
        "where",
        "select",
        "null",
        "true",
        "false",
    }
    keywords = [word for word in words if word not in stop_words]
    return set(keywords[:limit])


def score_knowledge_item(item: ReviewKnowledge, keywords: set[str], agent_name: str) -> int:
    haystack = " ".join(
        str(part or "")
        for part in [
            item.issue_type,
            item.title,
            item.description,
            item.suggestion,
            " ".join(item.tags or []),
        ]
    ).lower()
    score = sum(2 for keyword in keywords if keyword in haystack)
    if item.source_agent == agent_name:
        score += 3
    if item.risk == "HIGH":
        score += 2
    return score


def format_knowledge_prompt(knowledge_items: list[dict[str, Any]]) -> str:
    if not knowledge_items:
        return "暂无可参考的历史审查经验。"

    lines = ["以下是团队历史审查经验，请在判断风险和给出建议时优先参考，但不要机械照搬："]
    for index, item in enumerate(knowledge_items, start=1):
        title = item.get("title") or item.get("issue_type") or "未命名经验"
        suggestion = item.get("suggestion") or "未提供修复建议"
        lines.append(
            f"{index}. 类型：{item.get('issue_type')}；风险：{item.get('risk')}；标题：{title}；"
            f"描述：{item.get('description')}；建议：{suggestion}"
        )
    return "\n".join(lines)
