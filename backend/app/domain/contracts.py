"""Shared API contracts for the Migration Factory backend and Control Tower."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    """Base behavior for public, immutable API contract models."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class RunStatus(str, Enum):
    CREATED = "CREATED"
    CLIENT_CONSTRAINTS_CAPTURED = "CLIENT_CONSTRAINTS_CAPTURED"
    ELIGIBILITY_RUNNING = "ELIGIBILITY_RUNNING"
    ELIGIBILITY_FAILED = "ELIGIBILITY_FAILED"
    BASELINE_RUNNING = "BASELINE_RUNNING"
    BASELINE_COMPLETED = "BASELINE_COMPLETED"
    ANALYSIS_RUNNING = "ANALYSIS_RUNNING"
    ANALYSIS_COMPLETED = "ANALYSIS_COMPLETED"
    WAITING_ANALYSIS_APPROVAL = "WAITING_ANALYSIS_APPROVAL"
    PLANNING_RUNNING = "PLANNING_RUNNING"
    PLANNING_COMPLETED = "PLANNING_COMPLETED"
    WAITING_PLAN_APPROVAL = "WAITING_PLAN_APPROVAL"
    STAGE_RUNNING = "STAGE_RUNNING"
    TRANSFORMATION_RUNNING = "TRANSFORMATION_RUNNING"
    BUILD_RUNNING = "BUILD_RUNNING"
    BUILD_FAILED = "BUILD_FAILED"
    REPAIR_RUNNING = "REPAIR_RUNNING"
    REPAIR_COMPLETED = "REPAIR_COMPLETED"
    REPAIR_FAILED = "REPAIR_FAILED"
    WAITING_REPAIR_APPROVAL = "WAITING_REPAIR_APPROVAL"
    VALIDATION_RUNNING = "VALIDATION_RUNNING"
    REPORT_RUNNING = "REPORT_RUNNING"
    DIAGNOSTIC_HOLD = "DIAGNOSTIC_HOLD"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_MANUAL_ITEMS = "COMPLETED_WITH_MANUAL_ITEMS"
    COMPLETED_WITH_ACCEPTED_RISK = "COMPLETED_WITH_ACCEPTED_RISK"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StageStatus(str, Enum):
    STAGE_CREATED = "STAGE_CREATED"
    TOOLCHAIN_PROFILE_SELECTED = "TOOLCHAIN_PROFILE_SELECTED"
    SANDBOX_READY = "SANDBOX_READY"
    DEPENDENCY_AUDITED = "DEPENDENCY_AUDITED"
    MCP_CONTEXT_POLICY_RESOLVED = "MCP_CONTEXT_POLICY_RESOLVED"
    STAGE_RUNNING = "STAGE_RUNNING"
    TRANSFORMATION_RUNNING = "TRANSFORMATION_RUNNING"
    STATIC_SYMBOL_CHECK_RUNNING = "STATIC_SYMBOL_CHECK_RUNNING"
    VALIDATION_RUNNING = "VALIDATION_RUNNING"
    VALIDATION_PASSED = "VALIDATION_PASSED"
    REVIEW_READY = "REVIEW_READY"
    STAGE_COMMITTED = "STAGE_COMMITTED"
    STAGE_ROLLED_BACK = "STAGE_ROLLED_BACK"
    DIAGNOSTIC_HOLD = "DIAGNOSTIC_HOLD"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AgentStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"


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
    CANCELLED = "CANCELLED"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


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
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


class WorkflowEventType(str, Enum):
    RUN_STATE_CHANGED = "run_state_changed"
    STAGE_STATE_CHANGED = "stage_state_changed"
    AGENT_STATE_CHANGED = "agent_state_changed"
    VALIDATION_GATE_CHANGED = "validation_gate_changed"
    ARTIFACT_CREATED = "artifact_created"
    APPROVAL_REQUIRED = "approval_required"
    WORKFLOW_COMPLETED = "workflow_completed"



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
    source_angular_version: str
    target_angular_version: str
    status: StageStatus
    current_agent: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class AgentExecutionDto(ContractModel):
    execution_id: str
    run_id: str
    stage_id: str | None = None
    agent_name: str
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
    checksum: str | None = None


class CommandRequestDto(ContractModel):
    command_id: str
    run_id: str
    stage_id: str | None = None
    requester: str
    executable: str
    arguments: list[str] = Field(default_factory=list)
    working_directory: str
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


class WorkflowEventDto(ContractModel):
    event_id: str
    run_id: str
    stage_id: str | None = None
    event_type: str
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class MigrationEventDto(ContractModel):
    event_id: str
    run_id: str
    stage_id: str | None = None
    event_type: WorkflowEventType
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class MigrationRunDto(ContractModel):
    run_id: str
    status: RunStatus
    source_angular_version: str
    target_angular_version: str
    created_at: datetime
    updated_at: datetime
    stages: list[MigrationStageDto] = Field(min_length=1)
    agent_executions: list[AgentExecutionDto] = Field(default_factory=list)
    validation_gates: list[ValidationGateDto] = Field(default_factory=list)
    approval_events: list[ApprovalEventDto] = Field(default_factory=list)
    artifacts: list[ArtifactRefDto] = Field(default_factory=list)
    command_requests: list[CommandRequestDto] = Field(default_factory=list)
    command_results: list[CommandResultDto] = Field(default_factory=list)
    patch_ledger: list[PatchLedgerEntryDto] = Field(default_factory=list)
    repair_attempts: list[RepairAttemptDto] = Field(default_factory=list)
    workflow_events: list[WorkflowEventDto] = Field(default_factory=list)


# ── Common agent contract (AMF-S0-10) ──────────────────────────────


class AllowedAction(str, Enum):
    READ_FILE = "read_file"
    RUN_APPROVED_COMMAND = "run_approved_command"
    REQUEST_APPROVAL = "request_approval"
    READ_ARTIFACT_SUMMARY = "read_artifact_summary"
    CREATE_ARTIFACT = "create_artifact"


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


class AgentInputEnvelope(ContractModel):
    run_id: str
    stage_id: str | None = None
    workspace: WorkspaceRef | None = None
    client_constraints: ClientConstraints = Field(default_factory=ClientConstraints)
    current_workflow_state: RunStatus
    allowed_actions: list[AllowedAction] = Field(default_factory=list)
    artifact_locations: ArtifactLocations = Field(default_factory=ArtifactLocations)
    approved_plan_checksum: str | None = None


class AgentOutputEnvelope(ContractModel):
    agent_name: str
    run_id: str
    stage_id: str | None = None
    status: AgentStatus
    summary: str
    artifacts_created: list[str] = Field(default_factory=list)
    risks: list[RiskEntry] = Field(default_factory=list)
    requires_human_action: bool = False
    next_recommended_state: RunStatus
