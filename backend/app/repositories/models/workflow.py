"""Persistence tables for backend-owned migration workflow state."""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
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
    execution_id: Mapped[str | None] = mapped_column(String(64), index=True)
    input_checksum: Mapped[str | None] = mapped_column(String(128))
    output_checksum: Mapped[str | None] = mapped_column(String(128))
    workspace_fingerprint: Mapped[str | None] = mapped_column(String(128))
    artifact_ids: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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


class RunEventSequenceModel(Base):
    """Per-run atomic event-sequence counter.

    Every workflow-event writer allocates its next sequence through this
    single counter row (see app.state.event_sequencer). The atomic
    UPDATE ... RETURNING guarantees that exactly one writer wins each
    sequence number per run, so concurrent appends can never surface an
    IntegrityError on uq_workflow_events_run_sequence.
    """

    __tablename__ = "run_event_sequences"

    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), primary_key=True)
    last_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AssistantConversationModel(Base):
    """Run-scoped durable assistant thread metadata."""
    __tablename__ = "assistant_conversations"
    __table_args__ = (UniqueConstraint("run_id", "conversation_id", name="uq_assistant_conversation_run"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AssistantMessageModel(Base):
    """Sanitized, ordered assistant exchange and its authoritative proof."""
    __tablename__ = "assistant_messages"
    __table_args__ = (
        UniqueConstraint("run_id", "idempotency_key", name="uq_assistant_message_run_idempotency"),
        Index("ix_assistant_messages_conversation_order", "conversation_id", "message_order"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    conversation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    message_order: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    input_manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    input_manifest_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    projection: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    proof_label: Mapped[str] = mapped_column(String(64), nullable=False)
    usage: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    model_provenance: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128), index=True)
    retry_of_message_id: Mapped[str | None] = mapped_column(String(64), index=True)
    semantic_state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    operational_event_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    intent: Mapped[str] = mapped_column(String(64), nullable=False, default="unsupported")
    capability_key: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    answer_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="concise")


class AssistantLifecycleEventModel(Base):
    """Durable replayable lifecycle stream for one run-scoped assistant."""
    __tablename__ = "assistant_lifecycle_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_assistant_lifecycle_run_sequence"),
        UniqueConstraint("run_id", "idempotency_key", "event_type", name="uq_assistant_lifecycle_request_event"),
        Index("ix_assistant_lifecycle_run_sequence", "run_id", "sequence"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    message_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SourceIntakeJobModel(Base):
    """Durable work item for the run-owned source-intake pipeline."""

    __tablename__ = "source_intake_jobs"
    __table_args__ = ()

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    thread_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    worker_id: Mapped[str | None] = mapped_column(String(128))
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(128))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    snapshot_id: Mapped[str | None] = mapped_column(String(64))
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)


