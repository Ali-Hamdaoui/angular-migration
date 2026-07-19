"""Persistence tables for backend-owned migration workflow state."""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class MigrationRunModel(Base):
    __tablename__ = "migration_runs"
    __table_args__ = (Index("uq_migration_runs_graph_thread", "graph_thread_id", unique=True),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    run_phase: Mapped[str] = mapped_column(String(64), nullable=False)
    phase_status: Mapped[str] = mapped_column(String(64), nullable=False, default="running")
    approval_status: Mapped[str] = mapped_column(String(64), nullable=False, default="not_required")
    repair_status: Mapped[str] = mapped_column(String(64), nullable=False, default="not_required")
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_version_family: Mapped[str | None] = mapped_column(String(32))
    target_version_family: Mapped[str | None] = mapped_column(String(32))
    source_version_detected: Mapped[str | None] = mapped_column(String(64))
    target_version_resolved: Mapped[str | None] = mapped_column(String(64))
    source_angular_version: Mapped[str | None] = mapped_column(String(32))
    target_angular_version: Mapped[str | None] = mapped_column(String(32))
    preflight_id: Mapped[str | None] = mapped_column(String(64), index=True)
    source_path: Mapped[str | None] = mapped_column(Text)
    target_output_path: Mapped[str | None] = mapped_column(Text)  # legacy compatibility projection
    target_parent_path: Mapped[str | None] = mapped_column(Text)
    generated_output_name: Mapped[str | None] = mapped_column(String(255))
    resolved_output_root: Mapped[str | None] = mapped_column(Text, index=True)
    run_root: Mapped[str | None] = mapped_column(Text)
    artifact_root: Mapped[str | None] = mapped_column(Text)
    log_root: Mapped[str | None] = mapped_column(Text)
    report_root: Mapped[str | None] = mapped_column(Text)
    temporary_root: Mapped[str | None] = mapped_column(Text)
    migrated_app_path: Mapped[str | None] = mapped_column(Text)
    workspace_aliases: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    output_layout_version: Mapped[str | None] = mapped_column(String(64))
    graph_thread_id: Mapped[str | None] = mapped_column(String(128))
    client_constraints: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    target_policy_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    run_policy_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    pricing_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    actor: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MigrationStageModel(Base):
    __tablename__ = "migration_stages"
    __table_args__ = (UniqueConstraint("run_id", "stage_order", name="uq_migration_stages_run_order"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_order: Mapped[int] = mapped_column(Integer, nullable=False)
    source_version_family: Mapped[str | None] = mapped_column(String(32))
    target_version_family: Mapped[str | None] = mapped_column(String(32))
    source_version_detected: Mapped[str | None] = mapped_column(String(64))
    target_version_resolved: Mapped[str | None] = mapped_column(String(64))
    source_angular_version: Mapped[str | None] = mapped_column(String(32))
    target_angular_version: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    current_agent: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StageStepModel(Base):
    __tablename__ = "stage_steps"
    __table_args__ = (Index("ix_stage_steps_run_stage", "run_id", "stage_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str | None] = mapped_column(ForeignKey("migration_stages.id"), index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    component_type: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_id: Mapped[str | None] = mapped_column(String(64), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentExecutionModel(Base):
    __tablename__ = "agent_executions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str | None] = mapped_column(ForeignKey("migration_stages.id"), index=True)
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str | None] = mapped_column(Text)


class WorkflowEventModel(Base):
    __tablename__ = "workflow_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_workflow_events_run_sequence"),
        UniqueConstraint("run_id", "idempotency_key", name="uq_workflow_events_run_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str | None] = mapped_column(ForeignKey("migration_stages.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), index=True)
    actor: Mapped[str | None] = mapped_column(String(128))
    reason: Mapped[str | None] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApprovalEventModel(Base):
    __tablename__ = "approval_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str | None] = mapped_column(ForeignKey("migration_stages.id"), index=True)
    decision: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actor: Mapped[str | None] = mapped_column(String(128))
    rationale: Mapped[str | None] = mapped_column(Text)


class ApprovalPolicyEventModel(Base):
    __tablename__ = "approval_policy_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(64), nullable=False)
    changed_by: Mapped[str] = mapped_column(String(128), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)


class ArtifactMetadataModel(Base):
    __tablename__ = "artifact_metadata"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str | None] = mapped_column(ForeignKey("migration_stages.id"), index=True)
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CommandExecutionModel(Base):
    __tablename__ = "command_executions"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key", name="uq_command_executions_run_idempotency"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str | None] = mapped_column(ForeignKey("migration_stages.id"), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), index=True)
    requested_by: Mapped[str | None] = mapped_column(String(128))
    executable: Mapped[str] = mapped_column(String(128), nullable=False)
    arguments: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    working_directory_alias: Mapped[str | None] = mapped_column(String(128))
    runtime_profile_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_code: Mapped[int | None] = mapped_column(Integer)
    command_id: Mapped[str] = mapped_column(String(128), nullable=True, index=True)
    requester: Mapped[str | None] = mapped_column(String(128))
    shell: Mapped[bool] = mapped_column(Boolean, nullable=True, default=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=True)
    network_profile: Mapped[str] = mapped_column(String(128), nullable=True)
    cancellation_policy: Mapped[str] = mapped_column(String(64), nullable=True)
    runtime_checksum: Mapped[str | None] = mapped_column(String(128))
    baseline_checksum: Mapped[str | None] = mapped_column(String(128))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    timed_out: Mapped[bool] = mapped_column(Boolean, nullable=True, default=False)
    cancelled: Mapped[bool] = mapped_column(Boolean, nullable=True, default=False)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_by: Mapped[str | None] = mapped_column(String(128))
    cancel_idempotency_key: Mapped[str | None] = mapped_column(String(128))
    reconstruction_required: Mapped[bool] = mapped_column(Boolean, nullable=True, default=False)
    worker_id: Mapped[str | None] = mapped_column(String(128))
    stdout_artifact_id: Mapped[str | None] = mapped_column(String(128))
    stderr_artifact_id: Mapped[str | None] = mapped_column(String(128))
    command_log_artifact_id: Mapped[str | None] = mapped_column(String(128))
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=True, default=list)
    start_fingerprint: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    end_fingerprint: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    blockers: Mapped[list[str]] = mapped_column(JSON, nullable=True, default=list)
    environment_blocker: Mapped[str | None] = mapped_column(String(128))
    state_version: Mapped[int] = mapped_column(Integer, nullable=True, default=1)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=True, default=1)


