from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.db.types import PortableJSONB


class ReviewPlan(Base):
    """一次 MR 的审查策略计划。"""

    __tablename__ = "review_plans"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("review_tasks.id", ondelete="CASCADE"), index=True, nullable=False)
    mr_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    review_strategy: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    approval_policy: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    required_agents: Mapped[list[str]] = mapped_column(PortableJSONB, nullable=False, default=list)
    risk_domains: Mapped[list[str]] = mapped_column(PortableJSONB, nullable=False, default=list)
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    total_changes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    package_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_large_mr: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    reason: Mapped[str | None] = mapped_column(Text)
    plan_metadata: Mapped[dict[str, Any] | None] = mapped_column(PortableJSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    task = relationship("ReviewTask", back_populates="review_plans")
    packages = relationship("ReviewPackage", back_populates="plan", cascade="all, delete-orphan")
