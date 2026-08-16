"""Persistence model for governed proposal cycles (V2 F21-05)."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class ProposalCycleModel(Base):
    __tablename__ = "proposal_cycles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("repair_attempts.id"), nullable=False, index=True)
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False)
    proposal_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reviewer: Mapped[str | None] = mapped_column(String(128))
    hints: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    parent_cycle_id: Mapped[str | None] = mapped_column(String(64), index=True)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
