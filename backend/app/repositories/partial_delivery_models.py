"""Persistence model for partial deliveries (V2 F26-04)."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class PartialDeliveryModel(Base):
    __tablename__ = "partial_deliveries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    delivered_at_stage: Mapped[int | None] = mapped_column(Integer)
    delivered_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    validated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    remaining_stages: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    resumable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    blockers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
