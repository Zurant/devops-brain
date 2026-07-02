import json
from collections import defaultdict
from typing import Any

from src.core.state import ReviewState
from src.tools.llm_client import call_llm
from src.agents import parse_agent_json


RISK_ORDER = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
MAX_COMMENT_LENGTH = 12000

PROMPT_TEMPLATE = """
请作为首席技术架构师，基于以下结构化审查结果生成 MR 级二级汇总。
审查结果已经先按 package 做了归并，请你先看每个 package 的风险与问题，再输出整个 MR 的最终结论。
专家审查结果中可能包含 `referenced_knowledge`，表示该专家本次判断参考到的历史审查经验。
评论必须使用中文 Markdown，并按以下顺序组织：总体结论、关键风险、分模块审查结果、历史经验参考。
HIGH 风险优先展示；LOW 风险只做简短概括，避免评论过长。
请你仔细阅读每个专家的发现，并输出以下严格合法的 JSON 格式（注意：如果字符串内有换行，请使用 \\n 转义，不要输出原生换行符）：
{
    "final_risk_level": "LOW", // 取所有专家中发现的最高风险等级 (只能是 LOW, MEDIUM, HIGH 之一)
    "summary_report": "简短的中文综合分析总结",
    "final_comment": "适合直接作为 GitLab MR 评论的 Markdown 内容，按审查包组织问题，并在末尾用“历史经验参考”章节列出本次引用到的经验标题、风险和建议；如果没有引用经验则写明暂无引用"
}

结构化审查结果：
{summary_payload_json}
"""

def summary_agent(state: ReviewState):
    summary_payload = build_summary_payload(state)
    summary_payload_str = json.dumps(summary_payload, ensure_ascii=False, indent=2)
    
    print("\n=== [DEBUG] Summary Agent 结构化汇总输入 ===")
    print(summary_payload_str)
    print("==============================================\n")
    
    prompt = PROMPT_TEMPLATE.replace("{summary_payload_json}", summary_payload_str)
    
    response_text = call_llm(prompt, agent_name="summary")
    print("\n--- SUMMARY RAW LLM RESPONSE ---")
    print(response_text)
    print("--------------------------------\n")
    result = parse_agent_json(response_text, "summary")
    
    final_risk = highest_risk([result.get("final_risk_level"), summary_payload["final_risk_level"]])
    summary_report = result.get("summary_report") or build_fallback_summary_report(summary_payload)
    final_comment = result.get("final_comment") or build_fallback_final_comment(summary_payload)
        
    return {
        "final_risk_level": final_risk,
        "summary_report": summary_report,
        "final_comment": truncate_comment(final_comment),
    }


def build_summary_payload(state: ReviewState) -> dict[str, Any]:
    reviews = state.get("reviews", []) or []
    package_summaries = build_package_summaries(reviews)
    final_risk = highest_risk([package["risk"] for package in package_summaries])
    return {
        "final_risk_level": final_risk,
        "review_count": len(reviews),
        "package_count": len(package_summaries),
        "risk_counts": count_risks(package_summaries),
        "package_summaries": package_summaries,
    }