class PlanningJobModel(Base):
    """Durable continuation for the post-G04 planning workflow."""

    __tablename__ = "planning_jobs"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key", name="uq_planning_jobs_run_idempotency"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    thread_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    current_step: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    worker_id: Mapped[str | None] = mapped_column(String(128))
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(128))
    last_error_code: Mapped[str | None] = mapped_column(String(128))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    last_error_stage: Mapped[str | None] = mapped_column(String(128))
    retryable: Mapped[bool | None] = mapped_column(Boolean)
    first_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terminal_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TransformationContinuationModel(Base):
    __tablename__ = "transformation_continuations"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_transformation_continuation_run"),
        UniqueConstraint("thread_id", name="uq_transformation_continuation_thread"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    current_stage_id: Mapped[str] = mapped_column(ForeignKey("migration_stages.id"), nullable=False, index=True)
    thread_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    current_node: Mapped[str] = mapped_column(String(64), nullable=False)
    g06_approval_id: Mapped[str] = mapped_column(ForeignKey("g06_approvals.id"), nullable=False)
    plan_id: Mapped[str] = mapped_column(ForeignKey("migration_plans.id"), nullable=False)
    plan_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    stage_plan_id: Mapped[str] = mapped_column(ForeignKey("stage_execution_plans.id"), nullable=False)
    stage_plan_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    worker_id: Mapped[str | None] = mapped_column(String(128), index=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    claim_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    wake_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_error_code: Mapped[str | None] = mapped_column(String(128))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_by: Mapped[str | None] = mapped_column(String(128))
    cancel_idempotency_key: Mapped[str | None] = mapped_column(String(128))
    cancel_request_checksum: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StageCheckpointModel(Base):
    __tablename__ = "stage_checkpoints"
    __table_args__ = (
        UniqueConstraint("stage_id", "sequence", name="uq_stage_checkpoint_sequence"),
        Index(
            "uq_stage_checkpoint_sealed",
            "stage_id",
            unique=True,
            sqlite_where=text("sealed = 1"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(ForeignKey("migration_stages.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    source_checkpoint_id: Mapped[str | None] = mapped_column(ForeignKey("stage_checkpoints.id"))
    workspace_alias: Mapped[str] = mapped_column(String(128), nullable=False)
    workspace_path: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    manifest_artifact_id: Mapped[str | None] = mapped_column(String(128))
    manifest_checksum: Mapped[str | None] = mapped_column(String(128))
    created_from_execution_id: Mapped[str | None] = mapped_column(ForeignKey("command_executions.id"))
    safe_for_resume: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sealed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StageReconstructionRecordModel(Base):
    """Durable governed ledger entry for one workspace reconstruction.

    Every reconstruction of a stage workspace is recorded here in the same
    transaction as the authoritative binding change: the immutable source
    checkpoint (id + fingerprint), the route/reason that drove the
    reconstruction, and the restored fingerprint it produced.
    """

    __tablename__ = "stage_reconstruction_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(ForeignKey("migration_stages.id"), nullable=False, index=True)
    checkpoint_id: Mapped[str | None] = mapped_column(ForeignKey("stage_checkpoints.id"), index=True)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    source_workspace_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    restored_workspace_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    created_from_execution_id: Mapped[str | None] = mapped_column(ForeignKey("command_executions.id"))
    attempt_id: Mapped[str | None] = mapped_column(ForeignKey("repair_attempts.id"))
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StagePromptRequestModel(Base):
    __tablename__ = "stage_prompt_requests"
    __table_args__ = (UniqueConstraint("execution_id", "prompt_checksum", name="uq_stage_prompt_execution_checksum"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(ForeignKey("migration_stages.id"), nullable=False, index=True)
    execution_id: Mapped[str] = mapped_column(ForeignKey("command_executions.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    detector_version: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    context_artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    prompt_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    pre_command_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    observed_fingerprint: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    explanation_invocation_id: Mapped[str | None] = mapped_column(ForeignKey("llm_invocations.id"))
    explanation_artifact_id: Mapped[str | None] = mapped_column(String(128))
    selected_option_id: Mapped[str | None] = mapped_column(String(128))
    decision_actor: Mapped[str | None] = mapped_column(String(128))
    decision_idempotency_key: Mapped[str | None] = mapped_column(String(128))
    decision_request_checksum: Mapped[str | None] = mapped_column(String(128))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reconstruction_checkpoint_id: Mapped[str | None] = mapped_column(ForeignKey("stage_checkpoints.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StageGatePackageModel(Base):
    __tablename__ = "stage_gate_packages"
    __table_args__ = (
        UniqueConstraint("run_id", "stage_id", "gate_id", "gate_version", name="uq_stage_gate_package"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(ForeignKey("migration_stages.id"), nullable=False, index=True)
    gate_id: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    gate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    package_artifact_id: Mapped[str] = mapped_column(String(128), nullable=False)
    package_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_set_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    plan_id: Mapped[str] = mapped_column(ForeignKey("migration_plans.id"), nullable=False)
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_plan_id: Mapped[str] = mapped_column(ForeignKey("stage_execution_plans.id"), nullable=False)
    stage_plan_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    workspace_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    expected_state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StageGateDecisionModel(Base):
    __tablename__ = "stage_gate_decisions"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key", name="uq_stage_gate_decision_idempotency"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    gate_package_id: Mapped[str] = mapped_column(ForeignKey("stage_gate_packages.id"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(ForeignKey("migration_stages.id"), nullable=False, index=True)
    gate_id: Mapped[str] = mapped_column(String(16), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    expected_state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    package_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    workspace_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StageWorkspaceBindingModel(Base):
    """Authoritative contained workspace binding for one prepared stage."""

    __tablename__ = "stage_workspace_bindings"
    __table_args__ = (UniqueConstraint("run_id", "stage_id", "alias", name="uq_stage_workspace_binding"),)

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(ForeignKey("migration_stages.id"), nullable=False, index=True)
    alias: Mapped[str] = mapped_column(String(128), nullable=False)
    workspace_path: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_checkpoint_id: Mapped[str | None] = mapped_column(ForeignKey("stage_checkpoints.id"))
    input_fingerprint: Mapped[str | None] = mapped_column(String(128))
    last_verified_fingerprint: Mapped[str | None] = mapped_column(String(128))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
    execution_id: Mapped[str | None] = mapped_column(String(64), index=True)
    owner_reference: Mapped[str | None] = mapped_column(String(128))
    mime_type: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    immutable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    redacted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    correlation_id: Mapped[str | None] = mapped_column(String(128))
    safe_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class CommandTemplateModel(Base):
    """One registered command template in the structured registry."""
    __tablename__ = "command_templates"
    __table_args__ = (UniqueConstraint("command_id", "version", name="uq_command_templates_command_version"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    command_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    executable: Mapped[str] = mapped_column(String(128), nullable=False)
    arguments: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    executable_aliases: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    allowed_env_vars: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    max_output_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CommandAuthorizationAuditModel(Base):
    """Authorization audit record for every policy engine decision."""
    __tablename__ = "command_authorization_audits"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key", name="uq_cmd_auth_audit_run_idempotency"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str | None] = mapped_column(ForeignKey("migration_stages.id"), index=True)
    command_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    template_id: Mapped[str | None] = mapped_column(String(64))
    template_version: Mapped[int | None] = mapped_column(Integer)
    plan_id: Mapped[str | None] = mapped_column(String(64))
    plan_version: Mapped[int | None] = mapped_column(Integer)
    executable: Mapped[str] = mapped_column(String(128), nullable=False)
    arguments: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    decision: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expected_state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    execution_profile_id: Mapped[str | None] = mapped_column(String(128))
    workspace_alias: Mapped[str | None] = mapped_column(String(128))
    network_profile: Mapped[str | None] = mapped_column(String(64))
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(128))
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CommandLogChunkModel(Base):
    """One ordered log chunk from a command execution (S3-F03)."""
    __tablename__ = "command_log_chunks"
    __table_args__ = (
        Index("ix_cmd_log_chunks_exec_seq", "execution_id", "sequence"),
        UniqueConstraint("execution_id", "sequence", name="uq_cmd_log_chunks_exec_seq"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    execution_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    stream: Mapped[str] = mapped_column(String(16), nullable=False)  # stdout, stderr, system
    text: Mapped[str] = mapped_column(Text, nullable=False)
    redacted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    byte_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    character_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correlation_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CommandLogSummaryModel(Base):
    """Durable bounded-output cursor and finalization state for one execution."""
    __tablename__ = "command_log_summaries"

    execution_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    first_sequence: Mapped[int | None] = mapped_column(Integer)
    last_sequence: Mapped[int | None] = mapped_column(Integer)
    stdout_chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stderr_chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stdout_stored_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stderr_stored_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stdout_truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stderr_truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    redaction_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    finalized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    correlation_id: Mapped[str | None] = mapped_column(String(128))


class CommandExecutionModel(Base):
    __tablename__ = "command_executions"
    __table_args__ = (
        UniqueConstraint("run_id", "idempotency_key", name="uq_command_executions_run_idempotency"),
        Index(
            "uq_command_executions_active_run",
            "run_id",
            unique=True,
            sqlite_where=text("status IN ('queued', 'pending', 'running')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("migration_runs.id"), nullable=False, index=True)
    stage_id: Mapped[str | None] = mapped_column(ForeignKey("migration_stages.id"), index=True)
    authorization_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    template_id: Mapped[str | None] = mapped_column(String(64))
    template_version: Mapped[int | None] = mapped_column(Integer)
    plan_id: Mapped[str | None] = mapped_column(String(64))
    plan_version: Mapped[int | None] = mapped_column(Integer)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), index=True)
    request_payload_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(128), index=True)
    requested_by: Mapped[str | None] = mapped_column(String(128))
    executable: Mapped[str] = mapped_column(String(128), nullable=False)
    arguments: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    working_directory_alias: Mapped[str | None] = mapped_column(String(128))
    safe_relative_working_directory: Mapped[str | None] = mapped_column(String(512))
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
    claim_attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    prompt_request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    operation_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="read_only")
    checkpoint_id: Mapped[str | None] = mapped_column(String(64), index=True)
    parent_execution_id: Mapped[str | None] = mapped_column(
        ForeignKey("command_executions.id"), index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    process_id: Mapped[int | None] = mapped_column(Integer)
    failure_code: Mapped[str | None] = mapped_column(String(128))
    failure_message: Mapped[str | None] = mapped_column(Text)
    stdout_artifact_id: Mapped[str | None] = mapped_column(String(128))
    stderr_artifact_id: Mapped[str | None] = mapped_column(String(128))
    command_log_artifact_id: Mapped[str | None] = mapped_column(String(128))
    manifest_artifact_id: Mapped[str | None] = mapped_column(String(128))
    result_artifact_id: Mapped[str | None] = mapped_column(String(128))
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=True, default=list)
    start_fingerprint: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    end_fingerprint: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    blockers: Mapped[list[str]] = mapped_column(JSON, nullable=True, default=list)
    environment_blocker: Mapped[str | None] = mapped_column(String(128))
    state_version: Mapped[int] = mapped_column(Integer, nullable=True, default=1)
    authoritative_state_version: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
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
    checkpoint_id: Mapped[str | None] = mapped_column(ForeignKey("stage_checkpoints.id"), index=True)
    failure_evidence_artifact_id: Mapped[str | None] = mapped_column(String(128))
    failure_evidence_checksum: Mapped[str | None] = mapped_column(String(128))
    failure_route_artifact_id: Mapped[str | None] = mapped_column(String(128))
    failure_route_checksum: Mapped[str | None] = mapped_column(String(128))
    context_pack_artifact_id: Mapped[str | None] = mapped_column(String(128))
    context_pack_checksum: Mapped[str | None] = mapped_column(String(128))
    proposal_artifact_id: Mapped[str | None] = mapped_column(String(128))
    proposal_checksum: Mapped[str | None] = mapped_column(String(128))
    proposer_invocation_id: Mapped[str | None] = mapped_column(ForeignKey("llm_invocations.id"))
    review_artifact_id: Mapped[str | None] = mapped_column(String(128))
    review_checksum: Mapped[str | None] = mapped_column(String(128))
    reviewer_invocation_id: Mapped[str | None] = mapped_column(ForeignKey("llm_invocations.id"))
    g10_gate_package_id: Mapped[str | None] = mapped_column(ForeignKey("stage_gate_packages.id"))
    apply_ledger_artifact_id: Mapped[str | None] = mapped_column(String(128))
    apply_ledger_checksum: Mapped[str | None] = mapped_column(String(128))
    pre_fingerprint: Mapped[str | None] = mapped_column(String(128))
    post_fingerprint: Mapped[str | None] = mapped_column(String(128))
    validation_summary_artifact_id: Mapped[str | None] = mapped_column(String(128))
    validation_summary_checksum: Mapped[str | None] = mapped_column(String(128))
    failure_fingerprint: Mapped[str | None] = mapped_column(String(128), index=True)
    parent_attempt_id: Mapped[str | None] = mapped_column(ForeignKey("repair_attempts.id"))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    provider_http_status: Mapped[int | None] = mapped_column(Integer)
    provider_error_code: Mapped[str | None] = mapped_column(String(128))
    sanitized_provider_message: Mapped[str | None] = mapped_column(Text)
    provider_request_id: Mapped[str | None] = mapped_column(String(256))
    failure_stage: Mapped[str | None] = mapped_column(String(128))
    failure_subtype: Mapped[str | None] = mapped_column(String(128))
    transport_exception_type: Mapped[str | None] = mapped_column(String(128))
    endpoint_host: Mapped[str | None] = mapped_column(String(255))
    endpoint_path: Mapped[str | None] = mapped_column(String(128))
    retryable: Mapped[bool | None] = mapped_column(Boolean)
    response_received: Mapped[bool | None] = mapped_column(Boolean)
    response_content_type: Mapped[str | None] = mapped_column(String(128))
    response_bytes: Mapped[int | None] = mapped_column(Integer)
    response_sha256: Mapped[str | None] = mapped_column(String(128))
    response_kind: Mapped[str | None] = mapped_column(String(32))
    transport_started: Mapped[bool | None] = mapped_column(Boolean)
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
