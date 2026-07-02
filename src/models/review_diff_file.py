from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.db.types import PortableJSONB


class ReviewDiffFile(Base):
    """MR 中单个变更文件的结构化 diff 分析结果。"""

    __tablename__ = "review_diff_files"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("review_tasks.id", ondelete="CASCADE"), index=True, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    old_path: Mapped[str | None] = mapped_column(Text)
    new_path: Mapped[str | None] = mapped_column(Text)
    change_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="modified")
    language: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="unknown")
    extension: Mapped[str | None] = mapped_column(String(32), index=True)
    directory: Mapped[str | None] = mapped_column(Text)
    additions: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    deletions: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    total_changes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    risk_domains: Mapped[list[str]] = mapped_column(PortableJSONB, nullable=False, default=list)
    is_large_file: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    analysis_metadata: Mapped[dict[str, Any] | None] = mapped_column(PortableJSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    task = relationship("ReviewTask", back_populates="diff_files")
