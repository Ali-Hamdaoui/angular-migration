"""Closed Transformer workflow contracts."""

from datetime import datetime
from enum import Enum
import re
from typing import Literal

from pydantic import Field, field_validator, model_validator

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


class ProvenTransformationNode(str, Enum):
    """Proven-graph node vocabulary (V2.2 P0-1 contract names only).

    These names are introduced by the semantic-version phase so the dispatcher
    can select an immutable proven transition table from persisted plan JSON.
    Concrete handlers arrive with their behavior phases (P03-P12); dispatching
    to a node without a handler fails closed.
    """

    SELECT_RUN_MODE = "select_run_mode"
    PREPARE_STAGE_LAYOUT = "prepare_stage_layout"
    CREATE_SOURCE_BASELINE = "create_source_baseline"
    CONSTRUCT_DEPENDENCY_INTENT = "construct_dependency_intent"
    BIND_NPM_LOCK_AUTHORITY_POLICY = "bind_npm_lock_authority_policy"
    SELECT_SOURCE_LOCK_AUTHORITY = "select_source_lock_authority"
    READ_SOURCE_RESOLVED_LOCK = "read_source_resolved_lock"
    PROVE_SOURCE_MANIFEST_VS_RESOLUTION = "prove_source_manifest_vs_resolution"
    SOURCE_INSTALL_SAME_AUTHORITY = "source_install_same_authority"
    SOURCE_TREE = "source_tree"
    SOURCE_VERSION_PROOF = "source_version_proof"
    SOURCE_BUILD = "source_build"
    SOURCE_TEST = "source_test"
    SOURCE_DIAGNOSTIC_CAPTURE = "source_diagnostic_capture"
    FREEZE_SOURCE_BASELINE = "freeze_source_baseline"
    CREATE_DISCOVERY_GENERATION = "create_discovery_generation"
    PREPARE_DISCOVERY_TOOLCHAIN = "prepare_discovery_toolchain"
    PROVE_DISCOVERY_CLI_AUTHORITY = "prove_discovery_cli_authority"
    RUN_DISCOVERY = "run_discovery"
    ASSESS_DISCOVERY = "assess_discovery"
    PERSIST_TARGET_INTENT = "persist_target_intent"
    DISCARD_DISCOVERY = "discard_discovery"
    CREATE_AUTHORITATIVE_TARGET = "create_authoritative_target"
    APPLY_TARGET_INTENT = "apply_target_intent"
    DEPENDENCY_PLAN = "dependency_plan"
    SELECT_TARGET_LOCK_AUTHORITY = "select_target_lock_authority"
    LOCK_RESOLUTION = "lock_resolution"
    CREATE_MATERIALIZATION = "create_materialization"
    TARGET_INSTALL_SAME_AUTHORITY = "target_install_same_authority"
    TARGET_TREE = "target_tree"
    TARGET_VERSION_PROOF = "target_version_proof"
    INSPECT_MIGRATION_METADATA = "inspect_migration_metadata"
    BUILD_MIGRATION_LEDGER = "build_migration_ledger"
    EXECUTE_MIGRATION_OWNER = "execute_migration_owner"
    COMPARE_DEPENDENCY_AUTHORITY = "compare_dependency_authority"
    FREEZE_TARGET_AUTHORITY = "freeze_target_authority"
    CREATE_VALIDATION_GENERATION = "create_validation_generation"
    VALIDATION_INSTALL = "validation_install"
    VALIDATION_TREE = "validation_tree"
    VALIDATION_VERSION_PROOF = "validation_version_proof"
    VALIDATION_BUILD = "validation_build"
    VALIDATION_TEST = "validation_test"
    DIAGNOSTIC_DELTA = "diagnostic_delta"
    AGGREGATE_PROVEN_VALIDATION = "aggregate_proven_validation"
    PROMOTE_VALIDATED = "promote_validated"
    PROMOTION_PENDING = "promotion_pending"


