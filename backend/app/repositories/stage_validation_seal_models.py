"""Persistence model for stage validation seals (V2 F24-04)."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class StageValidationSealModel(Base):
    __tablename__ = "stage_validation_seals"

    __table_args__ = (Index("ix_stage_validation_seals_stage_id", "stage_id", unique=True),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    stage_id: Mapped[str] = mapped_column(ForeignKey("migration_stages.id"), nullable=False)
    stage_order: Mapped[int] = mapped_column(Integer, nullable=False)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    source_major: Mapped[int] = mapped_column(Integer, nullable=False)
    target_major: Mapped[int] = mapped_column(Integer, nullable=False)
    validation_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    workspace_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    sealed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
