from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.review_package import ReviewPackage
from src.models.review_task import ReviewTask
from src.services.diff_analyzer import split_diff_by_file


def build_package_review_contexts(db: Session, task: ReviewTask, diff_content: str) -> list[dict[str, Any]]:
    """把数据库里的审查包转换为 Agent 可直接消费的上下文。"""
    packages = list(
        db.scalars(
            select(ReviewPackage)
            .where(ReviewPackage.task_id == task.id)
            .order_by(ReviewPackage.priority.asc(), ReviewPackage.id.asc())
        ).all()
    )
    if not packages:
        return []

    diff_by_path = {path: diff for path, diff in split_diff_by_file(diff_content)}
    contexts: list[dict[str, Any]] = []
    for package in packages:
        package_diff = build_package_diff(package.file_paths or [], diff_by_path)
        contexts.append(
            {
                "package_id": package.id,
                "package_key": package.package_key,
                "package_type": package.package_type,
                "title": package.title,
                "risk_domains": package.risk_domains or [],
                "file_paths": package.file_paths or [],
                "selected_agents": package.selected_agents or [],
                "requires_human": package.requires_human,
                "diff_content": package_diff,
            }
        )
    return contexts


def build_package_diff(file_paths: list[str], diff_by_path: dict[str, str]) -> str:
    sections = []
    for file_path in file_paths:
        diff = diff_by_path.get(file_path)
        if diff is None:
            continue
        sections.append(f"# File: {file_path}\n{diff}".strip())
    return "\n\n".join(sections)
