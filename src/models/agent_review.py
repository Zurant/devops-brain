from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.db.types import PortableJSONB


class AgentReview(Base):
    """单个专家 Agent 的审查输出。"""

    __tablename__ = "agent_reviews"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("review_tasks.id", ondelete="CASCADE"), index=True, nullable=False)
    agent_name: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    risk: Mapped[str | None] = mapped_column(String(16), index=True)
    issues: Mapped[list[dict[str, Any]] | None] = mapped_column(PortableJSONB)
    raw_response: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(PortableJSONB)
    model_name: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    task = relationship("ReviewTask", back_populates="agent_reviews")
