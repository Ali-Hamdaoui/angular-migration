"""Closed Transformer workflow contracts."""

from datetime import datetime
from enum import Enum
import re

from pydantic import Field, field_validator

from app.domain.contracts import ContractModel

# Rejects only unsafe path disclosure or input. Repository-relative filenames
# and paths (package.json, angular.json, src/app/app.ts) that describe intended
# changes are allowed. Tokens are whitespace-delimited and trailing prose
# punctuation is stripped before matching.
_UNSAFE_PATH_TOKEN = re.compile(
    r"(?:"
    r"^[\\/]{2}"                                      # UNC / network share
    r"|^/[^/]"                                        # absolute POSIX path
    r"|^[A-Za-z]:[\\/]"                               # Windows drive path
    r"|^file://"                                      # file URL
    r"|(?:^|[/\\])\.\.(?=[\\/]|$)"                    # parent traversal
    r"|(?:^|[/\\])(?:baseline-sandbox|stage-sandboxes|repair-sandboxes"
    r"|final-assurance-sandbox|migrated-app|source-snapshot"
    r"|delivery-candidate|\.migration-factory|04_workflow_state|05_repairs)"
    r"(?:$|[/\\])"                                    # platform sandbox/runtime paths
    r")",
    re.IGNORECASE,
)


class TransformationStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_COMMAND = "waiting_command"
    WAITING_GATE = "waiting_gate"
    WAITING_PROMPT = "waiting_prompt"
    WAITING_RETRY = "waiting_retry"
    WAITING_REPAIR_REVISION = "waiting_repair_revision"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    FAILED = "failed"
    COMPLETED = "completed"


class TransformationNode(str, Enum):
    STAGE_WORKSPACE_READY = "stage_workspace_ready"
    BASELINE_INSTALL = "baseline_install"
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
    APPROVED_PENDING_EXECUTION = "approved_pending_execution"
    APPLY_REPAIR = "apply_repair"
    VERIFY_REPAIR = "verify_repair"
    RETRY_MIGRATION = "retry_migration"
    DEPENDENCY_TRANSITION = "dependency_transition"
    ANGULAR_UPDATE_RETRY = "angular_update_retry"
    MIGRATE_PACKAGES = "migrate_packages"
    REPAIR_REVALIDATE = "repair_revalidate"
    CREATE_G11 = "create_g11"
    WAIT_G11 = "wait_g11"
    CREATE_G12 = "create_g12"
    WAIT_G12 = "wait_g12"
    SEAL_STAGE = "seal_stage"
    MATERIALIZE_NEXT_STAGE = "materialize_next_stage"
    COMPLETE_RUN = "complete_run"
    STAGE_COMPLETED = "stage_completed"
    BLOCKED = "blocked"
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
    ANGULAR_UPDATE_COMMAND_POLICY = "angular_update_command_policy"
    ANGULAR_UPDATE_PEER_CONFLICT = "angular_update_peer_conflict"
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
    repair_attempt_id: str | None = None
    repair_attempt_number: int | None = None
    repair_parent_attempt_id: str | None = None
    repair_status: str | None = None
    repair_risk_level: str | None = None
    repair_proposal_checksum: str | None = None
    repair_review_checksum: str | None = None
    repair_diff_artifact_id: str | None = None
    repair_diff_checksum: str | None = None
    repair_proposal_operations: list[dict[str, str]] = Field(default_factory=list)
    repair_safe_diff: str | None = None
    repair_review: dict[str, object] | None = None
    repair_rationale: list[str] = Field(default_factory=list)
    repair_apply_checksum: str | None = None
    repair_validation_checksum: str | None = None
    next_backend_action: str | None = None
    angular_update_retry_attempt: int | None = None
    angular_update_retry_status: str | None = None
    workflow_step: str
    active_command_phase: str | None = None
    stage_start_fingerprint: str | None = None
    repair_contract: dict[str, object] | None = None
    dependency_operation: dict[str, object] | None = None
    completed_transition_phases: list[dict[str, object]] = Field(default_factory=list)
    repair_verification: dict[str, object] | None = None
    dependency_closure: dict[str, object] | None = None
    dependency_normalization: dict[str, object] | None = None
    validation_results: dict[str, object] = Field(default_factory=dict)
    active_error: dict[str, str] | None = None
    historical_diagnostics: list[dict[str, object]] = Field(default_factory=list)


class TransformationCancelRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=128)


class TransformationRestartRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=128)


class RepairInvocationRecoveryRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=2000)
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


class RepairDecisionRequest(ContractModel):
    attempt_id: str = Field(min_length=1, max_length=64)
    proposal_id: str = Field(min_length=1, max_length=128)
    base_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=128)


class RepairRevisionRequest(RepairDecisionRequest):
    instruction: str = Field(min_length=1, max_length=4000)

    @field_validator("instruction")
    @classmethod
    def plain_text_only(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("instruction must not be blank")
        if re.search(r"(?m)^\s*(?:diff --git|--- |\+\+\+ |@@ )", value) or re.search(
            r"(?m)^-[^-].*\n\+[^+]", value
        ):
            raise ValueError("raw patches are forbidden")
        tokens = (
            token.lstrip(" \t\r\n\"'`([{").rstrip(" \t\r\n\"'`)]}.,;:!?")
            for token in re.split(r"\s+", value)
        )
        if any(_UNSAFE_PATH_TOKEN.search(token) for token in tokens if token):
            raise ValueError("filesystem paths are forbidden")
        return value


class LegacyRepairOverrideRecoveryRequest(RepairRevisionRequest):
    expected_state_version: int = Field(ge=1)
    correlation_id: str = Field(min_length=1, max_length=128)
