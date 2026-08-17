"""Persistence model for V2 plans (F18-04)."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class V2PlanningModel(Base):
    __tablename__ = "v2_plans"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    source_major: Mapped[int] = mapped_column(Integer, nullable=False)
    target_major: Mapped[int] = mapped_column(Integer, nullable=False)
    catalogue_version: Mapped[str] = mapped_column(String(128), nullable=False)
    capability_snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    capability_snapshot_checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    stages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
