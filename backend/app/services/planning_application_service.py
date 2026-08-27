"""Authoritative, side-effect-free plan generation contract for S2-F06-I01."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable

from app.domain.command import ANGULAR_INSTALLED_MIGRATION_RENDERER, ANGULAR_UPDATE_V5_RENDERER, ANGULAR_UPDATE_V6_RENDERER, TRANSFORMATION_COMMAND_CATALOGUE

try:
    from app.domain.command import ANGULAR_MIGRATE_RANGE_RENDERER
except ImportError:  # frozen contract even if sibling absent
    from app.domain.command import TransformationCommandDefinition

    ANGULAR_MIGRATE_RANGE_RENDERER = TransformationCommandDefinition(
        command_id="angular-migrate-range",
        template_id="tpl-angular-migrate-range-v1",
        executable="npx",
        argument_patterns=("ng", "update", "{package}", "--migrate-only", "--from", "{from_version}", "--to", "{to_version}"),
        executable_aliases=("npx.cmd",),
        timeout_seconds=1800,
        allowed_env_vars=("NODE_OPTIONS", "NPM_CONFIG_CACHE", "NG_DISABLE_VERSION_CHECK"),
        max_output_bytes=5_000_000,
        description="Execute a governed migrate-only update for one package range",
    )
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
    TRANSFORMER_SEMANTIC_VERSION_LEGACY,
    TRANSFORMER_SEMANTIC_VERSION_PROVEN,
    ValidationPolicy,
    checksum_model,
    proven_plan_writer_enabled,
)
from app.services.stage_knowledge_service import StageKnowledgeRegistry
from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider


class PlanningApplicationError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422, *, details=None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


def planning_failure_details(error: Exception, *, planning_component: str) -> dict[str, str]:
    current = error
    seen: set[int] = set()
    while (current.__cause__ or current.__context__) and id(current) not in seen:
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    sanitize = lambda value: re.sub(r"(?:[A-Za-z]:\\|/|\\\\)[^\s,;]+", "<path>", " ".join(str(value).split()))[:500]
    return {
        "exception_type": type(error).__name__,
        "sanitized_exception_message": sanitize(error),
        "root_exception_type": type(current).__name__,
        "root_exception_message": sanitize(current),
        "planning_component": planning_component,
    }


def run_scoped_stage_id(run_id: str, catalogue_stage_id: str) -> str:
    """Return the globally unique persisted identity for one run-owned stage."""
    scoped = re.fullmatch(r"(?P<base>.+)--(?P<suffix>[0-9a-f]{16})", catalogue_stage_id)
    if scoped is not None:
        expected_suffix = hashlib.sha256(f"{run_id}:{scoped['base']}".encode()).hexdigest()[:16]
        if scoped["suffix"] == expected_suffix:
            return catalogue_stage_id
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
    def __init__(self, *, build_system_decisions: BuildSystemDecisionService | None = None, catalogue_provider: CompatibilityCatalogueProvider | None = None) -> None:
        self._builders = build_system_decisions or BuildSystemDecisionService()
        self._catalogue = catalogue_provider or CompatibilityCatalogueProvider()

    def create(self, request: PlanGenerationRequest, *, plan_version: int = 1) -> StageExecutionPlan:
        if (
            request.transformer_semantic_version == TRANSFORMER_SEMANTIC_VERSION_PROVEN
            and not proven_plan_writer_enabled()
        ):
            raise PlanningApplicationError(
                "PLANNING_PROVEN_NOT_READY",
                "Proven plan generation remains disabled until every required command template is registered.",
                409,
            )
        source_family, target_family, catalogue_stage_id, target_exact = request.stage_route[0][:4]
        stage_id = run_scoped_stage_id(request.run_id, catalogue_stage_id)
        target_cli_exact = request.target_cli_exact or (request.stage_route[0][4] if len(request.stage_route[0]) == 5 else target_exact)
        entry = self._catalogue.load(request.catalogue_version).entry_for(source_family, target_family)
        if entry is None or target_exact != entry.target_angular_exact or target_cli_exact != entry.target_cli_exact:
            raise PlanningApplicationError(
                "TARGET_COHORT_AUTHORITY_MISMATCH",
                "Stage route exact versions differ from the approved compatibility cohort.",
                409,
            )
        target_cohort = entry.target_cohort()
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
        angular_bindings = {"target_cli_exact": target_cli_exact, "target_exact": target_exact}
        if all(
            package in target_cohort
            for package in ("typescript", "rxjs", "zone.js", "@angular-devkit/build-angular")
        ):
            angular_definition = ANGULAR_UPDATE_V6_RENDERER
            angular_template_version = 6
            angular_bindings.update(
                {
                    "target_typescript_exact": target_cohort["typescript"],
                    "target_rxjs_exact": target_cohort["rxjs"],
                    "target_zone_js_exact": target_cohort["zone.js"],
                }
            )
        else:
            angular_definition = ANGULAR_UPDATE_V5_RENDERER
            angular_template_version = 5
        commands = {
            "bootstrap_install": (self._command("npm-ci-bootstrap", request),),
            "angular_update": (self._command("angular-update-exact", request, angular_bindings, definition=angular_definition, template_version=angular_template_version),),
            "target_version_check": (self._command("angular-version-verify", request),),
            "lockfile_generation": (self._command("npm-lockfile-generate", request),),
            "final_install": (self._command("npm-ci-final", request),),
            "migrate_packages": (self._command("angular-migrate-range", request, {"package": "@angular/core", "from_version": request.source_exact, "to_version": target_exact}),),
            "builds": (self._command("npm-script-build-production", request, {"build_script": request.resolved_scripts["build"], "build_configuration": "production"}),),
            "tests": (self._command("npm-script-test-ci", request, {"test_script": request.resolved_scripts["test"], "test_watch_flag": "--watch=false"}),),
            "lint": (self._command("npm-script-lint", request, {"lint_script": request.resolved_scripts["lint"]}),) if "lint" in request.resolved_scripts else (),
        }
        if request.transformer_semantic_version == TRANSFORMER_SEMANTIC_VERSION_PROVEN:
            # Proven plans never prebind the legacy combined update or the
            # Core-only migration groups; their group contract is the proven
            # command set below.  CLI-authority-bound commands (discovery,
            # migrate-only) are bound by the behavior phases at execution time
            # and therefore never rendered from static plan bindings.
            commands = {
                "bootstrap_install": commands["bootstrap_install"],
                "dependency_tree": (self._command("npm-dependency-tree", request),),
                "target_version_check": commands["target_version_check"],
                "lockfile_generation": commands["lockfile_generation"],
                "final_install": commands["final_install"],
                "builds": commands["builds"],
                "tests": commands["tests"],
                "lint": commands["lint"],
            }
        if request.installed_migration_fallback and not StageKnowledgeRegistry.allows_installed_migration_fallback(
            StageKnowledgeRegistry().entry(_major(source_family), _major(target_family)),
            request.capability_facts,
        ):
            raise PlanningApplicationError(
                "INSTALLED_MIGRATION_FALLBACK_NOT_AUTHORIZED",
                "Installed Angular migrations require an approved stage-plan policy.",
                409,
            )
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
        draft = StageExecutionPlan(stage_plan_id=f"stage-plan-{request.run_id}-{stage_id}-v{plan_version}", stage_id=stage_id, plan_version=plan_version, input_fingerprint=request.input_fingerprint, evidence_set_checksum=request.evidence_set_checksum, input_workspace_fingerprint=request.input_workspace_fingerprint, transformer_semantic_version=request.transformer_semantic_version, run_mode=request.run_mode, qualification_authorization_checksum=request.qualification_authorization_checksum, source_family=source_family, source_exact=request.source_exact, target_family=target_family, target_exact=target_exact, target_cli_exact=target_cli_exact, target_cohort=target_cohort, execution_profile_id=request.execution_profile_id, capability_snapshot_id=request.capability_snapshot_id, capability_snapshot_checksum=request.capability_snapshot_checksum, expected_dependency_changes=dispositions, package_manager=request.package_manager, resolved_scripts=dict(request.resolved_scripts), project_targets=dict(request.project_targets), commands=commands, build_system_decision=decision, validation_policy=validation, recovery_policy=recovery, repair_policy=repair, forbidden_change_policy=forbidden, checksum="sha256:" + "0" * 64)
        return draft.model_copy(update={"checksum": checksum_model(draft)})

    @staticmethod
    def _command(command_id, request, parameter_bindings=None, *, definition=None, template_version=None):
        if command_id == "angular-update-exact":
            definition = definition or ANGULAR_UPDATE_V5_RENDERER
            template_version = template_version or 5
        elif command_id == "angular-migrate-installed":
            definition = ANGULAR_INSTALLED_MIGRATION_RENDERER
            template_version = 1
        elif command_id == "angular-migrate-range":
            definition = ANGULAR_MIGRATE_RANGE_RENDERER
            template_version = 1
        else:
            definition = TRANSFORMATION_COMMAND_CATALOGUE[command_id]
            template_version = 3 if command_id == "npm-ci-final" else 1
        stage_id = run_scoped_stage_id(request.run_id, request.stage_route[0][2])
        alias = "STAGE_WORKSPACE_" + stage_id.upper().replace("-", "_")
        bindings = dict(parameter_bindings or {})
        return CommandTemplateReference(
            command_id=definition.command_id,
            template_id="tpl-npm-ci-final-v3" if command_id == "npm-ci-final" else definition.template_id,
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
        catalogue_checksum = CompatibilityCatalogueProvider().load(request.catalogue_version).checksum
        draft = MigrationPlan(plan_id=f"plan-{request.run_id}-v{plan_version}", run_id=request.run_id, version=plan_version, source_family=request.source_family, source_exact=request.source_exact, target_family=request.target_family, route=route, catalogue_version=request.catalogue_version, catalogue_checksum=catalogue_checksum, repair_policy=repair, capability_snapshot_id=request.capability_snapshot_id, capability_snapshot_checksum=request.capability_snapshot_checksum, stage_dependency_dispositions=dispositions, transformer_semantic_version=request.transformer_semantic_version, run_mode=request.run_mode, qualification_authorization_checksum=request.qualification_authorization_checksum, checksum="sha256:" + "0" * 64)
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
            raise PlanningApplicationError(
                "PLAN_GENERATION_FAILED",
                "Plan generation failed closed.",
                503,
                details=planning_failure_details(error, planning_component="PlanningApplicationService.generate"),
            ) from error
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
