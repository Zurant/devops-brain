import os
import platform

from dotenv import load_dotenv
from rq import SimpleWorker, Worker

from src.queue.redis_client import get_queue_name, get_redis_connection


def select_worker_class():
    """macOS 本地开发默认使用非 fork worker，避免 Objective-C fork 崩溃。"""
    mode = os.getenv("RQ_WORKER_MODE", "simple" if platform.system() == "Darwin" else "fork")
    if mode == "simple":
        return SimpleWorker
    return Worker


def main() -> None:
    load_dotenv()
    worker_class = select_worker_class()
    worker = worker_class([get_queue_name()], connection=get_redis_connection())
    worker.work()


if __name__ == "__main__":
    main()
