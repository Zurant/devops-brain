from dotenv import load_dotenv

from src.db.session import SessionLocal
from src.services.review_orchestrator import run_review_job


load_dotenv()


def process_review_job(thread_id: str, initial_state: dict) -> dict[str, str]:
    """RQ 后台任务入口。"""
    db = SessionLocal()
    try:
        return run_review_job(db, thread_id=thread_id, initial_state=initial_state)
    finally:
        db.close()
