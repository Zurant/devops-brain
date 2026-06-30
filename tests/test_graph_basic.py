import pytest
import uuid
import json
from unittest.mock import patch
from src.core.workflow import graph

def mock_call_llm(prompt: str, agent_name: str = "unknown", model: str = None) -> str:
    if agent_name == "summary":
        risk = "HIGH" if "HIGH_RISK" in prompt or '"risk": "HIGH"' in prompt else "LOW"
        return json.dumps({
            "final_risk_level": risk,
            "summary_report": f"Mock summary risk: {risk}",
            "final_comment": f"Mock GitLab comment risk: {risk}"
        })

    risk = "HIGH" if "HIGH_RISK" in prompt else "LOW"
    return json.dumps({
        "agent": agent_name,
        "issues": [{"description": "Mock high risk issue"}] if risk == "HIGH" else [],
        "risk": risk
    })

@patch("src.agents.quality.call_llm", side_effect=mock_call_llm)
@patch("src.agents.security.call_llm", side_effect=mock_call_llm)
@patch("src.agents.architecture.call_llm", side_effect=mock_call_llm)
@patch("src.agents.summary.call_llm", side_effect=mock_call_llm)
def test_low_risk_flow(*_):
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    initial_state = {
        "mr_id": "1",
        "project_id": "1",
        "diff_content": "normal code update",
        "mr_url": "http://example.com/mr/1"
    }
    
    # 执行图
    graph.invoke(initial_state, config=config)
    
    # 验证最终状态
    state = graph.get_state(config)
    assert state.values.get("final_risk_level") == "LOW"
    # 不应该挂起
    assert "human_review" not in (state.next or [])

@patch("src.agents.quality.call_llm", side_effect=mock_call_llm)
@patch("src.agents.security.call_llm", side_effect=mock_call_llm)
@patch("src.agents.architecture.call_llm", side_effect=mock_call_llm)
@patch("src.agents.summary.call_llm", side_effect=mock_call_llm)
def test_high_risk_interrupt_and_resume(*_):
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    initial_state = {
        "mr_id": "2",
        "project_id": "1",
        "diff_content": "some code with HIGH_RISK",
        "mr_url": "http://example.com/mr/2"
    }
    
    # 第一次执行，预期在 human_review 前被 interrupt
    graph.invoke(initial_state, config=config)
    
    state = graph.get_state(config)
    assert state.values.get("final_risk_level") == "HIGH"
    
    # 验证是否挂起（next 会包含将要执行的节点，或者是在条件边中断）
    assert state.next and ("human_review" in state.next or "summary:edges" in state.next)
    
    # 模拟人类通过 resume API 恢复，传入 decision
    graph.update_state(config, {"human_decision": "approve"})
    graph.invoke(None, config=config)
    
    # 再次获取状态验证完成
    final_state = graph.get_state(config)
    assert final_state.values.get("human_decision") == "approve"
    assert not final_state.next  # 图已执行完 END
