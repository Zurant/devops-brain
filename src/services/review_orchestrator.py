from typing import Any

from sqlalchemy.orm import Session

from src.api.globals import pending_reviews
from src.core.workflow import graph
from src.services.review_task_service import update_task_from_graph_state, update_task_status
from src.tools.gitlab_client import post_mr_comment


def run_review_job(
    db: Session,
    *,
    thread_id: str,
    initial_state: dict[str, Any],
) -> dict[str, str]:
    """执行一次 MR 审查任务，并把结果写回数据库。"""
    config = {"configurable": {"thread_id": thread_id}}
    update_task_status(db, thread_id, "running")

    try:
        graph.invoke(initial_state, config=config)
        state = graph.get_state(config)
        current_values = state.values

        if state.next and ("human_review" in state.next or "summary:edges" in state.next):
            pending_reviews[thread_id] = {
                "mr_id": current_values.get("mr_id"),
                "project_id": current_values.get("project_id"),
                "mr_url": current_values.get("mr_url"),
                "final_risk_level": current_values.get("final_risk_level"),
                "summary_report": current_values.get("summary_report"),
                "final_comment": current_values.get("final_comment"),
            }
            update_task_from_graph_state(db, thread_id, current_values, status="waiting_human")
            return {"status": "paused", "thread_id": thread_id}

        post_mr_comment(
            current_values.get("project_id", "mock"),
            current_values.get("mr_id", "mock"),
            current_values.get("final_comment", ""),
        )
        update_task_from_graph_state(db, thread_id, current_values, status="completed")
        return {"status": "completed", "thread_id": thread_id}
    except Exception as exc:
        update_task_status(db, thread_id, "failed", error_message=str(exc))
        raise
