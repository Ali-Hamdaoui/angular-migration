"""Shared API contracts for the Migration Factory backend and Control Tower."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContractModel(BaseModel):
    """Base behavior for public, immutable API contract models."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class RunStatus(str, Enum):
    CREATED = "CREATED"
    SOURCE_VALIDATION_RUNNING = "SOURCE_VALIDATION_RUNNING"
    SOURCE_VALIDATED = "SOURCE_VALIDATED"
    WORKSPACE_CLASSIFICATION_RUNNING = "WORKSPACE_CLASSIFICATION_RUNNING"
    BASELINE_RUNNING = "BASELINE_RUNNING"
    BASELINE_QUALIFIED = "BASELINE_QUALIFIED"
    CLIENT_CONSTRAINTS_CAPTURED = "CLIENT_CONSTRAINTS_CAPTURED"
    ELIGIBILITY_RUNNING = "ELIGIBILITY_RUNNING"
    ANALYSIS_RUNNING = "ANALYSIS_RUNNING"
    WAITING_ANALYSIS_APPROVAL = "WAITING_ANALYSIS_APPROVAL"
    PLANNING_RUNNING = "PLANNING_RUNNING"
    WAITING_PLAN_APPROVAL = "WAITING_PLAN_APPROVAL"
    STAGE_CREATED = "STAGE_CREATED"
    TOOLCHAIN_PROFILE_SELECTED = "TOOLCHAIN_PROFILE_SELECTED"
    SANDBOX_READY = "SANDBOX_READY"
    DEPENDENCY_AUDITED = "DEPENDENCY_AUDITED"
    TRANSFORMATION_RUNNING = "TRANSFORMATION_RUNNING"
    STATIC_SYMBOL_CHECK_RUNNING = "STATIC_SYMBOL_CHECK_RUNNING"
    VALIDATION_RUNNING = "VALIDATION_RUNNING"
    REPAIR_RUNNING = "REPAIR_RUNNING"
    WAITING_REPAIR_APPROVAL = "WAITING_REPAIR_APPROVAL"
    REVIEW_READY = "REVIEW_READY"
    STAGE_COMMITTED = "STAGE_COMMITTED"
    STAGE_ROLLED_BACK = "STAGE_ROLLED_BACK"
    REPORT_RUNNING = "REPORT_RUNNING"
    DELIVERY_RUNNING = "DELIVERY_RUNNING"
    PAUSE_REQUESTED = "PAUSE_REQUESTED"
    PAUSED = "PAUSED"
    RESUMING = "RESUMING"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLING = "CANCELLING"
    TIMED_OUT = "TIMED_OUT"
    WORKER_LOST = "WORKER_LOST"
    RECOVERY_RUNNING = "RECOVERY_RUNNING"
    ORPHANED = "ORPHANED"
    CLEANUP_RUNNING = "CLEANUP_RUNNING"
    CLEANUP_FAILED = "CLEANUP_FAILED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DIAGNOSTIC_HOLD = "DIAGNOSTIC_HOLD"


class RunPhase(str, Enum):
    PREFLIGHT_SNAPSHOT = "PREFLIGHT_SNAPSHOT"
    DISCOVERY_BASELINE = "DISCOVERY_BASELINE"
    FEASIBILITY_PLANNING = "FEASIBILITY_PLANNING"
    STAGED_MIGRATION = "STAGED_MIGRATION"
    FINAL_ASSURANCE = "FINAL_ASSURANCE"
    DELIVERY_REPORTING = "DELIVERY_REPORTING"


class PhaseStatus(str, Enum):
    """Status of a workflow phase, independent from the run current state."""

    NOT_STARTED = "not_started"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StageStatus(str, Enum):
    PENDING = "PENDING"
    PREPARING = "preparing"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    REPAIRING = "REPAIRING"
    PASSED = "PASSED"
    PASSED_WITH_KNOWN_BASELINE_FAILURES = "passed_with_known_baseline_failures"
    PASSED_WITH_MANUAL_ITEMS = "passed_with_manual_items"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    CANCELLED = "CANCELLED"
    DIAGNOSTIC_HOLD = "DIAGNOSTIC_HOLD"


