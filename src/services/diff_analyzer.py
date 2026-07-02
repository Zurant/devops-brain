from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from src.models.review_diff_file import ReviewDiffFile
from src.models.review_task import ReviewTask


LARGE_FILE_CHANGE_THRESHOLD = 300
LARGE_MR_CHANGE_THRESHOLD = 800
LARGE_MR_FILE_THRESHOLD = 20

LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".sql": "sql",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".ini": "ini",
    ".env": "dotenv",
    ".md": "markdown",
    ".sh": "shell",
    ".dockerfile": "dockerfile",
}

RISK_RULES = {
    "security": [
        "auth",
        "oauth",
        "permission",
        "password",
        "secret",
        "token",
        "jwt",
        "encrypt",
        "decrypt",
        "crypto",
        "login",
    ],
    "database": ["migration", "migrations", "schema", "sql", "alembic", "ddl"],
    "configuration": [".env", "config", "settings", "application.yml", "application.yaml", "properties", "toml"],
    "ci_cd": [".gitlab-ci", "github/workflows", "dockerfile", "docker-compose", "jenkinsfile", "k8s", "helm"],
    "dependency": ["requirements", "poetry.lock", "pyproject.toml", "package.json", "package-lock", "pom.xml", "go.mod"],
    "api": ["api", "controller", "router", "routes", "endpoint", "handler"],
    "test": ["test", "tests", "spec"],
}


@dataclass(slots=True)
class DiffFileAnalysis:
    file_path: str
    old_path: str | None = None
    new_path: str | None = None
    change_type: str = "modified"
    language: str = "unknown"
    extension: str | None = None
    directory: str | None = None
    additions: int = 0
    deletions: int = 0
    total_changes: int = 0
    risk_domains: list[str] = field(default_factory=list)
    is_large_file: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    diff: str = ""


def analyze_diff(diff_content: str) -> list[DiffFileAnalysis]:
    """将 MR diff 解析成文件级结构化分析结果。"""
    sections = split_diff_by_file(diff_content)
    return [analyze_diff_section(path, diff) for path, diff in sections]


def summarize_diff_analysis(files: list[DiffFileAnalysis]) -> dict[str, Any]:
    total_additions = sum(item.additions for item in files)
    total_deletions = sum(item.deletions for item in files)
    risk_domains = sorted({domain for item in files for domain in item.risk_domains})
    languages = sorted({item.language for item in files if item.language != "unknown"})
    total_changes = total_additions + total_deletions

    return {
        "file_count": len(files),
        "total_additions": total_additions,
        "total_deletions": total_deletions,
        "total_changes": total_changes,
        "languages": languages,
        "risk_domains": risk_domains,
        "is_large_mr": len(files) >= LARGE_MR_FILE_THRESHOLD or total_changes >= LARGE_MR_CHANGE_THRESHOLD,
        "large_file_count": sum(1 for item in files if item.is_large_file),
    }


def save_diff_analysis(db: Session, task: ReviewTask, diff_content: str) -> list[ReviewDiffFile]:
    """覆盖保存一次任务的文件级 diff 分析结果。"""
    analyses = analyze_diff(diff_content)
    summary = summarize_diff_analysis(analyses)

    db.execute(delete(ReviewDiffFile).where(ReviewDiffFile.task_id == task.id))
    rows: list[ReviewDiffFile] = []
    for item in analyses:
        row = ReviewDiffFile(
            task_id=task.id,
            file_path=item.file_path,
            old_path=item.old_path,
            new_path=item.new_path,
            change_type=item.change_type,
            language=item.language,
            extension=item.extension,
            directory=item.directory,
            additions=item.additions,
            deletions=item.deletions,
            total_changes=item.total_changes,
            risk_domains=item.risk_domains,
            is_large_file=item.is_large_file,
            analysis_metadata={**item.metadata, "mr_summary": summary},
        )
        db.add(row)
        rows.append(row)

    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def split_diff_by_file(diff_content: str) -> list[tuple[str, str]]:
    if not diff_content.strip():
        return []

    marker_pattern = re.compile(r"(?m)^# File: (?P<path>.+)$")
    matches = list(marker_pattern.finditer(diff_content))
    if matches:
        sections: list[tuple[str, str]] = []
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(diff_content)
            sections.append((match.group("path").strip(), diff_content[start:end].strip()))
        return sections

    git_sections = split_git_diff_sections(diff_content)
    if git_sections:
        return git_sections

    return [("unknown", diff_content)]


