"""Authoritative, side-effect-free plan generation contract for S2-F06-I01."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from app.domain.command import (
    ANGULAR_UPDATE_V2_RENDERER,
    NPM_LOCKFILE_RECREATE_V2_RENDERER,
    TRANSFORMATION_COMMAND_CATALOGUE,
)
from app.domain.planning import (
    BuildSystemDecision,
    CommandTemplateReference,
    ForbiddenChangePolicy,
    MigrationPlan,
    PlanGenerationRequest,
    PlanGenerationResult,
    RecoveryPolicy,
    RepairPolicy,
    StageExecutionPlan,
    ValidationPolicy,
    checksum_model,
)


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
        if request.catalogue_version == "catalog-v3":
            commands["angular_update"] = self._proven_stage_commands(request, source_family, target_family)
        draft = StageExecutionPlan(stage_plan_id=f"stage-plan-{request.run_id}-{stage_id}-v{plan_version}", stage_id=stage_id, plan_version=plan_version, input_fingerprint=request.input_fingerprint, evidence_set_checksum=request.evidence_set_checksum, input_workspace_fingerprint=request.input_workspace_fingerprint, source_family=source_family, source_exact=request.source_exact, target_family=target_family, target_exact=target_exact, target_cli_exact=target_cli_exact, execution_profile_id=request.execution_profile_id, package_manager=request.package_manager, resolved_scripts=dict(request.resolved_scripts), project_targets=dict(request.project_targets), commands=commands, build_system_decision=decision, validation_policy=validation, recovery_policy=recovery, repair_policy=repair, forbidden_change_policy=forbidden, checksum="sha256:" + "0" * 64)
        return draft.model_copy(update={"checksum": checksum_model(draft)})

    def _proven_stage_commands(self, request: PlanGenerationRequest, source_family: str, target_family: str):
        """Render the exact manifest/lock/migration sequence proven by catalog-v3."""
        from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider

        entry = CompatibilityCatalogueProvider().load("catalog-v3").entry_for(source_family, target_family)
        if entry is None:
            raise PlanningApplicationError("CATALOGUE_STAGE_MISSING", "The proven stage is absent from catalog-v3", 409)
        target_major = int(target_family.removeprefix("angular-").removesuffix(".x"))
        source_major = target_major - 1
        assignments = {
            **{f"dependencies[@angular/{name}]": entry.target_angular_exact for name in (
                "animations", "common", "compiler", "core", "forms", "platform-browser",
                "platform-browser-dynamic", "router",
            )},
            "dependencies[rxjs]": entry.rxjs_exact,
            "dependencies[zone.js]": entry.zone_js_exact,
            "devDependencies[@angular-devkit/build-angular]": entry.target_cli_exact,
            "devDependencies[@angular/cli]": entry.target_cli_exact,
            "devDependencies[@angular/compiler-cli]": entry.target_angular_exact,
            "devDependencies[typescript]": entry.typescript_exact,
        }
        deletes: list[str] = []
        if target_major == 12:
            assignments.update({
                "devDependencies[codelyzer]": "6.0.2",
                "devDependencies[@babel/core]": "7.14.8",
                "devDependencies[browserslist]": "4.28.2",
                "devDependencies[tmp]": "0.2.1",
                "devDependencies[node-releases]": "2.0.44",
                "devDependencies[karma]": "6.4.4",
                "devDependencies[karma-jasmine-html-reporter]": "1.5.4",
                "overrides[tmp]": "0.2.1",
                "overrides[node-releases]": "2.0.44",
            })
        if target_major >= 13:
            deletes.extend(("devDependencies[codelyzer]", "devDependencies[tslint]"))
            for name in ("builder", "eslint-plugin", "eslint-plugin-template", "schematics", "template-parser"):
                assignments[f"devDependencies[@angular-eslint/{name}]"] = entry.angular_eslint_exact
            if target_major == 13:
                assignments["overrides[@nrwl/cli]"] = "13.1.3"
            elif target_major >= 14:
                deletes.append("overrides[@nrwl/cli]")
        if target_major == 18:
            assignments.update({
                "devDependencies[chokidar]": "3.6.0",
                "devDependencies[@typescript-eslint/eslint-plugin]": "^7.2.0",
                "devDependencies[@typescript-eslint/parser]": "^7.2.0",
                "devDependencies[eslint]": "^8.57.0",
                "overrides[@angular-devkit/core][chokidar]": "3.6.0",
                "overrides[@angular/compiler-cli][chokidar]": "4.0.3",
            })
        elif target_major >= 19:
            deletes.extend((
                "devDependencies[chokidar]",
                "overrides[@angular-devkit/core]",
                "overrides[@angular/compiler-cli]",
            ))
        commands = [
            *(self._command("npm-pkg-delete", request, {"field": field}) for field in dict.fromkeys(deletes)),
            *(self._command("npm-pkg-set", request, {"assignment": f"{field}={value}"}) for field, value in assignments.items() if value),
            self._command("npm-lockfile-generate", request),
            self._command("npm-ci-final", request),
            self._command("angular-migrate-only", request, {
                "package": "@angular/cli", "source_floor": f"{source_major}.0.0", "target_exact": entry.target_cli_exact,
            }),
            self._command("angular-migrate-only", request, {
                "package": "@angular/core", "source_floor": f"{source_major}.0.0", "target_exact": entry.target_angular_exact,
            }),
        ]
        if entry.angular_eslint_exact and target_major in {13, 14, 15, 16, 17, 18, 20}:
            commands.append(self._command("angular-migrate-only", request, {
                "package": "@angular-eslint/schematics", "source_floor": f"{source_major}.0.0", "target_exact": entry.angular_eslint_exact,
            }))
        if target_major == 20:
            commands.append(self._command("angular-generate-inject", request))
        return tuple(commands)

    @staticmethod
    def _command(command_id, request, parameter_bindings=None):
        if command_id == "angular-update-exact":
            definition = ANGULAR_UPDATE_V2_RENDERER
            template_version = 2
        elif command_id == "npm-lockfile-generate" and request.catalogue_version == "catalog-v3":
            definition = NPM_LOCKFILE_RECREATE_V2_RENDERER
            template_version = 2
        else:
            definition = TRANSFORMATION_COMMAND_CATALOGUE[command_id]
            template_version = 1
        stage_id = run_scoped_stage_id(request.run_id, request.stage_route[0][2])
        alias = "STAGE_WORKSPACE_" + stage_id.upper().replace("-", "_")
        bindings = dict(parameter_bindings or {})
        if command_id == "angular-migrate-only":
            bindings["runner_path"] = str(
                Path(__file__).resolve().parents[1]
                / "command_execution"
                / "run_installed_migrations.cjs"
            )
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
        draft = MigrationPlan(plan_id=f"plan-{request.run_id}-v{plan_version}", run_id=request.run_id, version=plan_version, source_family=request.source_family, source_exact=request.source_exact, target_family=request.target_family, route=route, catalogue_version=request.catalogue_version, repair_policy=repair, checksum="sha256:" + "0" * 64)
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
