"""Persistence model for immutable migration routes (V2 F10-04)."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class MigrationRouteModel(Base):
    __tablename__ = "migration_routes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    source_major: Mapped[int] = mapped_column(Integer, nullable=False)
    target_major: Mapped[int] = mapped_column(Integer, nullable=False)
    catalogue_version: Mapped[str] = mapped_column(String(128), nullable=False)
    stages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    actor: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
