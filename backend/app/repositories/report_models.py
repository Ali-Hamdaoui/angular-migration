"""Persistence record for the durable G15 report approval boundary."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class ReportRecordModel(Base):
    __tablename__ = "report_records"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key", name="uq_report_records_run_idempotency"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    gate_id: Mapped[str] = mapped_column(String(16), nullable=False)
    gate_version: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    decision: Mapped[str | None] = mapped_column(String(64))
    package_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_set_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    report_checksum: Mapped[str | None] = mapped_column(String(128))
    narrative_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    package: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    stale_reason: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
