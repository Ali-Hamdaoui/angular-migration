"""Persistence model for third-party compatibility reports (V2 F15-04)."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class ThirdPartyCompatibilityReportModel(Base):
    __tablename__ = "third_party_compatibility_reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(ForeignKey("migration_stages.id"), nullable=False, index=True)
    source_major: Mapped[int] = mapped_column(Integer, nullable=False)
    target_major: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    blockers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    inventory: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
