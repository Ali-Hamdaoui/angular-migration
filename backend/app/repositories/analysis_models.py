"""Durable Analysis evidence and G04 approval records."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class AnalysisMetadataModel(Base):
    __tablename__ = "analysis_metadata"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key", name="uq_analysis_metadata_run_idempotency"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    artifact_set_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    prerequisite_artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    workspace_fingerprint: Mapped[str | None] = mapped_column(String(128))
    plan_version: Mapped[str | None] = mapped_column(String(128))
    invocation_id: Mapped[str | None] = mapped_column(ForeignKey("llm_invocations.id"), index=True)
    # ``invocation_id`` is retained as the proposer compatibility pointer.  The
    # phase-specific pointers are authoritative for an Analysis attempt.
    proposer_invocation_id: Mapped[str | None] = mapped_column(ForeignKey("llm_invocations.id"), index=True)
    reviewer_invocation_id: Mapped[str | None] = mapped_column(ForeignKey("llm_invocations.id"), index=True)
    failed_invocation_id: Mapped[str | None] = mapped_column(ForeignKey("llm_invocations.id"), index=True)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    artifact_checksums: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    package: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(128))
    failure_subtype: Mapped[str | None] = mapped_column(String(128))
    failure_stage: Mapped[str | None] = mapped_column(String(128))
    retryable: Mapped[bool | None] = mapped_column(default=False)
    correlation_id: Mapped[str | None] = mapped_column(String(128))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class G04ApprovalModel(Base):
    __tablename__ = "g04_approvals"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key", name="uq_g04_approvals_run_idempotency"),)

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
    workspace_fingerprint: Mapped[str | None] = mapped_column(String(128))
    plan_version: Mapped[str | None] = mapped_column(String(128))
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    comment: Mapped[str | None] = mapped_column(Text)
    stale_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
