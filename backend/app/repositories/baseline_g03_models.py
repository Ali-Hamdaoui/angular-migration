"""Durable S1-F14 baseline qualification and G03 decision records."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class BaselineAssessmentModel(Base):
    __tablename__ = "baseline_assessments"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key", name="uq_baseline_assessments_run_idempotency"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    policy: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    blockers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    known_failures: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    evidence_confidence: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    evidence_set_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    sandbox_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    execution_profile_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    source_artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    artifact_checksums: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    package_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class G03ApprovalModel(Base):
    __tablename__ = "g03_approvals"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key", name="uq_g03_approvals_run_idempotency"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    gate_id: Mapped[str] = mapped_column(String(16), nullable=False)
    gate_version: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    decision: Mapped[str | None] = mapped_column(String(64))
    package_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence_set_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    qualification_status: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    sandbox_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    execution_profile_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    package: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    stale_reason: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
