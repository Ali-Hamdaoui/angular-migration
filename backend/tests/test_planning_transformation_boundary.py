from datetime import UTC, datetime

import pytest
from pathlib import Path
from pydantic import ValidationError

from app.domain.command import ANGULAR_UPDATE_V2_RENDERER, ANGULAR_UPDATE_V4_RENDERER, DEFAULT_COMMAND_TEMPLATES, TRANSFORMATION_COMMAND_CATALOGUE, command_arguments_match
from app.domain.planning import CommandTemplateReference
from app.domain.planning import PlanGenerationRequest, StageExecutionPlan
from app.domain.contracts import CommandRequestDto
from app.command_execution.worker import CommandPolicy, CommandRegistry
from app.services.planning_application_service import StageExecutionPlanService
from app.services.planning_review_evidence_application_service import G06_APPROVAL_NEXT_RUN_STATUS
from app.services.planning_review_application_service import PlanRevisionService
from app.domain.planning_review import PlanRevisionChanges
from app.services.path_validation_service import is_portable_absolute_path


def test_g06_approval_waits_for_authoritative_stage_preparation():
    assert G06_APPROVAL_NEXT_RUN_STATUS == "WAITING_STAGE_PREPARATION"


def test_planned_command_reference_requires_immutable_template_binding():
    with pytest.raises(ValidationError):
        CommandTemplateReference(
            command_id="npm-ci-bootstrap",
            executable="npm",
            arguments=("ci",),
            working_directory_alias="STAGE_WORKSPACE_ANGULAR_18_TO_19",
            timeout_seconds=300,
            network_profile="approved-registries-only",
        )


def test_registry_defaults_cover_all_deterministic_planner_command_ids():
    registered = {template.command_id for template in DEFAULT_COMMAND_TEMPLATES}
    assert {
        "npm-ci-bootstrap",
        "angular-update-exact",
        "angular-version-verify",
        "npm-ci-final",
        "npm-script-build-production",
        "npm-script-test-ci",
        "npm-script-lint",
    } <= registered


def test_generated_commands_match_their_registered_argument_patterns():
    plan = StageExecutionPlanService().create(
        PlanGenerationRequest(
            run_id="run-command-contract", expected_state_version=1, idempotency_key="command-contract", actor="operator",
            source_exact="18.2.0", source_family="angular-18.x", target_family="angular-19.x",
            catalogue_version="catalog-v1", input_fingerprint="sha256:" + "1" * 64,
            execution_profile_id="profile-1", execution_profile_checksum="sha256:" + "4" * 64,
            builder="@angular-devkit/build-angular:application", resolved_scripts={"build": "build", "test": "test"},
            stage_route=(("angular-18.x", "angular-19.x", "angular-18-to-19", "19.2.0", "19.2.0"),),
        )
    )
    templates = {item.command_id: item for item in DEFAULT_COMMAND_TEMPLATES}

    for references in plan.commands.values():
        for reference in references:
            template = templates[reference.command_id]
            assert template.template_id == reference.template_id
            assert template.executable == reference.executable
            assert template.matches_arguments(reference.arguments)


def test_generated_commands_are_rendered_from_the_shared_transformation_catalogue():
    plan = StageExecutionPlanService().create(
        PlanGenerationRequest(
            run_id="run-shared-catalogue", expected_state_version=1, idempotency_key="shared-catalogue", actor="operator",
            source_exact="18.2.0", source_family="angular-18.x", target_family="angular-19.x",
            catalogue_version="catalog-v1", input_fingerprint="sha256:" + "1" * 64,
            execution_profile_id="profile-1", execution_profile_checksum="sha256:" + "4" * 64,
            builder="@angular-devkit/build-angular:application", resolved_scripts={"build": "build", "test": "test"},
            stage_route=(("angular-18.x", "angular-19.x", "angular-18-to-19", "19.2.0", "19.2.0"),),
        )
    )

    for references in plan.commands.values():
        for reference in references:
            if reference.command_id == "angular-update-exact":
                definition = ANGULAR_UPDATE_V4_RENDERER
            else:
                definition = TRANSFORMATION_COMMAND_CATALOGUE[reference.command_id]
            assert reference.template_id == definition.template_id
            assert reference.executable == definition.executable
            assert reference.arguments == definition.render_arguments(reference.parameter_bindings)


