import json
from unittest.mock import patch

from src.agents.summary import build_summary_payload, summary_agent


def test_build_summary_payload_groups_reviews_by_package_and_sorts_risk():
    payload = build_summary_payload(
        {
            "reviews": [
                {
                    "agent": "quality",
                    "risk": "LOW",
                    "package_id": 1,
                    "package_key": "module:src:python",
                    "package_title": "src 模块审查包",
                    "file_paths": ["src/app.py"],
                    "risk_domains": [],
                    "issues": [{"title": "命名可读性一般", "risk": "LOW"}],
                },
                {
                    "agent": "security",
                    "risk": "HIGH",
                    "package_id": 2,
                    "package_key": "risk_domain:security",
                    "package_title": "security 风险域审查包",
                    "file_paths": ["src/auth.py"],
                    "risk_domains": ["security"],
                    "issues": [{"title": "硬编码密钥", "risk": "HIGH", "suggestion": "改用密钥管理服务"}],
                },
            ]
        }
    )

    assert payload["final_risk_level"] == "HIGH"
    assert payload["package_count"] == 2
    assert payload["risk_counts"] == {"HIGH": 1, "MEDIUM": 0, "LOW": 1}
    assert payload["package_summaries"][0]["package_key"] == "risk_domain:security"
    assert payload["package_summaries"][0]["issues"][0]["title"] == "硬编码密钥"


def test_build_summary_payload_deduplicates_same_issue_in_package():
    payload = build_summary_payload(
        {
            "reviews": [
                {
                    "agent": "quality",
                    "risk": "MEDIUM",
                    "package_key": "risk_domain:database",
                    "issues": [
                        {"title": "SQL 拼接风险", "risk": "MEDIUM", "suggestion": "使用参数化查询"},
                    ],
                },
                {
                    "agent": "security",
                    "risk": "HIGH",
                    "package_key": "risk_domain:database",
                    "issues": [
                        {"title": "SQL 拼接风险", "risk": "HIGH", "suggestion": "使用参数化查询"},
                    ],
                },
            ]
        }
    )

    package = payload["package_summaries"][0]
    assert package["risk"] == "HIGH"
    assert package["agents"] == ["quality", "security"]
    assert package["issue_count"] == 1
    assert package["issues"][0]["risk"] == "HIGH"


def test_summary_agent_sends_structured_payload_to_llm():
    def mock_summary_llm(prompt: str, agent_name: str, model: str = None) -> str:
        assert "package_summaries" in prompt
        assert "risk_domain:security" in prompt
        assert "总体结论、关键风险、分模块审查结果、历史经验参考" in prompt
        return json.dumps(
            {
                "final_risk_level": "HIGH",
                "summary_report": "发现安全高风险问题",
                "final_comment": "## 总体结论\n存在高风险。",
            }
        )

    with patch("src.agents.summary.call_llm", side_effect=mock_summary_llm):
        result = summary_agent(
            {
                "reviews": [
                    {
                        "agent": "security",
                        "risk": "HIGH",
                        "package_key": "risk_domain:security",
                        "issues": [{"title": "硬编码密钥", "risk": "HIGH"}],
                    }
                ]
            }
        )

    assert result["final_risk_level"] == "HIGH"
    assert result["summary_report"] == "发现安全高风险问题"
    assert "总体结论" in result["final_comment"]


@patch("src.agents.summary.call_llm", return_value="not json")
def test_summary_agent_uses_readable_fallback_when_llm_response_invalid(mock_llm):
    result = summary_agent(
        {
            "reviews": [
                {
                    "agent": "security",
                    "risk": "HIGH",
                    "package_key": "risk_domain:security",
                    "package_title": "security 风险域审查包",
                    "file_paths": ["src/auth.py"],
                    "risk_domains": ["security"],
                    "issues": [{"title": "硬编码密钥", "risk": "HIGH", "suggestion": "改用环境变量"}],
                    "referenced_knowledge": [
                        {"title": "密钥泄露处理经验", "risk": "HIGH", "suggestion": "密钥不要入库。"}
                    ],
                }
            ]
        }
    )

    assert result["final_risk_level"] == "HIGH"
    assert "## 总体结论" in result["final_comment"]
    assert "## 分模块审查结果" in result["final_comment"]
    assert "硬编码密钥" in result["final_comment"]
    assert "密钥泄露处理经验" in result["final_comment"]


def test_summary_agent_truncates_too_long_comment():
    long_comment = "x" * 13000

    with patch(
        "src.agents.summary.call_llm",
        return_value=json.dumps(
            {
                "final_risk_level": "LOW",
                "summary_report": "评论过长",
                "final_comment": long_comment,
            }
        ),
    ):
        result = summary_agent({"reviews": []})

    assert len(result["final_comment"]) < len(long_comment)
    assert "已截断" in result["final_comment"]
