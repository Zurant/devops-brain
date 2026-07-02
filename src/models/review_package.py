from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.db.types import PortableJSONB


class ReviewPackage(Base):
    """Review Planner 拆分出的一个审查包。"""

    __tablename__ = "review_packages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("review_tasks.id", ondelete="CASCADE"), index=True, nullable=False)
    plan_id: Mapped[int] = mapped_column(ForeignKey("review_plans.id", ondelete="CASCADE"), index=True, nullable=False)
    package_key: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    package_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    directory: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(64), index=True)
    risk_domains: Mapped[list[str]] = mapped_column(PortableJSONB, nullable=False, default=list)
    file_paths: Mapped[list[str]] = mapped_column(PortableJSONB, nullable=False, default=list)
    selected_agents: Mapped[list[str]] = mapped_column(PortableJSONB, nullable=False, default=list)
    additions: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    deletions: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    total_changes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=50, server_default="50")
    requires_human: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    package_metadata: Mapped[dict[str, Any] | None] = mapped_column(PortableJSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    task = relationship("ReviewTask", back_populates="review_packages")
    plan = relationship("ReviewPlan", back_populates="packages")