def test_project_aware_script_and_target_bindings_reach_the_stage_plan():
    plan = StageExecutionPlanService().create(
        PlanGenerationRequest(
            run_id="run-project-aware", expected_state_version=1, idempotency_key="project-aware", actor="operator",
            source_exact="18.2.0", source_family="angular-18.x", target_family="angular-19.x",
            catalogue_version="catalog-v1", input_fingerprint="sha256:" + "1" * 64,
            execution_profile_id="profile-1", execution_profile_checksum="sha256:" + "4" * 64,
            builder="@angular-devkit/build-angular:application",
            resolved_scripts={"build": "build:portal", "test": "test:portal", "lint": "lint:portal"},
            project_targets={"build": "portal:build", "test": "portal:test", "lint": "portal:lint"},
            stage_route=(("angular-18.x", "angular-19.x", "angular-18-to-19", "19.2.0", "19.2.0"),),
        )
    )

    assert plan.resolved_scripts == {"build": "build:portal", "test": "test:portal", "lint": "lint:portal"}
    assert plan.project_targets["build"] == "portal:build"
    assert plan.commands["builds"][0].arguments == ("run", "build:portal", "--", "--configuration", "production")
    assert plan.commands["tests"][0].arguments == ("run", "test:portal", "--", "--watch=false")
    assert plan.commands["lint"][0].arguments == ("run", "lint:portal")


def test_worker_registers_every_generated_command_shape():
    registry = CommandRegistry()
    planner_commands = {
        "npm-ci-bootstrap": ("ci",),
        "angular-update-exact": ("--yes", "-p", "@angular/cli@19.2.0", "ng", "update", "@angular/cli@19.2.0", "@angular/core@19.2.0"),
        "angular-version-verify": ("ng", "version"),
        "npm-ci-final": ("ci",),
        "npm-script-build-production": ("run", "build", "--", "--configuration", "production"),
        "npm-script-test-ci": ("run", "test", "--", "--watch=false"),
        "npm-script-lint": ("run", "lint"),
    }

    for command_id, arguments in planner_commands.items():
        definition = registry.find(command_id)
        assert definition.matches_arguments(arguments)


def test_generated_plan_reaches_worker_policy_without_starting_a_process(tmp_path):
    plan = StageExecutionPlanService().create(
        PlanGenerationRequest(
            run_id="run-dry-run", expected_state_version=1, idempotency_key="dry-run", actor="operator",
            source_exact="18.2.0", source_family="angular-18.x", target_family="angular-19.x",
            catalogue_version="catalog-v1", input_fingerprint="sha256:" + "1" * 64,
            execution_profile_id="profile-1", execution_profile_checksum="sha256:" + "4" * 64,
            builder="@angular-devkit/build-angular:application", resolved_scripts={"build": "build", "test": "test"},
            stage_route=(("angular-18.x", "angular-19.x", "angular-18-to-19", "19.2.0", "19.2.0"),),
        )
    )
    workspace = tmp_path / "stage"
    workspace.mkdir()
    policy = CommandPolicy(
        sandbox_root=tmp_path,
        working_directory_aliases={
            "STAGE_WORKSPACE_ANGULAR_18_TO_19__7793C74A47FE5FF8": workspace
        },
        runtime_profiles=frozenset({"profile-1"}),
        network_profiles=frozenset({"approved-registries-only"}),
    )

    for references in plan.commands.values():
        for reference in references:
            structured = policy.validate(CommandRequestDto(
                command_id=reference.command_id,
                run_id="run-dry-run",
                stage_id=plan.stage_id,
                requested_by="operator",
                requester="operator",
                executable=reference.executable,
                arguments=list(reference.arguments),
                working_directory_alias=reference.working_directory_alias,
                runtime_profile_id="profile-1",
                timeout_seconds=reference.timeout_seconds,
                network_profile=reference.network_profile,
                idempotency_key=f"dry-run:{reference.command_id}",
                requested_at=datetime.now(UTC),
            ))
            assert structured.command == (reference.executable, *reference.arguments)


def test_worker_policy_accepts_a_bound_stage_workspace_alias(tmp_path):
    workspace = tmp_path / "stage"
    workspace.mkdir()

    policy = CommandPolicy(
        sandbox_root=tmp_path,
        working_directory_aliases={"STAGE_WORKSPACE_ANGULAR_18_TO_19": workspace},
    )

    assert policy.working_directory_aliases["STAGE_WORKSPACE_ANGULAR_18_TO_19"] == workspace.resolve()


def test_global_cli_target_cannot_override_the_first_route_or_core_major():
    with pytest.raises(ValueError, match="CLI target"):
        PlanGenerationRequest(
            run_id="run-1", expected_state_version=1, idempotency_key="plan-1", actor="operator",
            source_exact="18.2.0", source_family="angular-18.x", target_family="angular-19.x",
            catalogue_version="catalog-v1", input_fingerprint="sha256:" + "1" * 64,
            execution_profile_id="profile-1", builder="@angular-devkit/build-angular:application",
            stage_route=(("angular-18.x", "angular-19.x", "angular-18-to-19", "19.2.0", "21.0.0"),),
            target_cli_exact="21.0.0",
        )


