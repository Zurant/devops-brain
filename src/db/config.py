import os


def get_database_url() -> str:
    """读取业务数据库连接地址。"""
    return os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://devops_brain:devops_brain@localhost:5432/devops_brain",
    )
