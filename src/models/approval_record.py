from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class ApprovalRecord(Base):
    """人工审批记录。"""

    __tablename__ = "approval_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("review_tasks.id", ondelete="CASCADE"), index=True, nullable=False)
    thread_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    decision: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    operator: Mapped[str | None] = mapped_column(String(128))
    original_comment: Mapped[str | None] = mapped_column(Text)
    modified_comment: Mapped[str | None] = mapped_column(Text)
    comment_posted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    task = relationship("ReviewTask", back_populates="approval_records")
