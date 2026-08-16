"""Persistence model for project capability snapshots (V2 F13-03)."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class ProjectCapabilityModel(Base):
    __tablename__ = "project_capabilities"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str | None] = mapped_column(ForeignKey("migration_stages.id"), index=True)
    source_root: Mapped[str] = mapped_column(String(1024), nullable=False)
    angular_major: Mapped[int | None] = mapped_column(Integer)
    capabilities: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
