"""Persistence records for G03 Angular transformation, evidence, and G08 approval."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class AngularUpdateRecordModel(Base):
    """Persistent record of an Angular update execution and version verification."""

    __tablename__ = "angular_update_records"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key", name="uq_angular_update_run_idempotency"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_version_status: Mapped[str] = mapped_column(String(32), nullable=False)
    resolved_target_version: Mapped[str | None] = mapped_column(String(64))
    source_version: Mapped[str] = mapped_column(String(64), nullable=False)
    target_version: Mapped[str] = mapped_column(String(64), nullable=False)
    command_execution_id: Mapped[str | None] = mapped_column(String(64))
    prompt_detected: Mapped[str] = mapped_column(String(32), nullable=False, default="no_prompt")
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TransformationEvidenceModel(Base):
    """Persistent record of transformation diff, risk classification, and forbidden changes."""

    __tablename__ = "transformation_evidence"
    __table_args__ = (
        UniqueConstraint("run_id", "idempotency_key", name="uq_transformation_evidence_run_idempotency"),
        Index("ix_transformation_evidence_run_stage_created", "run_id", "stage_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(ForeignKey("migration_stages.id"), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    overall_risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    total_files_changed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    diff_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    diff_summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    package_change_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    migration_list: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    forbidden_changes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    changed_file_classifications: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    evidence_complete: Mapped[bool] = mapped_column(nullable=False, default=False)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    block_reason: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    input_fingerprint: Mapped[str | None] = mapped_column(String(128))
    target_fingerprint: Mapped[str | None] = mapped_column(String(128))
    request_checksum: Mapped[str | None] = mapped_column(String(128))
    gate_version: Mapped[str] = mapped_column(String(32), nullable=False, default="g03-evidence-v1")
    source_sandbox_path: Mapped[str | None] = mapped_column(String(512))
    target_sandbox_path: Mapped[str | None] = mapped_column(String(512))
    evidence_schema_version: Mapped[str] = mapped_column(String(64), nullable=False, default="transformation-evidence-v2")
    angular_update_record_id: Mapped[str | None] = mapped_column(ForeignKey("angular_update_records.id"), index=True)
    angular_update_binding_checksum: Mapped[str | None] = mapped_column(String(128))
    inventory_checksum: Mapped[str | None] = mapped_column(String(128))
    builder_comparison: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    risk_report: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    artifact_manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    artifact_set_checksum: Mapped[str | None] = mapped_column(String(128))
    integrity_status: Mapped[str] = mapped_column(String(32), nullable=False, default="in_progress", index=True)
    stale_reason: Mapped[str | None] = mapped_column(Text)
    failure_code: Mapped[str | None] = mapped_column(String(128))
    computation_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    computation_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class G08ApprovalModel(Base):
    """Persistent G08 transformation acceptance gate record."""

    __tablename__ = "g08_approvals"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key", name="uq_g08_approvals_run_idempotency"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(String(64), nullable=False)
    gate_id: Mapped[str] = mapped_column(String(16), nullable=False)
    gate_version: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    decision: Mapped[str | None] = mapped_column(String(64))
    package_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_set_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    workspace_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    package: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    stale_reason: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    request_checksum: Mapped[str] = mapped_column(String(128), nullable=False, server_default="sha256:" + "0" * 64)
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    plan_version: Mapped[int | None] = mapped_column(Integer)
    plan_checksum: Mapped[str | None] = mapped_column(String(128))
    package_artifact_id: Mapped[str | None] = mapped_column(String(64))
    parent_gate_record_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
