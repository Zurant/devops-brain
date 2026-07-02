import json
from unittest.mock import patch
from src.agents.quality import quality_agent
from src.agents.security import security_agent
from src.agents.architecture import architecture_agent
from src.agents.summary import summary_agent
from src.agents import parse_agent_json

def mock_call_llm_success(prompt: str, agent_name: str, model: str = None) -> str:
    """模拟大模型成功返回 markdown 格式的 JSON"""
    mock_res = {
        "agent": agent_name,
        "issues": [{"description": f"Mock issue from {agent_name}"}],
        "risk": "LOW"
    }
    return f"```json\n{json.dumps(mock_res)}\n```"


def build_package(**overrides):
    package = {
        "package_id": 7,
        "package_key": "risk_domain:database",
        "package_type": "risk_domain",
        "title": "database 风险域审查包",
        "risk_domains": ["database"],
        "file_paths": ["src/api.py"],
        "selected_agents": ["architecture", "quality"],
        "requires_human": True,
        "diff_content": "# File: src/api.py\n+cursor.execute(sql)",
    }
    package.update(overrides)
    return package

def mock_call_llm_fail(prompt: str, agent_name: str, model: str = None) -> str:
    """模拟大模型返回无效的乱码"""
    return "This is not a JSON, sorry!"

def test_parse_agent_json():
    # 测试正确的 markdown json
    valid_markdown = "```json\n{\"agent\": \"test\", \"risk\": \"LOW\"}\n```"
    res = parse_agent_json(valid_markdown, "test")
    assert res["risk"] == "LOW"

    # 测试无代码块的 json
    valid_json = "{\"agent\": \"test\", \"risk\": \"HIGH\"}"
    res2 = parse_agent_json(valid_json, "test")
    assert res2["risk"] == "HIGH"

    # 测试乱码 fallback
    invalid = "Hello world"
    res3 = parse_agent_json(invalid, "test")
    assert res3["risk"] == "MEDIUM"
    assert "error" in res3

@patch("src.agents.quality.call_llm", side_effect=mock_call_llm_success)
@patch("src.agents.knowledge_context.retrieve_relevant_knowledge", return_value=[])
def test_quality_agent_success(mock_knowledge, mock_llm):
    state = {"diff_content": "def foo(): pass"}
    res = quality_agent(state)
    reviews = res["reviews"]
    assert len(reviews) == 1
    assert reviews[0]["agent"] == "quality"
    assert reviews[0]["risk"] == "LOW"
    mock_knowledge.assert_called_once_with("def foo(): pass", agent_name="quality")

@patch("src.agents.security.call_llm", side_effect=mock_call_llm_fail)
@patch("src.agents.knowledge_context.retrieve_relevant_knowledge", return_value=[])
def test_security_agent_fallback(mock_knowledge, mock_llm):
    state = {"diff_content": "SELECT * FROM users"}
    res = security_agent(state)
    reviews = res["reviews"]
    assert len(reviews) == 1
    assert reviews[0]["agent"] == "security"
    assert reviews[0]["risk"] == "MEDIUM"
    assert "error" in reviews[0]

@patch("src.agents.architecture.call_llm", side_effect=mock_call_llm_success)
@patch("src.agents.knowledge_context.retrieve_relevant_knowledge", return_value=[])
def test_architecture_agent_success(mock_knowledge, mock_llm):
    state = {"diff_content": "class A: pass"}
    res = architecture_agent(state)
    assert res["reviews"][0]["agent"] == "architecture"


@patch(
    "src.agents.knowledge_context.retrieve_relevant_knowledge",
    return_value=[
        {
            "issue_type": "sql_injection",
            "risk": "HIGH",
            "title": "SQL 注入风险",
            "description": "拼接 SQL。",
            "suggestion": "使用参数化查询。",
        }
    ],
)
@patch("src.agents.security.call_llm", side_effect=mock_call_llm_success)
def test_security_agent_injects_knowledge_context(mock_llm, mock_knowledge):
    state = {"diff_content": "cursor.execute('SELECT * FROM users')"}

    res = security_agent(state)

    prompt = mock_llm.call_args.args[0]
    assert "历史经验参考" in prompt
    assert "SQL 注入风险" in prompt
    assert "使用参数化查询" in prompt
    referenced = res["reviews"][0]["referenced_knowledge"]
    assert referenced[0]["title"] == "SQL 注入风险"
    assert referenced[0]["suggestion"] == "使用参数化查询。"


@patch("src.agents.knowledge_context.retrieve_relevant_knowledge", return_value=[])
@patch("src.agents.quality.call_llm", side_effect=mock_call_llm_success)
def test_quality_agent_prompt_requires_structured_issue_schema(mock_llm, mock_knowledge):
    quality_agent({"diff_content": "def foo(): pass"})

    prompt = mock_llm.call_args.args[0]
    assert '"title": "问题短标题"' in prompt
    assert '"type": "complexity|duplication|naming|maintainability|other"' in prompt
    assert '"suggestion": "可执行的修改建议"' in prompt


@patch("src.agents.summary.call_llm", side_effect=mock_call_llm_success)
def test_summary_agent_prompt_includes_referenced_knowledge(mock_llm):
    summary_agent(
        {
            "reviews": [
                {
                    "agent": "security",
                    "risk": "HIGH",
                    "issues": [{"title": "SQL 注入"}],
                    "referenced_knowledge": [
                        {
                            "title": "历史 SQL 注入修复经验",
                            "risk": "HIGH",
                            "suggestion": "使用参数化查询。",
                        }
                    ],
                }
            ]
        }
    )

    prompt = mock_llm.call_args.args[0]
    assert "referenced_knowledge" in prompt
    assert "历史 SQL 注入修复经验" in prompt
    assert "历史经验参考" in prompt


@patch("src.agents.knowledge_context.retrieve_relevant_knowledge", return_value=[])
@patch("src.agents.quality.call_llm", side_effect=mock_call_llm_success)
def test_quality_agent_reviews_selected_packages(mock_llm, mock_knowledge):
    state = {"diff_content": "whole diff", "review_packages": [build_package()]}

    res = quality_agent(state)

    assert len(res["reviews"]) == 1
    review = res["reviews"][0]
    assert review["agent"] == "quality"
    assert review["package_id"] == 7
    assert review["package_key"] == "risk_domain:database"
    assert review["file_paths"] == ["src/api.py"]
    prompt = mock_llm.call_args.args[0]
    assert "# File: src/api.py" in prompt
    assert "whole diff" not in prompt


@patch("src.agents.security.call_llm", side_effect=mock_call_llm_success)
def test_security_agent_skips_when_package_not_selected(mock_llm):
    state = {"diff_content": "whole diff", "review_packages": [build_package()]}

    res = security_agent(state)

    assert res == {"reviews": []}
    mock_llm.assert_not_called()


@patch("src.agents.knowledge_context.retrieve_relevant_knowledge", return_value=[])
@patch("src.agents.architecture.call_llm", side_effect=mock_call_llm_success)
def test_architecture_agent_reviews_package_diff(mock_llm, mock_knowledge):
    state = {"diff_content": "whole diff", "review_packages": [build_package()]}

    res = architecture_agent(state)

    assert res["reviews"][0]["agent"] == "architecture"
    assert res["reviews"][0]["package_key"] == "risk_domain:database"
    prompt = mock_llm.call_args.args[0]
    assert "cursor.execute" in prompt
    assert "whole diff" not in prompt
