"""Immutable planning contracts for S2-F06-I01.

Planning produces the machine-readable contract that a later execution issue
may authorize.  It does not execute commands, persist evidence, or approve a
plan.  The models deliberately contain structured command references rather
than shell strings.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import re
from typing import Literal

from pydantic import Field, model_validator

from app.domain.contracts import ContractModel


_CHECKSUM = r"^sha256:[0-9a-f]{64}$"
_SHELL_TOKENS = re.compile(r"[;&|<>`$()\r\n]")
_EXACT_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
APPROVED_CATALOGUE_VERSIONS = frozenset({"catalog-v1", "catalog-v2"})
APPROVED_EXECUTION_PROFILE_PREFIX = "profile-"
APPROVED_VALIDATION_POLICIES = frozenset({"angular-stage-standard-v2"})
APPROVED_RECOVERY_POLICIES = frozenset({"safe-boundary-v1"})
APPROVED_REPAIR_POLICIES = frozenset({"proposer-reviewer-human-v1"})
APPROVED_BUILDERS = frozenset({
    "@angular-devkit/build-angular:application",
    "@angular-devkit/build-angular:browser",
    "@angular-devkit/build-angular:browser-esbuild",
    "@angular-devkit/build-angular:server",
})


class PlanArtifactInput(ContractModel):
    artifact_id: str = Field(min_length=1, max_length=128)
    checksum: str = Field(pattern=_CHECKSUM)


class CommandTemplateReference(ContractModel):
    """A command-registry reference safe to hand to CommandExecutor later."""

    command_id: str = Field(min_length=1, max_length=128)
    executable: str = Field(min_length=1, max_length=128)
    arguments: tuple[str, ...] = ()
    shell: Literal[False] = False
    working_directory_alias: str = Field(min_length=1, max_length=128)
    timeout_seconds: int = Field(gt=0, le=7200)
    network_profile: str = Field(min_length=1, max_length=128)
    conditional: bool = False

    @model_validator(mode="after")
    def reject_shell_syntax(self) -> "CommandTemplateReference":
        values = (self.command_id, self.executable, self.working_directory_alias, *self.arguments)
        if any(_SHELL_TOKENS.search(value) for value in values):
            raise ValueError("command references cannot contain shell syntax")
        return self


class ValidationPolicy(ContractModel):
    policy_id: str = Field(min_length=1, max_length=128)
    baseline_comparison_required: bool = True
    route_comparison_required: bool = True
    backend_comparison_required: bool = True
    required_checks: tuple[str, ...] = ("build", "test")


class RecoveryPolicy(ContractModel):
    policy_id: str = Field(min_length=1, max_length=128)
    safe_boundaries: tuple[str, ...] = ("before_bootstrap_install", "after_target_verification")
    rerun_read_only_steps: bool = True
    reconstruct_mutating_steps: bool = True


class RepairPolicy(ContractModel):
    policy_id: str = Field(min_length=1, max_length=128)
    enabled: bool = True
    proposer_reviewer_required: bool = True
    human_apply_required: bool = True


class ForbiddenChangePolicy(ContractModel):
    policy_id: str = Field(min_length=1, max_length=128)
    actions: tuple[str, ...] = (
        "force_dependency_resolution",
        "optional_standalone_migration",
        "optional_signals_migration",
        "optional_control_flow_migration",
        "optional_zoneless_migration",
    )


class BuildSystemDecision(ContractModel):
    decision_id: str = Field(min_length=1, max_length=128)
    builder: str = Field(min_length=1, max_length=256)
    action: Literal["preserve", "review_required", "blocked"]
    rationale: str = Field(min_length=1, max_length=2000)
    checksum: str = Field(pattern=_CHECKSUM)

    @classmethod
    def create(cls, *, decision_id: str, builder: str, action: Literal["preserve", "review_required", "blocked"], rationale: str) -> "BuildSystemDecision":
        payload = {"decision_id": decision_id, "builder": builder, "action": action, "rationale": rationale}
        return cls(**payload, checksum=_checksum(payload))


class MigrationPlan(ContractModel):
    plan_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    source_family: str = Field(pattern=r"^angular-(18|19|20)\.x$")
    source_exact: str = Field(min_length=1, max_length=64)
    target_family: str = Field(pattern=r"^angular-(19|20|21)\.x$")
    route: tuple[str, ...] = Field(min_length=1)
    mode: Literal["strict_compatibility"] = "strict_compatibility"
    catalogue_version: str = Field(min_length=1, max_length=128)
    stage_plan_strategy: Literal["resolve_exact_before_each_stage"] = "resolve_exact_before_each_stage"
    approval_policy: str = "mandatory-human-v1"
    repair_policy: RepairPolicy
    command_policy: str = "structured-registry-v1"
    artifact_policy: str = "immutable-stage-scoped-v1"
    checksum: str = Field(pattern=_CHECKSUM)


class StageExecutionPlan(ContractModel):
    stage_plan_id: str = Field(min_length=1, max_length=128)
    stage_id: str = Field(min_length=1, max_length=128)
    plan_version: int = Field(ge=1)
    input_fingerprint: str = Field(pattern=_CHECKSUM)
    source_family: str = Field(pattern=r"^angular-(18|19|20)\.x$")
    source_exact: str = Field(min_length=1, max_length=64)
    target_family: str = Field(pattern=r"^angular-(19|20|21)\.x$")
    target_exact: str = Field(min_length=1, max_length=64)
    target_cli_exact: str | None = Field(default=None, max_length=64)
    execution_profile_id: str = Field(min_length=1, max_length=128)
    commands: dict[str, tuple[CommandTemplateReference, ...]]
    build_system_decision: BuildSystemDecision
    validation_policy: ValidationPolicy
    recovery_policy: RecoveryPolicy
    repair_policy: RepairPolicy
    forbidden_change_policy: ForbiddenChangePolicy
    checksum: str = Field(pattern=_CHECKSUM)

    @model_validator(mode="after")
    def validate_commands(self) -> "StageExecutionPlan":
        required = {"bootstrap_install", "angular_update", "target_version_check", "final_install", "builds", "tests", "lint"}
        if set(self.commands) != required:
            raise ValueError("stage plan commands must contain the complete standard command set")
        if any(not refs for refs in self.commands.values() if self.commands.get("lint") != refs):
            raise ValueError("required stage plan command groups cannot be empty")
        if self.build_system_decision.action == "blocked":
            raise ValueError("a blocked build-system decision cannot produce an executable stage plan")
        return self


class PlanGenerationRequest(ContractModel):
    run_id: str = Field(min_length=1, max_length=128)
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    correlation_id: str | None = Field(default=None, max_length=128)
    source_exact: str = Field(min_length=1, max_length=64)
    source_family: str = Field(pattern=r"^angular-(18|19|20)\.x$")
    target_family: str = Field(default="angular-21.x", pattern=r"^angular-(19|20|21)\.x$")
    catalogue_version: str = Field(min_length=1, max_length=128)
    input_fingerprint: str = Field(pattern=_CHECKSUM)
    execution_profile_id: str = Field(min_length=1, max_length=128)
    stage_route: tuple[tuple[str, ...], ...] = Field(min_length=1)
    # Older callers and the public F06 contract omit this when the first
    # route entry carries the exact CLI version.  The stage planner derives
    # it from that entry, while still validating an explicitly supplied value.
    target_cli_exact: str | None = Field(default=None, max_length=64)
    builder: str = Field(min_length=1, max_length=256)
    prerequisite_artifacts: tuple[PlanArtifactInput, ...] = ()
    validation_policy_id: str = "angular-stage-standard-v2"
    recovery_policy_id: str = "safe-boundary-v1"
    repair_policy_id: str = "proposer-reviewer-human-v1"

    @model_validator(mode="after")
    def validate_route(self) -> "PlanGenerationRequest":
        if self.catalogue_version not in APPROVED_CATALOGUE_VERSIONS:
            raise ValueError("catalogue version is not approved")
        if not self.execution_profile_id.startswith(APPROVED_EXECUTION_PROFILE_PREFIX):
            raise ValueError("execution profile is not approved")
        if self.validation_policy_id not in APPROVED_VALIDATION_POLICIES:
            raise ValueError("validation policy is not approved")
        if self.recovery_policy_id not in APPROVED_RECOVERY_POLICIES:
            raise ValueError("recovery policy is not approved")
        if self.repair_policy_id not in APPROVED_REPAIR_POLICIES:
            raise ValueError("repair policy is not approved")
        if any(len(route) not in {4, 5} for route in self.stage_route):
            raise ValueError("stage route entries must contain Angular and CLI exact versions")
        if any(_SHELL_TOKENS.search(value) for route in self.stage_route for value in route):
            raise ValueError("stage route identifiers cannot contain shell syntax")
        if self.target_cli_exact is not None and not _EXACT_VERSION.fullmatch(self.target_cli_exact):
            raise ValueError("target CLI version must be an exact semantic version")
        if not _EXACT_VERSION.fullmatch(self.source_exact) or any(not _EXACT_VERSION.fullmatch(route[3]) or (len(route) == 5 and not _EXACT_VERSION.fullmatch(route[4])) for route in self.stage_route):
            raise ValueError("source and target versions must be exact semantic versions")
        if self.stage_route[0][0] != self.source_family or self.stage_route[-1][1] != self.target_family:
            raise ValueError("stage route must connect the requested source and target families")
        for index, route in enumerate(self.stage_route):
            source, target, _stage_id, target_exact = route[:4]
            source_major = int(source.removeprefix("angular-").removesuffix(".x"))
            target_major = int(target.removeprefix("angular-").removesuffix(".x"))
            if target_major != source_major + 1 or not target_exact:
                raise ValueError("stage route must contain adjacent families and exact targets")
            if index and self.stage_route[index - 1][1] != source:
                raise ValueError("stage route contains a discontinuity")
        return self


class PlanGenerationResult(ContractModel):
    run_id: str
    status: Literal["generated", "blocked"]
    plan: MigrationPlan
    first_stage_plan: StageExecutionPlan | None
    artifact_inputs: tuple[PlanArtifactInput, ...] = ()
    state_version: int
    idempotent_replay: bool = False
    error_code: str | None = None


def _checksum(value: object) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def checksum_model(value: ContractModel, *, exclude: tuple[str, ...] = ("checksum",)) -> str:
    payload = value.model_dump(mode="json", exclude=set(exclude))
    return _checksum(payload)


def utc_now() -> datetime:
    return datetime.now(UTC)
