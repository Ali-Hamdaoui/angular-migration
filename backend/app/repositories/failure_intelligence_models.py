"""Persistence model for failure intelligence snapshots (V2 F19-04)."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class FailureIntelligenceModel(Base):
    __tablename__ = "failure_intelligence"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    groups: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    root_causes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    graph: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