def build_package_summaries(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for review in reviews:
        grouped[review.get("package_key") or "whole_mr"].append(review)

    summaries = [build_package_summary(package_key, items) for package_key, items in grouped.items()]
    return sorted(summaries, key=lambda item: (-RISK_ORDER[item["risk"]], item["package_key"]))


def build_package_summary(package_key: str, reviews: list[dict[str, Any]]) -> dict[str, Any]:
    first = reviews[0] if reviews else {}
    issues = dedupe_issues(reviews)
    referenced_knowledge = dedupe_referenced_knowledge(reviews)
    risk = highest_risk([review.get("risk") for review in reviews] + [issue.get("risk") for issue in issues])

    return {
        "package_id": first.get("package_id"),
        "package_key": package_key,
        "package_title": first.get("package_title") or package_key,
        "package_type": first.get("package_type"),
        "risk": risk,
        "agents": sorted({str(review.get("agent", "unknown")) for review in reviews}),
        "file_paths": sorted({path for review in reviews for path in (review.get("file_paths") or [])}),
        "risk_domains": sorted({domain for review in reviews for domain in (review.get("risk_domains") or [])}),
        "issue_count": len(issues),
        "issues": sorted(issues, key=lambda item: (-RISK_ORDER[normalize_risk(item.get("risk"))], item.get("title") or item.get("description") or "")),
        "referenced_knowledge": referenced_knowledge,
        "agent_errors": [
            {"agent": review.get("agent", "unknown"), "error": review.get("error")}
            for review in reviews
            if review.get("error")
        ],
    }


def dedupe_issues(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for review in reviews:
        agent = str(review.get("agent", "unknown"))
        for issue in review.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            normalized = {
                **issue,
                "agent": issue.get("agent") or agent,
                "risk": normalize_risk(issue.get("risk") or review.get("risk")),
            }
            key = issue_dedupe_key(normalized)
            current = issues_by_key.get(key)
            if current is None or RISK_ORDER[normalized["risk"]] > RISK_ORDER[normalize_risk(current.get("risk"))]:
                issues_by_key[key] = normalized
    return list(issues_by_key.values())


def issue_dedupe_key(issue: dict[str, Any]) -> tuple[str, str, str]:
    title = str(issue.get("title") or issue.get("description") or "").strip().lower()
    file_path = str(issue.get("file_path") or issue.get("file") or "").strip().lower()
    suggestion = str(issue.get("suggestion") or "").strip().lower()
    return title, file_path, suggestion


def dedupe_referenced_knowledge(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    knowledge_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for review in reviews:
        for item in review.get("referenced_knowledge") or []:
            if not isinstance(item, dict):
                continue
            key = (str(item.get("title") or "").strip(), str(item.get("suggestion") or "").strip())
            knowledge_by_key.setdefault(key, item)
    return list(knowledge_by_key.values())


def count_risks(package_summaries: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for package in package_summaries:
        counts[normalize_risk(package.get("risk"))] += 1
    return counts


def highest_risk(risks: list[Any]) -> str:
    normalized = [normalize_risk(risk) for risk in risks if risk]
    if not normalized:
        return "LOW"
    return max(normalized, key=lambda risk: RISK_ORDER[risk])


def normalize_risk(risk: Any) -> str:
    value = str(risk or "LOW").upper()
    return value if value in RISK_ORDER else "MEDIUM"


def build_fallback_summary_report(payload: dict[str, Any]) -> str:
    counts = payload["risk_counts"]
    return (
        f"本次 MR 共完成 {payload['package_count']} 个审查包汇总，"
        f"最终风险为 {payload['final_risk_level']}。"
        f"风险分布：HIGH {counts['HIGH']} 个、MEDIUM {counts['MEDIUM']} 个、LOW {counts['LOW']} 个。"
    )


def build_fallback_final_comment(payload: dict[str, Any]) -> str:
    lines = [
        "## 总体结论",
        build_fallback_summary_report(payload),
        "",
        "## 关键风险",
    ]
    high_issues = [issue for package in payload["package_summaries"] for issue in package["issues"] if normalize_risk(issue.get("risk")) == "HIGH"]
    if high_issues:
        for issue in high_issues[:10]:
            lines.append(format_issue_line(issue))
    else:
        lines.append("暂无 HIGH 风险阻断项。")

    lines.extend(["", "## 分模块审查结果"])
    for package in payload["package_summaries"]:
        files = "、".join(package["file_paths"]) if package["file_paths"] else "未定位具体文件"
        agents = "、".join(package["agents"]) if package["agents"] else "无"
        lines.append(f"### {package['package_title']}（{package['risk']}）")
        lines.append(f"- 审查包：`{package['package_key']}`")
        lines.append(f"- 文件：{files}")
        lines.append(f"- Agent：{agents}")
        visible_issues = [issue for issue in package["issues"] if normalize_risk(issue.get("risk")) in {"HIGH", "MEDIUM"}]
        if not visible_issues:
            lines.append("- 未发现需要优先处理的问题。")
        for issue in visible_issues[:8]:
            lines.append(format_issue_line(issue))
        for error in package["agent_errors"]:
            lines.append(f"- Agent `{error['agent']}` 执行异常：{error['error']}")
        lines.append("")

    lines.extend(["## 历史经验参考"])
    knowledge_items = dedupe_payload_knowledge(payload)
    if not knowledge_items:
        lines.append("暂无引用历史经验。")
    for item in knowledge_items[:10]:
        title = item.get("title") or "未命名经验"
        risk = item.get("risk") or "-"
        suggestion = item.get("suggestion") or "暂无建议"
        lines.append(f"- **{title}**（{risk}）：{suggestion}")

    return "\n".join(lines).strip()


def format_issue_line(issue: dict[str, Any]) -> str:
    title = issue.get("title") or issue.get("description") or "未命名问题"
    risk = normalize_risk(issue.get("risk"))
    agent = issue.get("agent") or "unknown"
    suggestion = issue.get("suggestion")
    suffix = f" 建议：{suggestion}" if suggestion else ""
    return f"- **[{risk}] {title}**（{agent}）。{suffix}"


def dedupe_payload_knowledge(payload: dict[str, Any]) -> list[dict[str, Any]]:
    knowledge_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for package in payload["package_summaries"]:
        for item in package["referenced_knowledge"]:
            key = (str(item.get("title") or "").strip(), str(item.get("suggestion") or "").strip())
            knowledge_by_key.setdefault(key, item)
    return list(knowledge_by_key.values())


def truncate_comment(comment: str) -> str:
    if len(comment) <= MAX_COMMENT_LENGTH:
        return comment
    return comment[:MAX_COMMENT_LENGTH] + "\n\n> 评论内容过长，已截断；完整结构化结果请在审批工作台详情中查看。"
