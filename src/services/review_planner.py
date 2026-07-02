from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.models.review_diff_file import ReviewDiffFile
from src.models.review_package import ReviewPackage
from src.models.review_plan import ReviewPlan
from src.models.review_task import ReviewTask
from src.services.diff_analyzer import LARGE_MR_CHANGE_THRESHOLD, LARGE_MR_FILE_THRESHOLD


SECURITY_DOMAINS = {"security"}
ARCHITECTURE_DOMAINS = {"database", "configuration", "ci_cd", "dependency", "api"}
HIGH_ATTENTION_DOMAINS = SECURITY_DOMAINS | {"database", "ci_cd", "dependency"}


@dataclass(slots=True)
class ReviewPackageDraft:
    package_key: str
    package_type: str
    title: str
    directory: str | None
    language: str | None
    risk_domains: list[str]
    file_paths: list[str]
    selected_agents: list[str]
    additions: int
    deletions: int
    total_changes: int
    priority: int
    requires_human: bool
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ReviewPlanDraft:
    mr_type: str
    review_strategy: str
    approval_policy: str
    required_agents: list[str]
    risk_domains: list[str]
    file_count: int
    total_changes: int
    package_count: int
    is_large_mr: bool
    reason: str
    metadata: dict[str, Any]
    packages: list[ReviewPackageDraft]


def build_review_plan(diff_files: list[ReviewDiffFile]) -> ReviewPlanDraft:
    """根据文件级 diff 分析结果生成 MR 审查计划。"""
    file_count = len(diff_files)
    total_changes = sum(item.total_changes for item in diff_files)
    risk_domains = sorted({domain for item in diff_files for domain in (item.risk_domains or [])})
    is_large_mr = file_count >= LARGE_MR_FILE_THRESHOLD or total_changes >= LARGE_MR_CHANGE_THRESHOLD
    mr_type = classify_mr_type(diff_files, risk_domains, is_large_mr)
    packages = build_review_packages(diff_files, is_large_mr)
    required_agents = sorted({agent for package in packages for agent in package.selected_agents})
    approval_policy = decide_approval_policy(mr_type, risk_domains, is_large_mr, packages)
    review_strategy = decide_review_strategy(mr_type, packages)

    return ReviewPlanDraft(
        mr_type=mr_type,
        review_strategy=review_strategy,
        approval_policy=approval_policy,
        required_agents=required_agents,
        risk_domains=risk_domains,
        file_count=file_count,
        total_changes=total_changes,
        package_count=len(packages),
        is_large_mr=is_large_mr,
        reason=build_plan_reason(mr_type, approval_policy, risk_domains, file_count, total_changes),
        metadata={
            "large_mr_file_threshold": LARGE_MR_FILE_THRESHOLD,
            "large_mr_change_threshold": LARGE_MR_CHANGE_THRESHOLD,
        },
        packages=packages,
    )


def save_review_plan(db: Session, task: ReviewTask) -> ReviewPlan | None:
    """覆盖保存一次任务的审查计划与审查包。"""
    diff_files = list(db.scalars(select(ReviewDiffFile).where(ReviewDiffFile.task_id == task.id)).all())
    if not diff_files:
        return None

    draft = build_review_plan(diff_files)
    db.execute(delete(ReviewPackage).where(ReviewPackage.task_id == task.id))
    db.execute(delete(ReviewPlan).where(ReviewPlan.task_id == task.id))

    plan = ReviewPlan(
        task_id=task.id,
        mr_type=draft.mr_type,
        review_strategy=draft.review_strategy,
        approval_policy=draft.approval_policy,
        required_agents=draft.required_agents,
        risk_domains=draft.risk_domains,
        file_count=draft.file_count,
        total_changes=draft.total_changes,
        package_count=draft.package_count,
        is_large_mr=draft.is_large_mr,
        reason=draft.reason,
        plan_metadata=draft.metadata,
    )
    db.add(plan)
    db.flush()

    for package in draft.packages:
        db.add(
            ReviewPackage(
                task_id=task.id,
                plan_id=plan.id,
                package_key=package.package_key,
                package_type=package.package_type,
                title=package.title,
                directory=package.directory,
                language=package.language,
                risk_domains=package.risk_domains,
                file_paths=package.file_paths,
                selected_agents=package.selected_agents,
                additions=package.additions,
                deletions=package.deletions,
                total_changes=package.total_changes,
                priority=package.priority,
                requires_human=package.requires_human,
                package_metadata=package.metadata,
            )
        )

    db.commit()
    db.refresh(plan)
    return plan


def classify_mr_type(diff_files: list[ReviewDiffFile], risk_domains: list[str], is_large_mr: bool) -> str:
    if is_large_mr:
        return "large_mr"
    if "security" in risk_domains:
        return "security_sensitive"
    if "database" in risk_domains:
        return "database_change"
    if set(risk_domains) and set(risk_domains).issubset({"configuration", "ci_cd", "dependency"}):
        return "configuration_change"
    total_changes = sum(item.total_changes for item in diff_files)
    if len(diff_files) <= 2 and total_changes <= 80:
        return "small_change"
    if is_refactor_like(diff_files):
        return "refactor"
    return "feature_change"


