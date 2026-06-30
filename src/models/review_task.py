from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class ReviewTask(Base):
    """一次 GitLab MR 审查任务。"""

    __tablename__ = "review_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    project_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    mr_iid: Mapped[str] = mapped_column(String(128), nullable=False)
    mr_url: Mapped[str | None] = mapped_column(Text)
    source_branch: Mapped[str | None] = mapped_column(String(255))
    target_branch: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="running")
    final_risk_level: Mapped[str | None] = mapped_column(String(16), index=True)
    summary_report: Mapped[str | None] = mapped_column(Text)
    final_comment: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    agent_reviews = relationship("AgentReview", back_populates="task", cascade="all, delete-orphan")
    approval_records = relationship("ApprovalRecord", back_populates="task", cascade="all, delete-orphan")
