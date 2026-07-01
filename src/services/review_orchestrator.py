from typing import Any

from sqlalchemy.orm import Session

from src.api.globals import pending_reviews
from src.core.workflow import graph
from src.services.review_task_service import (
    mark_task_failed,
    mark_task_running,
    record_gitlab_comment_result,
    update_task_from_graph_state,
)
from src.tools.gitlab_client import post_mr_comment


def run_review_job(
    db: Session,
    *,
    thread_id: str,
    initial_state: dict[str, Any],
) -> dict[str, str]:
    """执行一次 MR 审查任务，并把结果写回数据库。"""
    config = {"configurable": {"thread_id": thread_id}}
    mark_task_running(db, thread_id)

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

        project_id = current_values.get("project_id", "mock")
        mr_id = current_values.get("mr_id", "mock")
        final_comment = current_values.get("final_comment", "")
        try:
            post_mr_comment(project_id, mr_id, final_comment)
            record_gitlab_comment_result(
                db,
                thread_id=thread_id,
                project_id=project_id,
                mr_iid=mr_id,
                comment_body=final_comment,
                source="auto",
                success=True,
            )
        except Exception as exc:
            record_gitlab_comment_result(
                db,
                thread_id=thread_id,
                project_id=project_id,
                mr_iid=mr_id,
                comment_body=final_comment,
                source="auto",
                success=False,
                error_message=str(exc),
            )
            raise
        update_task_from_graph_state(db, thread_id, current_values, status="completed")
        return {"status": "completed", "thread_id": thread_id}
    except Exception as exc:
        mark_task_failed(db, thread_id, str(exc))
        raise
