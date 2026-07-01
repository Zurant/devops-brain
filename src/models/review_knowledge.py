from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.db.types import PortableJSONB


class ReviewKnowledge(Base):
    """可复用的历史审查经验。"""

    __tablename__ = "review_knowledge"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    issue_type: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    risk: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    suggestion: Mapped[str | None] = mapped_column(Text)
    source_task_id: Mapped[int | None] = mapped_column(ForeignKey("review_tasks.id", ondelete="SET NULL"), index=True)
    source_thread_id: Mapped[str | None] = mapped_column(String(64), index=True)
    source_agent: Mapped[str | None] = mapped_column(String(64), index=True)
    tags: Mapped[list[str] | None] = mapped_column(PortableJSONB)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, default="anonymous")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    source_task = relationship("ReviewTask", back_populates="knowledge_entries")
