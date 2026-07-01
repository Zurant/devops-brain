from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class GitLabCommentRecord(Base):
    """GitLab MR 评论回写记录。"""

    __tablename__ = "gitlab_comment_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("review_tasks.id", ondelete="CASCADE"), index=True, nullable=False)
    thread_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    project_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    mr_iid: Mapped[str] = mapped_column(String(128), nullable=False)
    comment_body: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, index=True, nullable=False, default=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    task = relationship("ReviewTask", back_populates="gitlab_comment_records")