def build_review_packages(diff_files: list[ReviewDiffFile], is_large_mr: bool) -> list[ReviewPackageDraft]:
    grouped: dict[tuple[str, str], list[ReviewDiffFile]] = defaultdict(list)
    for item in diff_files:
        key = package_group_key(item, is_large_mr)
        grouped[key].append(item)

    packages = [build_package_from_group(key, items) for key, items in grouped.items()]
    return sorted(packages, key=lambda item: (item.priority, item.package_key))


def package_group_key(item: ReviewDiffFile, is_large_mr: bool) -> tuple[str, str]:
    domains = set(item.risk_domains or [])
    for domain in ["security", "database", "ci_cd", "dependency", "configuration"]:
        if domain in domains:
            return ("risk_domain", domain)

    if is_large_mr:
        directory = top_level_directory(item.directory or item.file_path)
        return ("directory", directory or "root")

    directory = item.directory or "root"
    language = item.language or "unknown"
    return ("module", f"{directory}:{language}")


def build_package_from_group(key: tuple[str, str], files: list[ReviewDiffFile]) -> ReviewPackageDraft:
    package_type, package_value = key
    risk_domains = sorted({domain for item in files for domain in (item.risk_domains or [])})
    selected_agents = select_agents(risk_domains)
    additions = sum(item.additions for item in files)
    deletions = sum(item.deletions for item in files)
    total_changes = additions + deletions
    requires_human = bool(set(risk_domains) & HIGH_ATTENTION_DOMAINS) or total_changes >= 300

    return ReviewPackageDraft(
        package_key=f"{package_type}:{package_value}",
        package_type=package_type,
        title=build_package_title(package_type, package_value, risk_domains),
        directory=common_directory(files),
        language=common_language(files),
        risk_domains=risk_domains,
        file_paths=sorted(item.file_path for item in files),
        selected_agents=selected_agents,
        additions=additions,
        deletions=deletions,
        total_changes=total_changes,
        priority=package_priority(risk_domains, total_changes),
        requires_human=requires_human,
        metadata={"file_count": len(files)},
    )


def select_agents(risk_domains: list[str]) -> list[str]:
    agents = {"quality"}
    domains = set(risk_domains)
    if domains & SECURITY_DOMAINS:
        agents.add("security")
    if domains & ARCHITECTURE_DOMAINS:
        agents.add("architecture")
    if not domains:
        agents.add("architecture")
    return sorted(agents)


def decide_approval_policy(mr_type: str, risk_domains: list[str], is_large_mr: bool, packages: list[ReviewPackageDraft]) -> str:
    if is_large_mr or mr_type in {"security_sensitive", "database_change"}:
        return "force_human"
    if any(package.requires_human for package in packages) or set(risk_domains) & {"ci_cd", "dependency"}:
        return "require_human"
    return "auto_allowed"


def decide_review_strategy(mr_type: str, packages: list[ReviewPackageDraft]) -> str:
    if mr_type == "large_mr":
        return "split_by_directory_and_risk"
    if len(packages) > 1:
        return "split_by_risk_domain"
    return "single_package"


def build_plan_reason(mr_type: str, approval_policy: str, risk_domains: list[str], file_count: int, total_changes: int) -> str:
    domain_text = "、".join(risk_domains) if risk_domains else "无明显高风险域"
    return f"MR 类型为 {mr_type}，涉及 {file_count} 个文件、{total_changes} 行变更，风险域：{domain_text}，审批策略：{approval_policy}。"


def build_package_title(package_type: str, package_value: str, risk_domains: list[str]) -> str:
    if package_type == "risk_domain":
        return f"{package_value} 风险域审查包"
    if risk_domains:
        return f"{package_value} 模块审查包（{', '.join(risk_domains)}）"
    return f"{package_value} 模块审查包"


def package_priority(risk_domains: list[str], total_changes: int) -> int:
    domains = set(risk_domains)
    if "security" in domains:
        return 10
    if "database" in domains:
        return 20
    if domains & {"ci_cd", "dependency"}:
        return 30
    if total_changes >= 300:
        return 40
    return 50


def common_directory(files: list[ReviewDiffFile]) -> str | None:
    directories = {item.directory for item in files if item.directory}
    return next(iter(directories)) if len(directories) == 1 else None


def common_language(files: list[ReviewDiffFile]) -> str | None:
    languages = {item.language for item in files if item.language}
    return next(iter(languages)) if len(languages) == 1 else None


def top_level_directory(path: str) -> str | None:
    return path.split("/", 1)[0] if path else None


def is_refactor_like(diff_files: list[ReviewDiffFile]) -> bool:
    if not diff_files:
        return False
    renamed_count = sum(1 for item in diff_files if item.change_type == "renamed")
    return renamed_count >= max(2, len(diff_files) // 2)
