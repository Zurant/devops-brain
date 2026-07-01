import os

from dotenv import load_dotenv
from redis import Redis
from rq import Queue


load_dotenv()


def get_queue_name() -> str:
    return os.getenv("REVIEW_QUEUE_NAME", "devops-brain")


def get_redis_connection() -> Redis:
    """创建 Redis 连接，默认连接本地 Redis。"""
    return Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


def get_review_queue() -> Queue:
    """获取代码审查任务队列。"""
    return Queue(get_queue_name(), connection=get_redis_connection())