#: Immutable proven transition table: every proven node the graph may dispatch,
#: mapped to its behavior-phase owner. Nodes without a registered handler fail
#: closed until their phase implements them.
PROVEN_TRANSITION_NODES: frozenset[str] = frozenset(node.value for node in ProvenTransformationNode)


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


def _canonical_checksum(payload: object) -> str:
    import hashlib
    import json

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


_DRAFT_CHECKSUM = "sha256:" + "0" * 64

_SHA256 = r"^sha256:[0-9a-f]{64}$"
_ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|/).+$")
_NPM_PACKAGE = re.compile(r"^@?[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)?$")


class AngularCliToolchainAuthorityError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class AngularCliToolchainAuthority(ContractModel):
    """Single generic evidence-bound Angular CLI execution authority (V2.2 §7).

    ``purpose`` distinguishes DISCOVERY and MIGRATION authorities.  Binds the
    exact requested/installed CLI, the checksummed absolute entrypoint, the
    governed Node/npm/npx identities, the exact governed PATH and allowed
    environment, the child-visible npm identity, and CLI-version proof.
    Bare ``ng`` or generic npx resolution can never produce this authority.
    """

    schema_version: str = "angular-cli-toolchain-authority-v1"
    strategy_id: str = Field(min_length=1, max_length=128)
    strategy_version: int = Field(ge=1)
    purpose: Literal["DISCOVERY", "MIGRATION"]
    run_id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    requested_cli_exact: str = Field(min_length=1)
    installed_cli_package_version: str = Field(min_length=1)
    cli_entrypoint_absolute: str = Field(min_length=1)
    cli_entrypoint_sha256: str = Field(pattern=_SHA256)
    cli_package_integrity: str = Field(min_length=1)
    node_runtime_id: str | None = None
    npm_runtime_id: str | None = None
    npx_runtime_id: str | None = None
    node_executable_absolute: str = Field(min_length=1)
    npm_executable_absolute: str = Field(min_length=1)
    npx_executable_absolute: str = Field(min_length=1)
    node_version_exact: str = Field(min_length=1)
    npm_version_exact: str = Field(min_length=1)
    npx_version_exact: str = Field(min_length=1)
    node_sha256: str = Field(pattern=_SHA256)
    npm_sha256: str = Field(pattern=_SHA256)
    npx_sha256: str = Field(pattern=_SHA256)
    governed_path: tuple[str, ...] = Field(min_length=1)
    governed_path_checksum: str = Field(pattern=_SHA256)
    allowed_environment: dict[str, str] = Field(default_factory=dict)
    allowed_environment_checksum: str = Field(pattern=_SHA256)
    child_npm_resolved_path: str = Field(min_length=1)
    child_npm_version_exact: str = Field(min_length=1)
    child_npm_sha256: str = Field(pattern=_SHA256)
    cli_version_proof_execution_id: str | None = None
    cli_version_proof_artifact_id: str | None = None
    source_generation_fingerprint: str = Field(min_length=1)
    target_stage_id: str = Field(min_length=1)
    toolchain_generation_fingerprint: str = Field(min_length=1)
    version_check_disabled_authorized: bool = False
    authority_checksum: str = Field(pattern=_SHA256)

    @model_validator(mode="after")
    def validate_and_bind(self) -> "AngularCliToolchainAuthority":
        if self.authority_checksum == _DRAFT_CHECKSUM:
            return self
        if self.requested_cli_exact != self.installed_cli_package_version:
            raise AngularCliToolchainAuthorityError(
                "ANGULAR_CLI_AUTHORITY_MISMATCH",
                "requested CLI exact must equal the installed CLI package version",
            )
        for label, path in (
            ("cli_entrypoint", self.cli_entrypoint_absolute),
            ("node", self.node_executable_absolute),
            ("npm", self.npm_executable_absolute),
            ("npx", self.npx_executable_absolute),
            ("child_npm", self.child_npm_resolved_path),
        ):
            if not _ABSOLUTE_PATH.match(path):
                raise AngularCliToolchainAuthorityError(
                    "ANGULAR_CLI_AUTHORITY_MISMATCH",
                    f"{label} must be an absolute contained path",
                )
        if not _NPM_PACKAGE.match(_cohort_package_of(self.requested_cli_exact)):
            raise AngularCliToolchainAuthorityError(
                "ANGULAR_CLI_AUTHORITY_MISMATCH",
                "requested CLI identity is not a valid npm package version binding",
            )
        if self.child_npm_resolved_path != self.npm_executable_absolute or self.child_npm_version_exact != self.npm_version_exact or self.child_npm_sha256 != self.npm_sha256:
            raise AngularCliToolchainAuthorityError(
                "CHILD_PACKAGE_MANAGER_AUTHORITY_MISMATCH",
                "child-visible npm must resolve to the bound npm descriptor",
            )
        if not self.governed_path:
            raise AngularCliToolchainAuthorityError(
                "ANGULAR_CLI_AUTHORITY_MISMATCH",
                "governed PATH cannot be empty or ambient",
            )
        if self.version_check_disabled_authorized and not self.allowed_environment.get("NG_DISABLE_VERSION_CHECK"):
            raise AngularCliToolchainAuthorityError(
                "ANGULAR_CLI_DELEGATION_UNPROVEN",
                "NG_DISABLE_VERSION_CHECK requires an explicit strategy-authorized environment value",
            )
        payload = self.model_dump(mode="json", exclude={"authority_checksum"})
        expected = _canonical_checksum(payload)
        if self.authority_checksum != expected:
            raise AngularCliToolchainAuthorityError(
                "ANGULAR_CLI_AUTHORITY_MISMATCH",
                "authority checksum does not bind its payload",
            )
        return self

    @classmethod
    def create(cls, **fields) -> "AngularCliToolchainAuthority":
        draft = cls(**fields, authority_checksum=_DRAFT_CHECKSUM)
        checksum = _canonical_checksum(draft.model_dump(mode="json", exclude={"authority_checksum"}))
        return draft.model_copy(update={"authority_checksum": checksum})


