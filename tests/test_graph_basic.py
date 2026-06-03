import pytest
import uuid
from src.core.workflow import graph

def test_low_risk_flow():
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

def test_high_risk_interrupt_and_resume():
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