class StepStatus(str, Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    SKIPPED = "SKIPPED"
    MANUAL = "MANUAL"
    DEFERRED = "DEFERRED"
    ACCEPTED_RISK = "ACCEPTED_RISK"
    CANCELLED = "CANCELLED"


class AgentStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"


class DeterministicComponentType(str, Enum):
    SOURCE_INTAKE_VALIDATOR = "SourceIntakeValidator"
    SNAPSHOT_SERVICE = "SnapshotService"
    WORKSPACE_TOPOLOGY_CLASSIFIER = "WorkspaceTopologyClassifier"
    COMPATIBILITY_RESOLVER = "CompatibilityResolver"
    TOOLCHAIN_RUNTIME_MANAGER = "ToolchainRuntimeManager"
    COMMAND_POLICY_ENGINE = "CommandPolicyEngine"
    BASELINE_QUALIFICATION_SERVICE = "BaselineQualificationService"
    STATIC_SYMBOL_GATE = "StaticSymbolGate"
    PARITY_EVIDENCE_ENGINE = "ParityEvidenceEngine"
    CHECKPOINT_SERVICE = "CheckpointService"
    ARTIFACT_SERVICE = "ArtifactService"
    WORKER_SUPERVISOR = "WorkerSupervisor"
    DELIVERY_SERVICE = "DeliveryService"


class AgentKind(str, Enum):
    ANALYSIS = "AnalysisAgent"
    PLANNING = "PlanningAgent"
    TRANSFORMATION = "TransformationAgent"
    BUILD_VALIDATION = "BuildValidationAgent"
    REPAIR = "RepairAgent"
    REPORT = "ReportAgent"
    ASSISTANT = "AssistantAgent"
    ELIGIBILITY = "EligibilityAgent"


class ValidationStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_CONFIGURED = "not_configured"
    MANUAL_VALIDATION_REQUIRED = "manual_validation_required"
    DEFERRED_COMPANY_TOOL_REQUIRED = "deferred_company_tool_required"
    BLOCKED_BY_ENVIRONMENT = "blocked_by_environment"
    ACCEPTED_RISK = "accepted_risk"
    SKIPPED_NOT_APPLICABLE = "skipped_not_applicable"


class ApprovalDecision(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ACCEPTED_RISK = "ACCEPTED_RISK"
    MODIFICATION_REQUESTED = "MODIFICATION_REQUESTED"
    APPROVED_WITH_RISK = "APPROVED_WITH_RISK"
    CANCELLED = "CANCELLED"


class ApprovalStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFICATION_REQUESTED = "modification_requested"
    APPROVED_WITH_RISK = "approved_with_risk"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class RepairStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    ESCALATED = "escalated"
    CANCELLED = "cancelled"


class AutoApprovalMode(str, Enum):
    OFF = "off"
    ELIGIBLE_GATES = "eligible_gates"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TopologySupportLevel(str, Enum):
    OFFICIALLY_SUPPORTED = "officially_supported"
    HISTORICAL_VALIDATED = "historical_validated"
    HISTORICAL_EXPERIMENTAL = "historical_experimental"
    BLOCKED = "blocked"


class AssuranceStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    CONDITIONAL = "conditional"
    MANUAL_REQUIRED = "manual_required"
    NOT_EVALUATED = "not_evaluated"


class DeliveryStatus(str, Enum):
    NOT_PUBLISHED = "not_published"
    PUBLISHED = "published"
    PUBLISHED_WITH_MANUAL_ITEMS = "published_with_manual_items"
    BLOCKED = "blocked"


class ArtifactType(str, Enum):
    JSON = "json"
    YAML = "yaml"
    MARKDOWN = "markdown"
    TEXT_LOG = "text_log"
    COMMAND_LOG = "command_log"
    PATCH = "patch"
    DIFF = "diff"
    REPORT = "report"


class CommandStatus(str, Enum):
    QUEUED = "queued"
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class CancellationPolicy(str, Enum):
    TERMINATE_PROCESS_TREE = "terminate_process_tree"
    WAIT_FOR_SAFE_POINT = "wait_for_safe_point"


class WorkflowEventType(str, Enum):
    ANALYSIS_INPUT_VALIDATION_STARTED = 'ANALYSIS_INPUT_VALIDATION_STARTED'
    ANALYSIS_INPUT_VALIDATION_COMPLETED = 'ANALYSIS_INPUT_VALIDATION_COMPLETED'
    ANALYSIS_CONTEXT_PREPARED = 'ANALYSIS_CONTEXT_PREPARED'
    LLM_REQUEST_PREPARED = 'LLM_REQUEST_PREPARED'
    LLM_HTTP_REQUEST_STARTED = 'LLM_HTTP_REQUEST_STARTED'
    LLM_HTTP_RESPONSE_RECEIVED = 'LLM_HTTP_RESPONSE_RECEIVED'
    LLM_RESPONSE_DECODED = 'LLM_RESPONSE_DECODED'
    LLM_STRUCTURED_OUTPUT_VALIDATED = 'LLM_STRUCTURED_OUTPUT_VALIDATED'
    LLM_INVOCATION_STARTED = 'LLM_INVOCATION_STARTED'
    LLM_INVOCATION_COMPLETED = 'LLM_INVOCATION_COMPLETED'
    LLM_INVOCATION_FAILED = 'LLM_INVOCATION_FAILED'
    LLM_BUDGET_WARNING = 'LLM_BUDGET_WARNING'
    LLM_BUDGET_BLOCKED = 'LLM_BUDGET_BLOCKED'
    ANALYSIS_AGENT_STARTED = 'ANALYSIS_AGENT_STARTED'
    ANALYSIS_AGENT_COMPLETED = 'ANALYSIS_AGENT_COMPLETED'
    ANALYSIS_AGENT_FAILED = 'ANALYSIS_AGENT_FAILED'
    ANALYSIS_REVIEWER_STARTED = 'ANALYSIS_REVIEWER_STARTED'
    ANALYSIS_REVIEWER_COMPLETED = 'ANALYSIS_REVIEWER_COMPLETED'
    ANALYSIS_REVIEWER_FAILED = 'ANALYSIS_REVIEWER_FAILED'
    G04_CREATED = 'G04_CREATED'
    G04_APPROVED = 'G04_APPROVED'
    G04_MODIFICATION_REQUESTED = 'G04_MODIFICATION_REQUESTED'
    G04_REJECTED = 'G04_REJECTED'
    G04_STALE = 'G04_STALE'
    COMPATIBILITY_RESOLUTION_STARTED = "COMPATIBILITY_RESOLUTION_STARTED"
    COMPATIBILITY_RESOLUTION_COMPLETED = "COMPATIBILITY_RESOLUTION_COMPLETED"
    COMPATIBILITY_RESOLUTION_BLOCKED = "COMPATIBILITY_RESOLUTION_BLOCKED"
    G05_CREATED = "G05_CREATED"
    G05_APPROVED = "G05_APPROVED"
    G05_MODIFICATION_REQUESTED = "G05_MODIFICATION_REQUESTED"
    G05_REJECTED = "G05_REJECTED"
    G05_STALE = "G05_STALE"
    STATE_CONTRACT_MIGRATED = "STATE_CONTRACT_MIGRATED"
    APPROVAL_POLICY_DISABLED_FOR_PRODUCTION = "APPROVAL_POLICY_DISABLED_FOR_PRODUCTION"
    RUN_STATE_CHANGED = "run_state_changed"
    STAGE_STATE_CHANGED = "stage_state_changed"
    STEP_STATE_CHANGED = "step_state_changed"
    COMPONENT_STATE_CHANGED = "component_state_changed"
    AGENT_STATE_CHANGED = "agent_state_changed"
    VALIDATION_GATE_CHANGED = "validation_gate_changed"
    ARTIFACT_CREATED = "artifact_created"
    APPROVAL_REQUIRED = "approval_required"
    WORKFLOW_COMPLETED = "workflow_completed"
    RUN_CREATED = "RUN_CREATED"
    RUN_START_ACCEPTED = "RUN_START_ACCEPTED"
    RUN_STARTED = "RUN_STARTED"
    RUN_START_REJECTED = "RUN_START_REJECTED"
    SOURCE_INTAKE_QUEUED = "SOURCE_INTAKE_QUEUED"
    SOURCE_INTAKE_STARTED = "SOURCE_INTAKE_STARTED"
    SOURCE_INTAKE_COMPLETED = "SOURCE_INTAKE_COMPLETED"
    SOURCE_INTAKE_FAILED = "SOURCE_INTAKE_FAILED"
    RUN_RECONSTRUCTED = "RUN_RECONSTRUCTED"
    SNAPSHOT_STARTED = "SNAPSHOT_STARTED"
    SNAPSHOT_CREATED = "SNAPSHOT_CREATED"
    SNAPSHOT_FAILED = "SNAPSHOT_FAILED"
    SNAPSHOT_PROGRESS_UPDATED = "SNAPSHOT_PROGRESS_UPDATED"
    SNAPSHOT_QUARANTINED = "SNAPSHOT_QUARANTINED"
    SOURCE_INTEGRITY_VERIFIED = "SOURCE_INTEGRITY_VERIFIED"
    SOURCE_INTEGRITY_FAILED = "SOURCE_INTEGRITY_FAILED"
    G02_CREATED = "G02_CREATED"
    G02_APPROVED = "G02_APPROVED"
    G02_REJECTED = "G02_REJECTED"
    G02_STALE = "G02_STALE"
    EXECUTION_PROFILE_RESOLUTION_STARTED = "EXECUTION_PROFILE_RESOLUTION_STARTED"
    EXECUTION_PROFILE_RESOLVED = "EXECUTION_PROFILE_RESOLVED"
    EXECUTION_PROFILE_BLOCKED = "EXECUTION_PROFILE_BLOCKED"
    EXECUTION_PROFILE_SELECTED = "EXECUTION_PROFILE_SELECTED"
    BASELINE_WORKSPACE_STARTED = "BASELINE_WORKSPACE_STARTED"
    BASELINE_WORKSPACE_READY = "BASELINE_WORKSPACE_READY"
    LOCKFILE_PREQUALIFICATION_COMPLETED = "LOCKFILE_PREQUALIFICATION_COMPLETED"
    LIFECYCLE_SCRIPT_REVIEW_REQUIRED = "LIFECYCLE_SCRIPT_REVIEW_REQUIRED"
    BASELINE_INSTALL_AUTHORIZED = "BASELINE_INSTALL_AUTHORIZED"
    BASELINE_INSTALL_BLOCKED = "BASELINE_INSTALL_BLOCKED"
    COMMAND_QUEUED = "COMMAND_QUEUED"
    COMMAND_STARTED = "COMMAND_STARTED"
    COMMAND_OUTPUT_AVAILABLE = "COMMAND_OUTPUT_AVAILABLE"
    COMMAND_OUTPUT_CHUNK = "COMMAND_OUTPUT_CHUNK"
    BASELINE_INSTALL_SUCCEEDED = "BASELINE_INSTALL_SUCCEEDED"
    BASELINE_INSTALL_FAILED = "BASELINE_INSTALL_FAILED"
    COMMAND_CANCELLED = "COMMAND_CANCELLED"
    COMMAND_INTERRUPTED = "COMMAND_INTERRUPTED"
    BASELINE_TARGETS_DISCOVERED = "BASELINE_TARGETS_DISCOVERED"
    BASELINE_BUILD_STARTED = "BASELINE_BUILD_STARTED"
    BASELINE_BUILD_COMPLETED = "BASELINE_BUILD_COMPLETED"
    BASELINE_TESTS_STARTED = "BASELINE_TESTS_STARTED"
    BASELINE_TESTS_COMPLETED = "BASELINE_TESTS_COMPLETED"
    BASELINE_LINT_STARTED = "BASELINE_LINT_STARTED"
    BASELINE_LINT_COMPLETED = "BASELINE_LINT_COMPLETED"
    BASELINE_FAILURES_FINGERPRINTED = "BASELINE_FAILURES_FINGERPRINTED"
    BASELINE_ROUTE_ANCHOR_CREATED = "BASELINE_ROUTE_ANCHOR_CREATED"
    BASELINE_BACKEND_ANCHOR_CREATED = "BASELINE_BACKEND_ANCHOR_CREATED"
    BASELINE_QUALIFIED = "BASELINE_QUALIFIED"
    BASELINE_QUALIFIED_WITH_KNOWN_FAILURES = "BASELINE_QUALIFIED_WITH_KNOWN_FAILURES"
    BASELINE_BLOCKED = "BASELINE_BLOCKED"
    G03_CREATED = "G03_CREATED"
    G03_APPROVED = "G03_APPROVED"
    G03_REJECTED = "G03_REJECTED"
    DISCOVERY_STARTED = "DISCOVERY_STARTED"
    SCANNER_COMPLETED = "SCANNER_COMPLETED"
    DISCOVERY_COMPLETED = "DISCOVERY_COMPLETED"
    DISCOVERY_BLOCKED = "DISCOVERY_BLOCKED"
    PARITY_BASELINE_STARTED = "PARITY_BASELINE_STARTED"
    PARITY_BASELINE_COMPLETED = "PARITY_BASELINE_COMPLETED"
    PARITY_BASELINE_BLOCKED = "PARITY_BASELINE_BLOCKED"
    MIGRATION_PLAN_CREATED = "MIGRATION_PLAN_CREATED"
    STAGE_PLAN_CREATED = "STAGE_PLAN_CREATED"
    PLAN_REVISION_CREATED = "PLAN_REVISION_CREATED"
    APPROVAL_MARKED_STALE = "APPROVAL_MARKED_STALE"
    PLANNING_AGENT_COMPLETED = "PLANNING_AGENT_COMPLETED"
    G06_CREATED = "G06_CREATED"
    G06_APPROVED = "G06_APPROVED"
    G06_MODIFICATION_REQUESTED = "G06_MODIFICATION_REQUESTED"
    G06_REJECTED = "G06_REJECTED"
    G06_STALE = "G06_STALE"
    SPRINT1_BOUNDARY_REACHED = "SPRINT1_BOUNDARY_REACHED"
    COMMAND_AUTHORIZATION_ACCEPTED = "COMMAND_AUTHORIZATION_ACCEPTED"
    COMMAND_AUTHORIZATION_REJECTED = "COMMAND_AUTHORIZATION_REJECTED"
    COMMAND_SUCCEEDED = "COMMAND_SUCCEEDED"
    COMMAND_FAILED = "COMMAND_FAILED"
    RUN_CANCEL_REQUESTED = "RUN_CANCEL_REQUESTED"
    RUN_CANCELLED = "RUN_CANCELLED"


class ErrorEnvelope(ContractModel):
    error_code: str
    message: str
    correlation_id: str
    details: dict[str, Any] = Field(default_factory=dict)


class PreflightRequestDto(ContractModel):
    source_path: str = Field(min_length=1)
    target_output_path: str = Field(min_length=1)
    target_angular_family: str = Field(default="21.x", min_length=1)
    migration_mode: str = Field(default="strict-functional-parity", min_length=1)
    auto_approval_enabled: bool = False


class PreflightResultDto(ContractModel):
    preflight_id: str
    checksum: str
    expires_at: datetime
    source_path: str
    target_output_path: str
    status: str
    message: str
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    capabilities: dict[str, str] = Field(default_factory=dict)
    runtime_profile_available: bool = True
    registry_access: str = "placeholder_not_checked"
    topology_status: str = "placeholder_not_scanned"
    angular_eligibility: str = "placeholder_not_scanned"
    artifact: dict[str, Any] | None = None


class CreateMockMigrationRequestDto(ContractModel):
    preflight_checksum: str = Field(min_length=1)
    idempotency_key: str | None = None


class OperationResultDto(ContractModel):
    run_id: str
    operation: str
    status: str
    idempotent: bool = True
    message: str


class ApprovalRequestDto(ContractModel):
    gate_id: str = Field(min_length=1)
    decision: ApprovalDecision
    actor: str | None = None
    rationale: str | None = None
    idempotency_key: str | None = None


class ApprovalPolicyRequestDto(ContractModel):
    auto_approval_enabled: bool
    actor: str | None = None
    reason: str | None = None


class ApprovalPolicyDto(ContractModel):
    run_id: str
    auto_approval_enabled: bool
    reevaluated_gate_id: str | None = None
    status: str


class AssistantMessageRequestDto(ContractModel):
    run_id: str | None = None
    message: str = Field(min_length=1)


class AssistantMessageResponseDto(ContractModel):
    run_id: str | None = None
    response: str
    status: str


class MigrationStageDto(ContractModel):
    stage_id: str
    run_id: str
    stage_order: int = Field(ge=1)
    source_version_family: str | None = None
    target_version_family: str | None = None
    source_version_detected: str | None = None
    target_version_resolved: str | None = None
    source_angular_version: str | None = None
    target_angular_version: str | None = None
    status: StageStatus
    current_agent: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class StageStepDto(ContractModel):
    step_id: str
    run_id: str
    stage_id: str | None = None
    name: str
    status: StepStatus
    component_type: str
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ComponentExecutionDto(ContractModel):
    execution_id: str
    run_id: str
    stage_id: str | None = None
    component_name: str
    component_type: DeterministicComponentType
    status: StepStatus
    started_at: datetime
    finished_at: datetime | None = None
    summary: str | None = None


class AgentExecutionDto(ContractModel):
    execution_id: str
    run_id: str
    stage_id: str | None = None
    agent_name: str
    agent_kind: AgentKind | None = None
    status: AgentStatus
    started_at: datetime
    finished_at: datetime | None = None
    summary: str | None = None


class ValidationGateDto(ContractModel):
    gate_id: str
    run_id: str
    stage_id: str | None = None
    name: str
    status: ValidationStatus
    checked_at: datetime
    details: str | None = None


class ApprovalEventDto(ContractModel):
    approval_id: str
    run_id: str
    stage_id: str | None = None
    decision: ApprovalDecision
    requested_at: datetime
    decided_at: datetime | None = None
    actor: str | None = None
    rationale: str | None = None


class ArtifactRefDto(ContractModel):
    artifact_id: str
    run_id: str
    stage_id: str | None = None
    artifact_type: ArtifactType
    relative_path: str
    created_at: datetime
    checksum: str
    immutable: bool = True
    redacted: bool = False
    truncated: bool = False


class RuntimeProfileDto(ContractModel):
    runtime_profile_id: str
    node_version: str | None = None
    npm_version: str | None = None
    angular_cli_version: str | None = None
    checksum: str


class CommandRequestDto(ContractModel):
    command_id: str
    run_id: str
    stage_id: str | None = None
    requested_by: str | None = None
    requester: str | None = None
    executable: str
    arguments: list[str] = Field(default_factory=list)
    shell: bool = False
    working_directory_alias: str | None = None
    working_directory: str | None = None
    runtime_profile_id: str = "source-runtime-profile"
    timeout_seconds: int = Field(default=30, gt=0)
    network_profile: str = "none"
    cancellation_policy: CancellationPolicy = CancellationPolicy.TERMINATE_PROCESS_TREE
    idempotency_key: str | None = None
    requested_at: datetime


class CommandResultDto(ContractModel):
    command_id: str
    run_id: str
    stage_id: str | None = None
    status: CommandStatus
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    exit_code: int | None = None
    stdout_artifact: ArtifactRefDto | None = None
    stderr_artifact: ArtifactRefDto | None = None


class CommandTemplateDto(ContractModel):
    """One registered command template in the structured registry."""
    template_id: str
    command_id: str
    executable: str
    arguments: list[str] = Field(default_factory=list)
    executable_aliases: list[str] = Field(default_factory=list)
    description: str = ""
    status: str = "active"
    version: int = 1
    allowed_env_vars: list[str] = Field(default_factory=list)
    max_output_bytes: int | None = 1_000_000
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CommandTemplateListDto(ContractModel):
    """Response wrapper for GET /api/v1/operator/command-templates."""
    templates: list[CommandTemplateDto] = Field(default_factory=list)
    total: int = 0


class CommandPolicyValidateRequestDto(ContractModel):
    """Request body for POST /api/v1/operator/command-policy/validate."""
    run_id: str = Field(min_length=1)
    expected_state_version: int = Field(default=1, ge=1)
    stage_id: str | None = None
    command_id: str = Field(min_length=1)
    template_id: str | None = None
    template_version: int | None = Field(default=None, ge=1)
    executable: str = Field(min_length=1)
    arguments: list[str] = Field(default_factory=list)
    cwd_alias: str | None = None
    plan_id: str | None = None
    plan_version: int | None = Field(default=None, ge=1)
    working_directory_alias: str | None = None
    working_directory: str | None = None
    execution_profile_id: str = "source-runtime-profile"
    network_profile: str = "none"
    cancellation_policy: str = "terminate_process_tree"
    timeout_seconds: int = Field(default=300, gt=0, le=3600)
    idempotency_key: str = Field(min_length=1, max_length=128)
    requested_by: str | None = None
    correlation_id: str | None = Field(default=None, min_length=1, max_length=128)
    shell: bool = False


class CommandPolicyValidateResponseDto(ContractModel):
    """Response body for POST /api/v1/operator/command-policy/validate."""
    authorization_id: str
    run_id: str
    stage_id: str | None = None
    plan_id: str | None = None
    command_id: str
    executable: str
    arguments: list[str] = Field(default_factory=list)
    cwd_alias: str | None = None
    execution_profile_id: str = "source-runtime-profile"
    decision: str
    reasons: list[str] = Field(default_factory=list)
    policy_version: str = "s3-f01-v1"
    idempotent_replay: bool = False
    expected_state_version: int = 1
    authoritative_state_version: int = 1
    artifact_id: str | None = None
    correlation_id: str | None = None
    request_payload_hash: str | None = None
    idempotency_key: str | None = None
    decision_timestamp: datetime | None = None


class CommandExecuteRequestDto(ContractModel):
    """Request body for POST /api/v1/runs/{run_id}/commands."""
    authorization_decision_id: str = Field(min_length=1)
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    requested_by: str | None = None


class CommandExecutionResponseDto(ContractModel):
    """Response body for command execution endpoints."""
    execution_id: str
    run_id: str
    command_id: str
    status: str
    state_version: int = 1
    event_sequence: int = 1
    idempotent_replay: bool = False
    stage_id: str | None = None
    authorization_id: str | None = None
    template_id: str | None = None
    template_version: int | None = None
    plan_id: str | None = None
    plan_version: int | None = None
    execution_profile_id: str | None = None
    workspace_alias: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    exit_code: int | None = None
    failure_code: str | None = None
    correlation_id: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    stdout_artifact_id: str | None = None
    stderr_artifact_id: str | None = None
    command_log_artifact_id: str | None = None
    manifest_artifact_id: str | None = None
    result_artifact_id: str | None = None
    executable: str | None = None
    arguments: list[str] = Field(default_factory=list)
    safe_relative_working_directory: str | None = None
    runtime_checksum: str | None = None
    worker_id: str | None = None
    failure_reason: str | None = None
    request_payload_hash: str | None = None
    cancel_requested_at: datetime | None = None
    cancel_requested_by: str | None = None
    cancelled: bool = False
    timed_out: bool = False


class CancelCommandRequestDto(ContractModel):
    """Request body for POST /api/v1/runs/{run_id}/commands/{execution_id}/cancel."""
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)


class LogChunkResponseDto(ContractModel):
    """One log chunk in a response."""
    sequence: int
    stream: str
    text: str
    redacted: bool = False
    truncated: bool = False
    created_at: str = ""
    byte_count: int = 0
    character_count: int = 0


class WorkerLeaseDto(ContractModel):
    lease_id: str
    run_id: str
    execution_id: str | None = None
    worker_id: str
    backend_instance_id: str | None = None
    acquired_at: datetime
    heartbeat_at: datetime | None = None
    expires_at: datetime


class PatchLedgerEntryDto(ContractModel):
    patch_id: str
    run_id: str
    stage_id: str
    affected_files: list[str] = Field(min_length=1)
    change_summary: str
    risk_level: RiskLevel
    created_at: datetime
    validation_status: ValidationStatus


class RepairAttemptDto(ContractModel):
    repair_attempt_id: str
    run_id: str
    stage_id: str
    attempt_number: int = Field(ge=1)
    status: AgentStatus
    risk_level: RiskLevel
    created_at: datetime
    diagnosis: str | None = None


class AssuranceStatusDto(ContractModel):
    technical_upgrade_status: AssuranceStatus
    functional_parity_status: AssuranceStatus
    security_assurance_status: AssuranceStatus
    quality_assurance_status: AssuranceStatus
    delivery_readiness: AssuranceStatus


class DeliveryManifestDto(ContractModel):
    run_id: str
    status: DeliveryStatus
    delivery_path: str | None = None
    manifest_checksum: str | None = None
    published_at: datetime | None = None


class TopologySummaryDto(ContractModel):
    package_manager: str
    source_family: str
    target_family: str
    support_level: TopologySupportLevel


class LlmUsageRecordDto(ContractModel):
    usage_id: str
    run_id: str
    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    input_price_per_million: float = Field(ge=0)
    output_price_per_million: float = Field(ge=0)
    cost_usd: float = Field(ge=0)
    created_at: datetime


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(str, Enum):
    WORKER_LOSS = "worker_loss"
    STUCK_STATE = "stuck_state"
    SOURCE_INTEGRITY_FAILURE = "source_integrity_failure"
    DISK_THRESHOLD = "disk_threshold"
    REPEATED_TIMEOUT = "repeated_timeout"
    STATE_ARTIFACT_INCONSISTENCY = "state_artifact_inconsistency"
    SQLITE_CONTENTION = "sqlite_contention"


class RunMetricDto(ContractModel):
    metric_name: str
    run_id: str
    stage_id: str | None = None
    value: float = Field(ge=0)
    unit: str
    labels: dict[str, str] = Field(default_factory=dict)


class AlertEventDto(ContractModel):
    alert_id: str
    run_id: str
    alert_type: AlertType
    severity: AlertSeverity
    message: str
    created_at: datetime
    stage_id: str | None = None
    correlation_id: str | None = None


class DiagnosticsSummaryDto(ContractModel):
    run_id: str
    stage_id: str | None = None
    generated_at: datetime
    metrics: list[RunMetricDto] = Field(default_factory=list)
    alerts: list[AlertEventDto] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class WorkflowEventDto(ContractModel):
    event_id: str
    run_id: str
    stage_id: str | None = None
    event_type: str
    occurred_at: datetime
    sequence: int = Field(default=1, ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class MigrationEventDto(ContractModel):
    event_id: str
    run_id: str
    stage_id: str | None = None
    event_type: WorkflowEventType
    occurred_at: datetime
    sequence: int = Field(default=1, ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class MigrationRunDto(ContractModel):
    run_id: str
    status: RunStatus
    run_phase: RunPhase = RunPhase.FEASIBILITY_PLANNING
    phase_status: PhaseStatus = PhaseStatus.RUNNING
    approval_status: ApprovalStatus = ApprovalStatus.NOT_REQUIRED
    repair_status: RepairStatus = RepairStatus.NOT_REQUIRED
    source_version_family: str | None = None
    target_version_family: str | None = None
    source_version_detected: str | None = None
    target_version_resolved: str | None = None
    source_angular_version: str | None = None
    target_angular_version: str | None = None
    created_at: datetime
    updated_at: datetime
    source_angular_exact: str | None = None
    catalogue_version: str | None = None
    registry_snapshot: dict[str, Any] | None = None
    runtime_candidates: list[dict[str, Any]] = Field(default_factory=list)
    stages: list[MigrationStageDto] = Field(min_length=1)
    steps: list[StageStepDto] = Field(default_factory=list)
    component_executions: list[ComponentExecutionDto] = Field(default_factory=list)
    agent_executions: list[AgentExecutionDto] = Field(default_factory=list)
    validation_gates: list[ValidationGateDto] = Field(default_factory=list)
    approval_events: list[ApprovalEventDto] = Field(default_factory=list)
    artifacts: list[ArtifactRefDto] = Field(default_factory=list)
    command_requests: list[CommandRequestDto] = Field(default_factory=list)
    command_results: list[CommandResultDto] = Field(default_factory=list)
    worker_leases: list[WorkerLeaseDto] = Field(default_factory=list)
    patch_ledger: list[PatchLedgerEntryDto] = Field(default_factory=list)
    repair_attempts: list[RepairAttemptDto] = Field(default_factory=list)
    assurance: AssuranceStatusDto | None = None
    delivery: DeliveryManifestDto | None = None
    topology: TopologySummaryDto | None = None
    llm_usage: list[LlmUsageRecordDto] = Field(default_factory=list)
    diagnostics: DiagnosticsSummaryDto | None = None
    workflow_events: list[WorkflowEventDto] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_incompatible_terminal_state(self) -> "MigrationRunDto":
        if self.status in {RunStatus.COMPLETED, RunStatus.CANCELLED, RunStatus.FAILED}:
            active = {StageStatus.RUNNING, StageStatus.WAITING_APPROVAL, StageStatus.REPAIRING}
            if any(stage.status in active for stage in self.stages):
                raise ValueError("terminal runs cannot contain active stages")
        return self


class CreateAuthoritativeRunRequestDto(ContractModel):
    preflight_id: str = Field(min_length=1)
    input_checksum: str = Field(min_length=1)
    artifact_set_checksum: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    client_constraints: dict[str, bool] = Field(default_factory=dict)
    pricing_snapshot: dict[str, str | float | int] = Field(default_factory=dict)


class StartAuthoritativeRunRequestDto(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)


class CancelAuthoritativeRunRequestDto(ContractModel):
    """Operator-confirmed cancellation of an authoritative run."""

    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)


class AuthoritativeRunStateDto(ContractModel):
    run_id: str
    status: RunStatus
    run_phase: RunPhase
    phase_status: str
    approval_status: ApprovalStatus
    repair_status: RepairStatus
    state_version: int = Field(ge=1)
    preflight_id: str | None = None
    source_path: str | None = None
    target_output_path: str | None = None
    graph_thread_id: str | None = None
    created_at: datetime
    updated_at: datetime
    workspace_aliases: dict[str, str] = Field(default_factory=dict)
    target_parent_path: str | None = None
    generated_output_name: str | None = None
    resolved_output_root: str | None = None
    run_root: str | None = None
    migrated_app_path: str | None = None
    source_angular_exact: str | None = None
    catalogue_version: str | None = None
    registry_snapshot: dict[str, object] | None = None
    runtime_candidates: list[dict[str, object]] = Field(default_factory=list)
    plan_inputs: dict[str, object] | None = None
    artifacts: list[ArtifactRefDto] = Field(default_factory=list)
    workflow_events: list[WorkflowEventDto] = Field(default_factory=list)


class AuthoritativeRunMutationResultDto(ContractModel):
    run_id: str
    job_id: str | None = None
    status: RunStatus
    state_version: int = Field(ge=1)
    event_sequence: int = Field(ge=1)
    graph_thread_id: str
    idempotent_replay: bool = False
    artifacts: list[ArtifactRefDto] = Field(default_factory=list)


# Deterministic component and AI-agent contracts (AMF-S0-10)


class ComponentInputEnvelope(ContractModel):
    run_id: str
    stage_id: str | None = None
    component_type: DeterministicComponentType
    input_artifact_refs: list[str] = Field(default_factory=list)
    policy_version: str = "migration-policy-v1"
    state_version: int = Field(default=1, ge=1)


class ComponentOutputEnvelope(ContractModel):
    run_id: str
    stage_id: str | None = None
    component_type: DeterministicComponentType
    status: StepStatus
    summary: str
    output_artifact_refs: list[str] = Field(default_factory=list)
    recommended_next_step: str | None = None


class DeterministicComponentContract(ContractModel):
    component_type: DeterministicComponentType
    responsibility: str
    allowed_inputs: list[str] = Field(default_factory=list)
    allowed_outputs: list[str] = Field(default_factory=list)
    may_call_llm: bool = False
    may_execute_commands_directly: bool = False

    @model_validator(mode="after")
    def enforce_deterministic_boundary(self) -> "DeterministicComponentContract":
        if self.may_call_llm:
            raise ValueError("deterministic components cannot call LLMs")
        if self.may_execute_commands_directly:
            raise ValueError("deterministic components cannot execute commands directly")
        return self


class AllowedAction(str, Enum):
    READ_FILE = "read_file"
    RUN_APPROVED_COMMAND = "run_approved_command"
    REQUEST_APPROVAL = "request_approval"
    READ_ARTIFACT_SUMMARY = "read_artifact_summary"
    CREATE_ARTIFACT = "create_artifact"
    PROPOSE_PATCH = "propose_patch"


class ClientConstraints(ContractModel):
    preserve_ui: bool = True
    preserve_behavior: bool = True
    preserve_business_logic: bool = True
    preserve_api_contracts: bool = True
    preserve_authentication_authorization: bool = True
    allow_optional_modernization: bool = False


class WorkspaceRef(ContractModel):
    sandbox_path: str
    sandbox_branch: str


class ArtifactLocations(ContractModel):
    analysis: str | None = None
    planning: str | None = None
    validation: str | None = None
    transform: str | None = None
    repair: str | None = None
    final: str | None = None


class RiskEntry(ContractModel):
    risk_id: str
    severity: RiskLevel
    description: str


class UntrustedContextRef(ContractModel):
    context_id: str
    source: str
    artifact_ref: str | None = None
    reason: str = "repository content, comments, or logs are untrusted data"


class ActionProposalDto(ContractModel):
    proposal_id: str
    action_type: AllowedAction
    rationale: str
    registered_action_id: str | None = None
    requires_backend_authorization: bool = True
    authorizes_execution: bool = False
    authorizes_approval: bool = False

    @model_validator(mode="after")
    def enforce_proposal_boundary(self) -> "ActionProposalDto":
        if self.action_type == AllowedAction.RUN_APPROVED_COMMAND and not self.registered_action_id:
            raise ValueError("command proposals must reference a registered action id")
        if self.authorizes_execution or self.authorizes_approval:
            raise ValueError("agent proposals cannot authorize execution or approval")
        return self


class PatchProposalDto(ContractModel):
    proposal_id: str
    files: list[str] = Field(min_length=1)
    rationale: str
    risk_level: RiskLevel
    expected_behavior_impact: str
    validation_requests: list[str] = Field(min_length=1)
    authorizes_application: bool = False

    @model_validator(mode="after")
    def enforce_patch_boundary(self) -> "PatchProposalDto":
        if self.authorizes_application:
            raise ValueError("patch proposals cannot authorize application")
        return self


class AgentInputEnvelope(ContractModel):
    run_id: str
    stage_id: str | None = None
    agent_kind: AgentKind | None = None
    workspace: WorkspaceRef | None = None
    client_constraints: ClientConstraints = Field(default_factory=ClientConstraints)
    current_workflow_state: RunStatus
    allowed_actions: list[AllowedAction] = Field(default_factory=list)
    artifact_locations: ArtifactLocations = Field(default_factory=ArtifactLocations)
    approved_plan_checksum: str | None = None
    untrusted_context: list[UntrustedContextRef] = Field(default_factory=list)


class AgentOutputEnvelope(ContractModel):
    agent_name: str
    agent_kind: AgentKind | None = None
    run_id: str
    stage_id: str | None = None
    status: AgentStatus
    summary: str
    artifacts_created: list[str] = Field(default_factory=list)
    risks: list[RiskEntry] = Field(default_factory=list)
    action_proposals: list[ActionProposalDto] = Field(default_factory=list)
    patch_proposals: list[PatchProposalDto] = Field(default_factory=list)
    requires_human_action: bool = False
    authorizes_execution: bool = False
    authorizes_approval: bool = False
    next_recommended_state: RunStatus

    @model_validator(mode="after")
    def enforce_agent_authority_boundary(self) -> "AgentOutputEnvelope":
        if self.authorizes_execution or self.authorizes_approval:
            raise ValueError("AI output cannot authorize execution or approval")
        return self