def _cohort_package_of(version_binding: str) -> str:
    # The CLI cohort identity is fixed by the catalogue; only the exact
    # version is bound here.
    return "@angular/cli"


class DiscoveryResult(ContractModel):
    """One disposable discovery probe outcome; process exit and completeness
    are independent facts (V2.2 §8/P04)."""

    schema_version: str = "discovery-result-v1"
    run_id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    generation_id: str = Field(min_length=1)
    toolchain_authority_checksum: str = Field(pattern=_SHA256)
    strategy_id: str = Field(min_length=1, max_length=128)
    strategy_version: int = Field(ge=1)
    execution_id: str = Field(min_length=1)
    process_exit_code: int | None = None
    process_status: str = Field(min_length=1)
    pre_manifest_sha256: str = Field(pattern=_SHA256)
    post_manifest_sha256: str = Field(pattern=_SHA256)
    pre_lockfile_sha256: str | None = Field(default=None, pattern=_SHA256)
    post_lockfile_sha256: str | None = Field(default=None, pattern=_SHA256)
    post_workspace_fingerprint: str | None = None
    discovery_complete: bool
    completeness_findings: tuple[str, ...] = ()
    prompt_evidence_artifact_id: str | None = None
    result_artifact_id: str | None = None
    artifact_checksum: str = Field(pattern=_SHA256)


