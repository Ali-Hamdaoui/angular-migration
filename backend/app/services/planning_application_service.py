"""Authoritative, side-effect-free plan generation contract for S2-F06-I01."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

from app.domain.command import ANGULAR_INSTALLED_MIGRATION_RENDERER, ANGULAR_UPDATE_V4_RENDERER, TRANSFORMATION_COMMAND_CATALOGUE
from app.domain.planning import (
    BuildSystemDecision,
    CommandTemplateReference,
    ForbiddenChangePolicy,
    MigrationPlan,
    PlanGenerationRequest,
    PlanGenerationResult,
    RepairPolicy,
    RecoveryPolicy,
    StageExecutionPlan,
    ValidationPolicy,
    checksum_model,
)
from app.services.stage_knowledge_service import StageKnowledgeRegistry


class PlanningApplicationError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def run_scoped_stage_id(run_id: str, catalogue_stage_id: str) -> str:
    """Return the globally unique persisted identity for one run-owned stage."""
    suffix = hashlib.sha256(f"{run_id}:{catalogue_stage_id}".encode()).hexdigest()[:16]
    marker = f"--{suffix}"
    if catalogue_stage_id.endswith(marker):
        return catalogue_stage_id
    return f"{catalogue_stage_id[: 64 - len(marker)]}{marker}"


class BuildSystemDecisionService:
    """Make the builder decision deterministically from observed builder data."""

    def decide(self, *, builder: str, decision_id: str) -> BuildSystemDecision:
        from app.domain.planning import APPROVED_BUILDERS
        if builder not in APPROVED_BUILDERS:
            return BuildSystemDecision.create(decision_id=decision_id, builder=builder, action="blocked", rationale="Unsupported custom builder requires manual preparation.")
        return BuildSystemDecision.create(decision_id=decision_id, builder=builder, action="preserve", rationale="Preserve the existing supported Angular builder; modernization is not part of this plan.")


class StageExecutionPlanService:
    def __init__(self, *, build_system_decisions: BuildSystemDecisionService | None = None) -> None:
        self._builders = build_system_decisions or BuildSystemDecisionService()

    def create(self, request: PlanGenerationRequest, *, plan_version: int = 1) -> StageExecutionPlan:
        source_family, target_family, catalogue_stage_id, target_exact = request.stage_route[0][:4]
        stage_id = run_scoped_stage_id(request.run_id, catalogue_stage_id)
        target_cli_exact = request.target_cli_exact or (request.stage_route[0][4] if len(request.stage_route[0]) == 5 else target_exact)
        decision = self._builders.decide(builder=request.builder, decision_id=f"builder-{request.run_id}-{stage_id}-v{plan_version}")
        if decision.action == "blocked":
            raise PlanningApplicationError("UNSUPPORTED_BUILD_SYSTEM", decision.rationale, 409)
        if request.execution_profile_checksum is None:
            raise PlanningApplicationError(
                "EXECUTION_PROFILE_CHECKSUM_REQUIRED",
                "The selected execution profile checksum is required for every planned command.",
                409,
            )
        missing_scripts = [name for name in ("build", "test") if name not in request.resolved_scripts]
        if missing_scripts:
            raise PlanningApplicationError(
                "REQUIRED_SCRIPT_NOT_RESOLVED",
                "Required package scripts were not resolved: " + ", ".join(missing_scripts),
                409,
            )
        validation = ValidationPolicy(policy_id=request.validation_policy_id)
        recovery = RecoveryPolicy(policy_id=request.recovery_policy_id)
        repair = RepairPolicy(policy_id=request.repair_policy_id)
        forbidden = ForbiddenChangePolicy(policy_id="forbidden-modernization-v1")
        commands = {
            "bootstrap_install": (self._command("npm-ci-bootstrap", request),),
            "angular_update": (self._command("angular-update-exact", request, {"target_cli_exact": target_cli_exact, "target_exact": target_exact}),),
            "target_version_check": (self._command("angular-version-verify", request),),
            "lockfile_generation": (self._command("npm-lockfile-generate", request),),
            "final_install": (self._command("npm-ci-final", request),),
            "builds": (self._command("npm-script-build-production", request, {"build_script": request.resolved_scripts["build"], "build_configuration": "production"}),),
            "tests": (self._command("npm-script-test-ci", request, {"test_script": request.resolved_scripts["test"], "test_watch_flag": "--watch=false"}),),
            "lint": (self._command("npm-script-lint", request, {"lint_script": request.resolved_scripts["lint"]}),) if "lint" in request.resolved_scripts else (),
        }
        if request.installed_migration_fallback:
            commands["installed_migration_fallback"] = (
                self._command(
                    "angular-migrate-installed",
                    request,
                    {
                        "package": "@angular/core",
                        "from_version": request.source_exact,
                        "to_version": target_exact,
                    },
                ),
            )
        knowledge = StageKnowledgeRegistry().entry(_major(source_family), _major(target_family))
        dispositions = StageKnowledgeRegistry.dependency_dispositions(knowledge, request.capability_facts)
        draft = StageExecutionPlan(stage_plan_id=f"stage-plan-{request.run_id}-{stage_id}-v{plan_version}", stage_id=stage_id, plan_version=plan_version, input_fingerprint=request.input_fingerprint, evidence_set_checksum=request.evidence_set_checksum, input_workspace_fingerprint=request.input_workspace_fingerprint, source_family=source_family, source_exact=request.source_exact, target_family=target_family, target_exact=target_exact, target_cli_exact=target_cli_exact, execution_profile_id=request.execution_profile_id, capability_snapshot_id=request.capability_snapshot_id, capability_snapshot_checksum=request.capability_snapshot_checksum, expected_dependency_changes=dispositions, package_manager=request.package_manager, resolved_scripts=dict(request.resolved_scripts), project_targets=dict(request.project_targets), commands=commands, build_system_decision=decision, validation_policy=validation, recovery_policy=recovery, repair_policy=repair, forbidden_change_policy=forbidden, checksum="sha256:" + "0" * 64)
        return draft.model_copy(update={"checksum": checksum_model(draft)})

    @staticmethod
    def _command(command_id, request, parameter_bindings=None):
        if command_id == "angular-update-exact":
            definition = ANGULAR_UPDATE_V4_RENDERER
            template_version = 4
        elif command_id == "angular-migrate-installed":
            definition = ANGULAR_INSTALLED_MIGRATION_RENDERER
            template_version = 1
        else:
            definition = TRANSFORMATION_COMMAND_CATALOGUE[command_id]
            template_version = 1
        stage_id = run_scoped_stage_id(request.run_id, request.stage_route[0][2])
        alias = "STAGE_WORKSPACE_" + stage_id.upper().replace("-", "_")
        bindings = dict(parameter_bindings or {})
        return CommandTemplateReference(
            command_id=definition.command_id,
            template_id=definition.template_id,
            template_version=template_version,
            parameter_bindings=bindings,
            executable=definition.executable,
            arguments=definition.render_arguments(bindings),
            working_directory_alias=alias,
            timeout_seconds=definition.timeout_seconds,
            network_profile=definition.network_profile,
            runtime_profile_checksum=request.execution_profile_checksum,
            conditional=definition.conditional,
        )


class MigrationPlanService:
    def create(self, request: PlanGenerationRequest, *, plan_version: int = 1) -> MigrationPlan:
        repair = RepairPolicy(policy_id=request.repair_policy_id)
        route = tuple(
            run_scoped_stage_id(request.run_id, item[2])
            for item in request.stage_route
        )
        dispositions = {
            item[2]: StageKnowledgeRegistry.dependency_dispositions(
                StageKnowledgeRegistry().entry(_major(item[0]), _major(item[1])),
                request.capability_facts,
            )
            for item in request.stage_route
        }
        draft = MigrationPlan(plan_id=f"plan-{request.run_id}-v{plan_version}", run_id=request.run_id, version=plan_version, source_family=request.source_family, source_exact=request.source_exact, target_family=request.target_family, route=route, catalogue_version=request.catalogue_version, repair_policy=repair, capability_snapshot_id=request.capability_snapshot_id, capability_snapshot_checksum=request.capability_snapshot_checksum, stage_dependency_dispositions=dispositions, checksum="sha256:" + "0" * 64)
        return draft.model_copy(update={"checksum": checksum_model(draft)})


class PlanningApplicationService:
    """Compose deterministic planners while leaving persistence to I02."""

    def __init__(self, *, state_version_reader: Callable[[str], int] | None = None, artifact_checksum_reader: Callable[[str], str] | None = None, migration_plans: MigrationPlanService | None = None, stage_plans: StageExecutionPlanService | None = None) -> None:
        self._state_version_reader = state_version_reader
        self._artifact_checksum_reader = artifact_checksum_reader
        self._migration_plans = migration_plans or MigrationPlanService()
        self._stage_plans = stage_plans or StageExecutionPlanService()
        self._results: dict[tuple[str, str], tuple[str, PlanGenerationResult]] = {}

    def generate(self, request: PlanGenerationRequest, *, plan_version: int = 1) -> PlanGenerationResult:
        key = (request.run_id, request.idempotency_key)
        request_checksum = self._request_checksum(request)
        existing = self._results.get(key)
        if existing:
            if existing[0] != request_checksum:
                raise PlanningApplicationError("IDEMPOTENCY_PAYLOAD_MISMATCH", "The idempotency key was already used with a different payload.", 409)
            return existing[1].model_copy(update={"idempotent_replay": True})
        if self._state_version_reader and self._state_version_reader(request.run_id) != request.expected_state_version:
            raise PlanningApplicationError("STALE_STATE_VERSION", "The run state version is stale.", 409)
        self._validate_prerequisites(request)
        if request.builder not in __import__("app.domain.planning", fromlist=["APPROVED_BUILDERS"]).APPROVED_BUILDERS:
            raise PlanningApplicationError("UNSUPPORTED_BUILD_SYSTEM", "Unsupported custom builder requires manual preparation.", 409)
        try:
            plan = self._migration_plans.create(request, plan_version=plan_version)
            stage = self._stage_plans.create(request, plan_version=plan_version)
        except PlanningApplicationError:
            raise
        except Exception as error:
            raise PlanningApplicationError("PLAN_GENERATION_FAILED", "Plan generation failed closed.", 503) from error
        result = PlanGenerationResult(run_id=request.run_id, status="generated", plan=plan, first_stage_plan=stage, artifact_inputs=request.prerequisite_artifacts, state_version=request.expected_state_version)
        self._results[key] = (request_checksum, result)
        return result

    def _validate_prerequisites(self, request: PlanGenerationRequest) -> None:
        if not self._artifact_checksum_reader:
            return
        for artifact in request.prerequisite_artifacts:
            try:
                actual = self._artifact_checksum_reader(artifact.artifact_id)
            except Exception as error:
                raise PlanningApplicationError("PREREQUISITE_ARTIFACT_UNAVAILABLE", "A prerequisite artifact is unavailable.", 409) from error
            if actual != artifact.checksum:
                raise PlanningApplicationError("PREREQUISITE_ARTIFACT_CHECKSUM_MISMATCH", "A prerequisite artifact checksum does not match.", 409)

    @staticmethod
    def _request_checksum(request: PlanGenerationRequest) -> str:
        return "sha256:" + hashlib.sha256(json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _major(family: str) -> int:
    return int(family.removeprefix("angular-").removesuffix(".x"))
