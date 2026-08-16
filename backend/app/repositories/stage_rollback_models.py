"""Persistence model for stage rollbacks (V2 F25-04)."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class StageRollbackModel(Base):
    __tablename__ = "stage_rollbacks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    rollback_point_stage_order: Mapped[int | None] = mapped_column(Integer)
    sealed_stage_count: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_preserved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
