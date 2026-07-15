"""Durable S1-F10 baseline workspace and prequalification records."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class BaselineQualificationModel(Base):
    __tablename__ = "baseline_qualifications"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key", name="uq_baseline_qualifications_run_idempotency"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    snapshot_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sandbox_path: Mapped[str] = mapped_column(Text, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    sandbox_fingerprint: Mapped[str | None] = mapped_column(String(128))
    package: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    lockfile: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    scripts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    registry: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    blockers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    authorization_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_authorized")
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
