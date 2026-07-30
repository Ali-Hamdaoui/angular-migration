"""Closed Transformer workflow contracts."""

from datetime import datetime
from enum import Enum

from pydantic import Field

from app.domain.contracts import ContractModel


class TransformationStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_COMMAND = "waiting_command"
    WAITING_GATE = "waiting_gate"
    WAITING_PROMPT = "waiting_prompt"
    WAITING_RETRY = "waiting_retry"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    FAILED = "failed"
    COMPLETED = "completed"


class TransformationNode(str, Enum):
    VALIDATE_G06 = "validate_g06"
    PREPARE_WORKSPACE = "prepare_workspace"
    RESOLVE_RUNTIME = "resolve_runtime"
    DEPENDENCY_PREFLIGHT = "dependency_preflight"
    COLLECT_KNOWN_DECISIONS = "collect_known_decisions"
    CREATE_G07 = "create_g07"
    WAIT_G07 = "wait_g07"
    BOOTSTRAP_INSTALL = "bootstrap_install"
    VERIFY_BOOTSTRAP = "verify_bootstrap"
    ANGULAR_UPDATE = "angular_update"
    HANDLE_PROMPT = "handle_prompt"
    WAIT_PROMPT_DECISION = "wait_prompt_decision"
    TARGET_INSPECTION = "target_inspection"
    VERSION_VERIFY = "version_verify"
    TRANSFORMATION_EVIDENCE = "transformation_evidence"
    CREATE_G08 = "create_g08"
    WAIT_G08 = "wait_g08"
    FINAL_INSTALL = "final_install"
    BUILD = "build"
    TEST = "test"
    AGGREGATE_VALIDATION = "aggregate_validation"
    CREATE_G09 = "create_g09"
    WAIT_G09 = "wait_g09"
    CLASSIFY_FAILURE = "classify_failure"
    PROPOSE_REPAIR = "propose_repair"
    REVIEW_REPAIR = "review_repair"
    CREATE_G10 = "create_g10"
    WAIT_G10 = "wait_g10"
    APPLY_REPAIR = "apply_repair"
    REPAIR_REVALIDATE = "repair_revalidate"
    CREATE_G11 = "create_g11"
    WAIT_G11 = "wait_g11"
    CREATE_G12 = "create_g12"
    WAIT_G12 = "wait_g12"
    SEAL_STAGE = "seal_stage"
    MATERIALIZE_NEXT_STAGE = "materialize_next_stage"
    COMPLETE_RUN = "complete_run"
    CANCEL = "cancel"
    TERMINAL = "terminal"


class StageGateId(str, Enum):
    G07 = "G07"
    G08 = "G08"
    G09 = "G09"
    G10 = "G10"
    G11 = "G11"
    G12 = "G12"


class FailureRoute(str, Enum):
    ENVIRONMENT_TRANSIENT = "environment_transient"
    ENVIRONMENT_PERMANENT = "environment_permanent"
    DEPENDENCY_INCOMPATIBLE = "dependency_incompatible"
    UNEXPECTED_PROMPT = "unexpected_prompt"
    POLICY_VIOLATION = "policy_violation"
    REPAIRABLE_SOURCE = "repairable_source"
    NON_REPAIRABLE_VALIDATION = "non_repairable_validation"
    NO_PROGRESS = "no_progress"


class TransformationProjection(ContractModel):
    run_id: str
    continuation_id: str
    stage_id: str
    status: TransformationStatus
    current_node: TransformationNode
    state_version: int = Field(ge=1)
    stage_status: str
    source_version: str | None = None
    target_version: str | None = None
    checkpoint_kind: str | None = None
    workspace_fingerprint: str | None = None
    active_gate: StageGateId | None = None
    active_command_id: str | None = None
    active_command_status: str | None = None
    active_prompt_id: str | None = None
    last_error_code: str | None = None
    cancel_requested_at: datetime | None = None


class TransformationCancelRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=128)


class StageGateDecisionRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    package_checksum: str = Field(min_length=1)
    workspace_fingerprint: str = Field(min_length=1)
    decision: str = Field(pattern="^(approve|reject|request_modification|cancel)$")
    comment: str | None = None
    correlation_id: str = Field(min_length=1, max_length=128)


class PromptDecisionRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    prompt_checksum: str = Field(min_length=1)
    selected_option_id: str = Field(min_length=1)
    comment: str | None = None
    correlation_id: str = Field(min_length=1, max_length=128)