def test_stage_plan_keeps_evidence_checksum_separate_from_workspace_fingerprint():
    plan = StageExecutionPlan(
        stage_plan_id="stage-plan-1", stage_id="stage-18-to-19", plan_version=1,
        input_fingerprint="sha256:" + "1" * 64,
        evidence_set_checksum="sha256:" + "2" * 64,
        input_workspace_fingerprint="sha256:" + "3" * 64,
        source_family="angular-18.x", source_exact="18.2.0", target_family="angular-19.x",
        target_exact="19.2.0", target_cli_exact="19.2.0", execution_profile_id="profile-1",
        commands={"bootstrap_install": ({"command_id": "x", "template_id": "t", "template_version": 1, "executable": "npm", "arguments": [], "working_directory_alias": "STAGE_WORKSPACE_ANGULAR_18_TO_19", "timeout_seconds": 1, "network_profile": "none"},), "angular_update": ({"command_id": "x2", "template_id": "t2", "template_version": 1, "executable": "npx", "arguments": [], "working_directory_alias": "STAGE_WORKSPACE_ANGULAR_18_TO_19", "timeout_seconds": 1, "network_profile": "none"},), "target_version_check": ({"command_id": "x3", "template_id": "t3", "template_version": 1, "executable": "npx", "arguments": [], "working_directory_alias": "STAGE_WORKSPACE_ANGULAR_18_TO_19", "timeout_seconds": 1, "network_profile": "none"},), "lockfile_generation": ({"command_id": "x-lock", "template_id": "t-lock", "template_version": 1, "executable": "npm", "arguments": [], "working_directory_alias": "STAGE_WORKSPACE_ANGULAR_18_TO_19", "timeout_seconds": 1, "network_profile": "none"},), "final_install": ({"command_id": "x4", "template_id": "t4", "template_version": 1, "executable": "npm", "arguments": [], "working_directory_alias": "STAGE_WORKSPACE_ANGULAR_18_TO_19", "timeout_seconds": 1, "network_profile": "none"},), "builds": ({"command_id": "x5", "template_id": "t5", "template_version": 1, "executable": "npm", "arguments": [], "working_directory_alias": "STAGE_WORKSPACE_ANGULAR_18_TO_19", "timeout_seconds": 1, "network_profile": "none"},), "tests": ({"command_id": "x6", "template_id": "t6", "template_version": 1, "executable": "npm", "arguments": [], "working_directory_alias": "STAGE_WORKSPACE_ANGULAR_18_TO_19", "timeout_seconds": 1, "network_profile": "none"},), "lint": ({"command_id": "x7", "template_id": "t7", "template_version": 1, "executable": "npm", "arguments": [], "working_directory_alias": "STAGE_WORKSPACE_ANGULAR_18_TO_19", "timeout_seconds": 1, "network_profile": "none"},)},
        build_system_decision={"decision_id": "d", "builder": "@angular-devkit/build-angular:application", "action": "preserve", "rationale": "observed", "checksum": "sha256:" + "4" * 64},
        validation_policy={"policy_id": "angular-stage-standard-v2"}, recovery_policy={"policy_id": "safe-boundary-v1"}, repair_policy={"policy_id": "proposer-reviewer-human-v1"}, forbidden_change_policy={"policy_id": "forbidden-modernization-v1"}, checksum="sha256:" + "5" * 64,
    )
    assert plan.evidence_set_checksum != plan.input_workspace_fingerprint


@pytest.mark.parametrize("value", [r"C:\unauthorized\path", r"\\server\share\path", "/unauthorized/path"])
def test_path_classification_is_host_independent(value):
    assert is_portable_absolute_path(value) is True


def test_new_plan_uses_v4_template():
    """Newly generated angular-update-exact commands use the strict V4 template."""
    plan = StageExecutionPlanService().create(
        PlanGenerationRequest(
            run_id="run-v4-test", expected_state_version=1, idempotency_key="v4-test", actor="operator",
            source_exact="18.2.0", source_family="angular-18.x", target_family="angular-19.x",
            catalogue_version="catalog-v1", input_fingerprint="sha256:" + "1" * 64,
            execution_profile_id="profile-1", execution_profile_checksum="sha256:" + "4" * 64,
            builder="@angular-devkit/build-angular:application", resolved_scripts={"build": "build", "test": "test"},
            stage_route=(("angular-18.x", "angular-19.x", "angular-18-to-19", "19.2.0", "19.2.0"),),
        )
    )
    update = plan.commands["angular_update"][0]
    assert update.template_version == 4
    assert update.template_id == ANGULAR_UPDATE_V4_RENDERER.template_id
    assert "--allow-dirty" not in update.arguments
    assert "--force" not in update.arguments
    assert "--legacy-peer-deps" not in update.arguments
    assert "--interactive=false" not in " ".join(update.arguments)
    assert ANGULAR_UPDATE_V4_RENDERER.render_arguments({
        "target_cli_exact": plan.target_cli_exact,
        "target_exact": plan.target_exact,
    }) == update.arguments