def split_git_diff_sections(diff_content: str) -> list[tuple[str, str]]:
    diff_pattern = re.compile(r"(?m)^diff --git a/(?P<old>\S+) b/(?P<new>\S+).*$")
    matches = list(diff_pattern.finditer(diff_content))
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(diff_content)
        sections.append((match.group("new"), diff_content[start:end].strip()))
    return sections


def analyze_diff_section(file_path: str, diff: str) -> DiffFileAnalysis:
    old_path, new_path = extract_paths(file_path, diff)
    effective_path = new_path or old_path or file_path
    additions, deletions = count_changed_lines(diff)
    extension = detect_extension(effective_path)
    language = detect_language(effective_path, extension)
    directory = detect_directory(effective_path)
    change_type = detect_change_type(old_path, new_path, diff)
    risk_domains = detect_risk_domains(effective_path, language, diff)
    total_changes = additions + deletions

    return DiffFileAnalysis(
        file_path=effective_path,
        old_path=old_path,
        new_path=new_path,
        change_type=change_type,
        language=language,
        extension=extension,
        directory=directory,
        additions=additions,
        deletions=deletions,
        total_changes=total_changes,
        risk_domains=risk_domains,
        is_large_file=total_changes >= LARGE_FILE_CHANGE_THRESHOLD,
        metadata={"has_tests": "test" in effective_path.lower() or "tests" in effective_path.lower()},
        diff=diff,
    )


def extract_paths(file_path: str, diff: str) -> tuple[str | None, str | None]:
    old_path = None
    new_path = file_path if file_path != "unknown" else None

    old_match = re.search(r"(?m)^---\s+(?:a/)?(?P<path>\S+)", diff)
    new_match = re.search(r"(?m)^\+\+\+\s+(?:b/)?(?P<path>\S+)", diff)
    if old_match and old_match.group("path") != "/dev/null":
        old_path = old_match.group("path")
    if new_match and new_match.group("path") != "/dev/null":
        new_path = new_match.group("path")

    return old_path, new_path


def count_changed_lines(diff: str) -> tuple[int, int]:
    additions = 0
    deletions = 0
    for line in diff.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return additions, deletions


def detect_extension(path: str) -> str | None:
    lowered = path.lower()
    if lowered.endswith("dockerfile") or "/dockerfile" in lowered:
        return ".dockerfile"
    suffix = PurePosixPath(path).suffix.lower()
    return suffix or None


def detect_language(path: str, extension: str | None) -> str:
    lowered = path.lower()
    if lowered.endswith("dockerfile") or "/dockerfile" in lowered:
        return "dockerfile"
    if extension in LANGUAGE_BY_EXTENSION:
        return LANGUAGE_BY_EXTENSION[extension]
    return "unknown"


def detect_directory(path: str) -> str | None:
    parent = str(PurePosixPath(path).parent)
    return None if parent == "." else parent


def detect_change_type(old_path: str | None, new_path: str | None, diff: str) -> str:
    if "new file mode" in diff or re.search(r"(?m)^---\s+/dev/null", diff):
        return "added"
    if "deleted file mode" in diff or re.search(r"(?m)^\+\+\+\s+/dev/null", diff):
        return "deleted"
    if old_path and new_path and old_path != new_path:
        return "renamed"
    return "modified"


def detect_risk_domains(path: str, language: str, diff: str) -> list[str]:
    haystack = f"{path}\n{diff}".lower()
    domains = set()
    for domain, keywords in RISK_RULES.items():
        if any(keyword in haystack for keyword in keywords):
            domains.add(domain)

    if language == "sql":
        domains.add("database")
    if language in {"yaml", "toml", "ini", "dotenv", "json"} and "test" not in haystack:
        domains.add("configuration")
    if any(keyword in haystack for keyword in ["select ", "insert ", "update ", "delete ", "drop table", "alter table"]):
        domains.add("database")
    if any(keyword in haystack for keyword in ["subprocess", "eval(", "exec(", "pickle", "shell=true"]):
        domains.add("security")

    return sorted(domains)
