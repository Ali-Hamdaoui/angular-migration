"""Persistence model for lockfile generation evidence (V2 F08-04)."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class LockfileGenerationEvidenceModel(Base):
    __tablename__ = "lockfile_generation_evidence"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(ForeignKey("migration_stages.id"), nullable=False, index=True)
    execution_id: Mapped[str | None] = mapped_column(String(64))
    lockfile_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    lockfile_version: Mapped[int | None] = mapped_column(Integer)
    source_family: Mapped[str] = mapped_column(String(32), nullable=False)
    target_family: Mapped[str] = mapped_column(String(32), nullable=False)
    node_version: Mapped[str | None] = mapped_column(String(64))
    npm_version: Mapped[str | None] = mapped_column(String(64))
    node_sha256: Mapped[str | None] = mapped_column(String(64))
    npm_sha256: Mapped[str | None] = mapped_column(String(64))
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False)
    blockers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    deterministic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
