from src.core.state import ReviewState

def orchestrator(state: ReviewState):
    """
    调度节点：接收到 webhook 的初始状态后，初始化各个必须字段。
    """
    return {
        "human_decision": None,
        "reviews": []
    }