def test_planned_angular_update_matches_v4_template():
    """The rendered arguments match the strict V4 template pattern."""
    plan = StageExecutionPlanService().create(
        PlanGenerationRequest(
            run_id="run-match-v4", expected_state_version=1, idempotency_key="match-v4", actor="operator",
            source_exact="18.2.0", source_family="angular-18.x", target_family="angular-19.x",
            catalogue_version="catalog-v1", input_fingerprint="sha256:" + "1" * 64,
            execution_profile_id="profile-1", execution_profile_checksum="sha256:" + "4" * 64,
            builder="@angular-devkit/build-angular:application", resolved_scripts={"build": "build", "test": "test"},
            stage_route=(("angular-18.x", "angular-19.x", "angular-18-to-19", "19.2.0", "19.2.0"),),
        )
    )
    update = plan.commands["angular_update"][0]
    assert command_arguments_match(ANGULAR_UPDATE_V4_RENDERER.argument_patterns, update.arguments)
    assert command_arguments_match(ANGULAR_UPDATE_V2_RENDERER.argument_patterns, update.arguments) is False


def test_rebuilt_plan_uses_catalogue_for_arguments():
    """Revised angular_update commands are rendered via the strict V4 catalogue."""
    from app.services.planning_application_service import PlanningApplicationService
    from app.domain.planning_review import PlanRevisionRequest, G06Gate

    result = PlanningApplicationService().generate(PlanGenerationRequest(
        run_id="run-rebuild", expected_state_version=1, idempotency_key="rebuild-plan", actor="operator",
        source_exact="18.2.0", source_family="angular-18.x", target_family="angular-19.x",
        catalogue_version="catalog-v1", input_fingerprint="sha256:" + "1" * 64,
        execution_profile_id="profile-1", execution_profile_checksum="sha256:" + "4" * 64,
        builder="@angular-devkit/build-angular:application", resolved_scripts={"build": "build", "test": "test"},
        stage_route=(("angular-18.x", "angular-19.x", "angular-18-to-19", "19.2.0", "19.2.0"),),
    ))
    changes = PlanRevisionChanges(target_cli_exact="19.3.0")
    request = PlanRevisionRequest(
        run_id="run-rebuild", idempotency_key="rebuild-v2", expected_state_version=1,
        actor="test-operator",
        artifact_set_checksum="sha256:" + "a" * 64,
        plan=result.plan.model_dump(mode="json"),
        stage_plan=result.first_stage_plan.model_dump(mode="json"),
        changes=changes,
    )
    service = PlanRevisionService()
    revision = service.revise(request)
    revised_commands = revision.stage_plan.get("commands", {})
    angular_update = revised_commands.get("angular_update", [{}])[0]
    expected_v4 = ANGULAR_UPDATE_V4_RENDERER.render_arguments({
        "target_cli_exact": "19.3.0",
        "target_exact": "19.2.0",
    })
    assert angular_update["arguments"] == list(expected_v4), (
        f"Revised arguments {angular_update['arguments']} do not match "
        f"ANGULAR_UPDATE_V4_RENDERER output {list(expected_v4)}"
    )
    assert angular_update.get("template_version") == 4, (
        f"Expected template_version=4, got {angular_update.get('template_version')}"
    )
    assert angular_update.get("template_id") == ANGULAR_UPDATE_V4_RENDERER.template_id


def test_v1_plan_remains_immutable():
    """The catalogue v1 template still contains --interactive=false."""
    v1 = TRANSFORMATION_COMMAND_CATALOGUE["angular-update-exact"]
    assert "--interactive=false" in v1.argument_patterns
    assert v1.template_id == "tpl-angular-update-exact"


def test_old_g07_rejects_v2_argv():
    """An old G07-approved v1 argument tuple does NOT match the v2 pattern."""
    v1_args = (
        "--yes", "-p", "@angular/cli@19.2.0", "ng", "update",
        "@angular/core@19.2.0", "@angular/cli@19.2.0", "--interactive=false",
    )
    v2_args = (
        "--yes", "-p", "@angular/cli@19.2.0", "ng", "update",
        "@angular/core@19.2.0", "@angular/cli@19.2.0",
    )
    assert command_arguments_match(TRANSFORMATION_COMMAND_CATALOGUE["angular-update-exact"].argument_patterns, v1_args)
    assert command_arguments_match(TRANSFORMATION_COMMAND_CATALOGUE["angular-update-exact"].argument_patterns, v2_args) is False
    assert command_arguments_match(ANGULAR_UPDATE_V2_RENDERER.argument_patterns, v2_args)
    assert command_arguments_match(ANGULAR_UPDATE_V2_RENDERER.argument_patterns, v1_args) is False
