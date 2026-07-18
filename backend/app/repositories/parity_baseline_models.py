from datetime import datetime
from typing import Any
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.repositories.models.base import Base


class ParityBaselineEvidenceModel(Base):
    __tablename__ = "parity_baseline_evidence"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key", name="uq_parity_baseline_run_idempotency"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    artifact_checksums: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    prerequisite_artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    error_code: Mapped[str | None] = mapped_column(String(128))
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