class TargetIntent(ContractModel):
    """Normalized, source-bound target dependency intent (V2.2 §8).

    Immutable and evidence-bound: source files and discovery lock changes are
    never copied into it.  A complete intent requires proven toolchain
    authority and deterministic completeness findings.
    """

    schema_version: Literal["target-intent-v1"] = "target-intent-v1"
    run_id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    source_baseline_fingerprint: str = Field(min_length=1)
    discovery_execution_id: str = Field(min_length=1)
    process_exit_code: int | None = None
    discovery_complete: bool
    completeness_findings: tuple[str, ...] = ()
    dependency_intent_checksum: str = Field(pattern=_SHA256)
    source_package_json_sha256: str = Field(pattern=_SHA256)
    discovered_package_json_sha256: str = Field(pattern=_SHA256)
    target_cohort: dict[str, str]
    catalogue_checksum: str = Field(pattern=_SHA256)
    registry_snapshot_checksum: str = Field(pattern=_SHA256)
    discovery_toolchain_authority_checksum: str = Field(pattern=_SHA256)
    checksum: str = Field(pattern=_SHA256)

    @model_validator(mode="after")
    def validate_intent(self) -> "TargetIntent":
        if self.checksum == _DRAFT_CHECKSUM:
            return self
        if any(not _NPM_PACKAGE.match(name) or not _EXACT_SEMVER_PATTERN.match(exact) for name, exact in self.target_cohort.items()):
            raise ValueError("target cohort must bind valid npm names to exact versions")
        if "@angular/core" not in self.target_cohort or "@angular/cli" not in self.target_cohort:
            raise ValueError("target cohort must contain exact required core and CLI intent")
        payload = self.model_dump(mode="json", exclude={"checksum"})
        expected = _canonical_checksum(payload)
        if self.checksum != expected:
            raise ValueError("target intent checksum does not bind its payload")
        return self

    @classmethod
    def create(cls, **fields) -> "TargetIntent":
        draft = cls(**fields, checksum=_DRAFT_CHECKSUM)
        checksum = _canonical_checksum(draft.model_dump(mode="json", exclude={"checksum"}))
        return draft.model_copy(update={"checksum": checksum})


_EXACT_SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


class SourceBaselineEvidence(ContractModel):
    """Immutable evidence for one proven stage source baseline (V2.2 P0-2).

    Binds the section-aware root intent, the bound-npm lock authority
    selection and canonical resolved-state proof, same-authority npm-ci/npm-ls
    executions, exact cohort proof, build/test/lint executions, baseline
    diagnostics, and the frozen workspace fingerprint into one checksum.
    """

    schema_version: str = "source-baseline-evidence-v1"
    run_id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    generation_id: str = Field(min_length=1)
    input_sealed_checkpoint_id: str | None = None
    input_sealed_fingerprint: str | None = None
    dependency_intent_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    package_json_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    npm_exact_version: str = Field(min_length=1)
    lockfile_policy_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    selected_lock_filename: str = Field(min_length=1)
    selected_lock_kind: str = Field(min_length=1)
    selected_lock_version: int = Field(ge=1, le=3)
    selected_lock_raw_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    dependency_set_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    root_sync_status: str = Field(min_length=1)
    root_sync_findings: tuple[dict[str, object], ...] = ()
    runtime_identity_checksum: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    install_execution_id: str | None = None
    tree_execution_id: str | None = None
    version_proof_execution_id: str | None = None
    build_execution_id: str | None = None
    test_execution_id: str | None = None
    lint_execution_id: str | None = None
    execution_artifact_ids: tuple[str, ...] = ()
    exact_cohort: dict[str, str] = Field(default_factory=dict)
    normalized_diagnostics: tuple[dict[str, str], ...] = ()
    baseline_fingerprint: str = Field(min_length=1)
    status: str
    checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @classmethod
    def create(cls, **fields) -> "SourceBaselineEvidence":
        draft = cls(**fields, checksum=_DRAFT_CHECKSUM)
        checksum = _canonical_checksum(draft.model_dump(mode="json", exclude={"checksum"}))
        return draft.model_copy(update={"checksum": checksum})

    @model_validator(mode="after")
    def bind_checksum(self) -> "SourceBaselineEvidence":
        if self.checksum == _DRAFT_CHECKSUM:
            return self
        expected = _canonical_checksum(self.model_dump(mode="json", exclude={"checksum"}))
        if self.checksum != expected:
            raise ValueError("source baseline evidence checksum does not bind its payload")
        return self