class WorkerLeaseModel(Base):
    __tablename__ = "worker_leases"
    __table_args__ = (Index("ix_worker_leases_run_owner", "run_id", "worker_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    execution_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    worker_id: Mapped[str] = mapped_column(String(128), nullable=False)
    lease_owner: Mapped[str] = mapped_column(String(128), nullable=False)
    backend_instance_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class ActiveRunClaimModel(Base):
    """Durable single-run and target ownership claim."""

    __tablename__ = "active_run_claims"
    __table_args__ = (UniqueConstraint("run_id", name="uq_active_run_claim_run"), UniqueConstraint("target_output_path", name="uq_active_run_claim_target"))

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    target_output_path: Mapped[str] = mapped_column(Text, nullable=False)
    lease_owner: Mapped[str] = mapped_column(String(128), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class RepairAttemptModel(Base):
    __tablename__ = "repair_attempts"
    __table_args__ = (UniqueConstraint("run_id", "stage_id", "attempt_number", name="uq_repair_attempts_stage_attempt"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(ForeignKey("migration_stages.id"), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    diagnosis: Mapped[str | None] = mapped_column(Text)


class LlmUsageRecordModel(Base):
    __tablename__ = "llm_usage_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    input_price_per_million: Mapped[float] = mapped_column(Float, nullable=False)
    output_price_per_million: Mapped[float] = mapped_column(Float, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LlmInvocationModel(Base):
    __tablename__ = 'llm_invocations'
    __table_args__ = (UniqueConstraint('run_id', 'idempotency_key', name='uq_llm_invocations_run_idempotency'),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey('migration_runs.id'), nullable=False, index=True)
    stage_id: Mapped[str | None] = mapped_column(ForeignKey('migration_stages.id'), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    input_hashes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    deployment_alias: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(128), nullable=False)
    pricing_version: Mapped[str] = mapped_column(String(128), nullable=False, default='unknown')
    stage: Mapped[str | None] = mapped_column(String(128))
    redacted_summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    failure_code: Mapped[str | None] = mapped_column(String(64))
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    artifact_checksums: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UsageCostRecordModel(Base):
    __tablename__ = 'usage_cost_records'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    invocation_id: Mapped[str] = mapped_column(ForeignKey('llm_invocations.id'), nullable=False, unique=True)
    run_id: Mapped[str] = mapped_column(ForeignKey('migration_runs.id'), nullable=False, index=True)
    stage_id: Mapped[str | None] = mapped_column(ForeignKey('migration_stages.id'), index=True)
    pricing_version: Mapped[str] = mapped_column(String(128), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    input_price_per_million: Mapped[float] = mapped_column(Float, nullable=False)
    output_price_per_million: Mapped[float] = mapped_column(Float, nullable=False)
    input_cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    output_cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    total_cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RunAssuranceStatusModel(Base):
    __tablename__ = "run_assurance_statuses"

    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), primary_key=True)
    technical_upgrade_status: Mapped[str] = mapped_column(String(64), nullable=False)
    functional_parity_status: Mapped[str] = mapped_column(String(64), nullable=False)
    security_assurance_status: Mapped[str] = mapped_column(String(64), nullable=False)
    quality_assurance_status: Mapped[str] = mapped_column(String(64), nullable=False)
    delivery_readiness: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
class EnvironmentCapabilityModel(Base):
    __tablename__ = "environment_capability_snapshots"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_environment_capability_idempotency"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    artifacts: Mapped[dict[str, str] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EnvironmentDiagnosticEventModel(Base):
    __tablename__ = "environment_diagnostic_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(128))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
class SourceAnalysisModel(Base):
    __tablename__ = "source_analyses"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_source_analysis_idempotency"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
class PathValidationModel(Base):
    __tablename__ = "path_validations"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_path_validation_idempotency"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_fingerprint: Mapped[str | None] = mapped_column(String(128))
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TargetReservationModel(Base):
    __tablename__ = "target_reservations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    validation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_path: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

class SourceSnapshotModel(Base):
    __tablename__ = "source_snapshots"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key", name="uq_source_snapshots_run_idempotency"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    execution_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    backend_instance_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_path: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_id: Mapped[str | None] = mapped_column(String(128))
    fingerprint: Mapped[str | None] = mapped_column(String(128))
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    exclusions: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False, default=list)
    git_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApprovalGateModel(Base):
    """Persist approval gate decisions bound to a run."""
    __tablename__ = "workflow_approval_gates"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key", name="uq_workflow_approval_gates_run_idempotency"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    gate_id: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    gate_version: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    decision: Mapped[str | None] = mapped_column(String(64))
    package_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_set_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    comment: Mapped[str | None] = mapped_column(Text)
    stale_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StageValidationModel(Base):
    """Persist final install and static checks results for a stage validation run."""
    __tablename__ = "stage_validations"
    __table_args__ = (UniqueConstraint("run_id", "stage_id", name="uq_stage_validations_run_stage"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(ForeignKey("migration_stages.id"), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    step_config: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    install_succeeded: Mapped[bool | None] = mapped_column(Boolean, default=False)
    all_checks_passed: Mapped[bool | None] = mapped_column(Boolean, default=False)
    check_results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    install_log_artifact_id: Mapped[str | None] = mapped_column(String(128))
    static_checks_report_artifact_id: Mapped[str | None] = mapped_column(String(128))
    dependency_tree_artifact_id: Mapped[str | None] = mapped_column(String(128))
    validation_summary_artifact_id: Mapped[str | None] = mapped_column(String(128))
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    artifact_checksums: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StageBuildModel(Base):
    """Persist per-target build results for a stage."""
    __tablename__ = "stage_builds"
    __table_args__ = (UniqueConstraint("run_id", "stage_id", name="uq_stage_builds_run_stage"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(ForeignKey("migration_stages.id"), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    per_target_statuses: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    parser_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    artifact_checksums: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StageTestModel(Base):
    """Persist test and conditional lint results for a stage."""
    __tablename__ = "stage_tests"
    __table_args__ = (UniqueConstraint("run_id", "stage_id", name="uq_stage_tests_run_stage"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(ForeignKey("migration_stages.id"), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    test_status: Mapped[str | None] = mapped_column(String(32))
    lint_status: Mapped[str | None] = mapped_column(String(32))
    test_results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    lint_results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    failure_comparison: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    artifact_checksums: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StageAssuranceModel(Base):
    """Persist parity comparison and assurance dimensions for a stage."""
    __tablename__ = "stage_assurances"
    __table_args__ = (UniqueConstraint("run_id", "stage_id", name="uq_stage_assurances_run_stage"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(ForeignKey("migration_stages.id"), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    comparison_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    assurance_dimensions: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    route_comparison_artifact_id: Mapped[str | None] = mapped_column(String(128))
    backend_comparison_artifact_id: Mapped[str | None] = mapped_column(String(128))
    risk_rollup_artifact_id: Mapped[str | None] = mapped_column(String(128))
    parity_checklist_artifact_id: Mapped[str | None] = mapped_column(String(128))
    assurance_summary_artifact_id: Mapped[str | None] = mapped_column(String(128))
    g09_package_artifact_id: Mapped[str | None] = mapped_column(String(128))
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    artifact_checksums: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StageSealModel(Base):
    """Persist stage seal output fingerprint and completeness report."""
    __tablename__ = "stage_seals"
    __table_args__ = (UniqueConstraint("run_id", "stage_id", name="uq_stage_seals_run_stage"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(ForeignKey("migration_stages.id"), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    output_fingerprint: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    completeness_report: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    cleanup_report_artifact_id: Mapped[str | None] = mapped_column(String(128))
    cleanliness_report_artifact_id: Mapped[str | None] = mapped_column(String(128))
    output_manifest_artifact_id: Mapped[str | None] = mapped_column(String(128))
    stage_evidence_index_artifact_id: Mapped[str | None] = mapped_column(String(128))
    g12_package_artifact_id: Mapped[str | None] = mapped_column(String(128))
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    artifact_checksums: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StageCopyForwardRecord(Base):
    """Persist copy-forward between stages."""
    __tablename__ = "stage_copy_forward_records"
    __table_args__ = (UniqueConstraint("run_id", "source_stage_id", name="uq_copy_forward_run_source"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    source_stage_id: Mapped[str] = mapped_column(ForeignKey("migration_stages.id"), nullable=False, index=True)
    target_stage_id: Mapped[str] = mapped_column(ForeignKey("migration_stages.id"), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    next_stage_created: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sandbox_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    artifact_checksums: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OutputFingerprintModel(Base):
    """Persist output fingerprint snapshot for a stage."""
    __tablename__ = "output_fingerprints"
    __table_args__ = (UniqueConstraint("run_id", "stage_id", name="uq_output_fingerprints_run_stage"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(ForeignKey("migration_stages.id"), nullable=False, index=True)
    fingerprint: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class G09ApprovalModel(Base):
    """Persist G09 validation gate approval records."""
    __tablename__ = "g09_approvals"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key", name="uq_g09_approvals_run_idempotency"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(ForeignKey("migration_stages.id"), nullable=False, index=True)
    gate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    gate_version: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    decision: Mapped[str | None] = mapped_column(String(64))
    package_checksum: Mapped[str | None] = mapped_column(String(128))
    artifact_set_checksum: Mapped[str | None] = mapped_column(String(128))
    workspace_fingerprint: Mapped[str | None] = mapped_column(String(128))
    plan_version: Mapped[str | None] = mapped_column(String(128))
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    comment: Mapped[str | None] = mapped_column(Text)
    stale_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class G12ApprovalModel(Base):
    """Persist G12 seal gate approval records."""
    __tablename__ = "g12_approvals"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key", name="uq_g12_approvals_run_idempotency"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(ForeignKey("migration_stages.id"), nullable=False, index=True)
    gate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    gate_version: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    decision: Mapped[str | None] = mapped_column(String(64))
    package_checksum: Mapped[str | None] = mapped_column(String(128))
    artifact_set_checksum: Mapped[str | None] = mapped_column(String(128))
    workspace_fingerprint: Mapped[str | None] = mapped_column(String(128))
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    comment: Mapped[str | None] = mapped_column(Text)
    stale_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
