import pytest
from pydantic import ValidationError

from app.domain.command import DEFAULT_COMMAND_TEMPLATES
from app.domain.planning import CommandTemplateReference
from app.domain.planning import PlanGenerationRequest, StageExecutionPlan
from app.services.planning_review_evidence_application_service import G06_APPROVAL_NEXT_RUN_STATUS
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
        commands={"bootstrap_install": ({"command_id": "x", "template_id": "t", "template_version": 1, "executable": "npm", "arguments": [], "working_directory_alias": "STAGE_WORKSPACE_ANGULAR_18_TO_19", "timeout_seconds": 1, "network_profile": "none"},), "angular_update": ({"command_id": "x2", "template_id": "t2", "template_version": 1, "executable": "npx", "arguments": [], "working_directory_alias": "STAGE_WORKSPACE_ANGULAR_18_TO_19", "timeout_seconds": 1, "network_profile": "none"},), "target_version_check": ({"command_id": "x3", "template_id": "t3", "template_version": 1, "executable": "npx", "arguments": [], "working_directory_alias": "STAGE_WORKSPACE_ANGULAR_18_TO_19", "timeout_seconds": 1, "network_profile": "none"},), "final_install": ({"command_id": "x4", "template_id": "t4", "template_version": 1, "executable": "npm", "arguments": [], "working_directory_alias": "STAGE_WORKSPACE_ANGULAR_18_TO_19", "timeout_seconds": 1, "network_profile": "none"},), "builds": ({"command_id": "x5", "template_id": "t5", "template_version": 1, "executable": "npm", "arguments": [], "working_directory_alias": "STAGE_WORKSPACE_ANGULAR_18_TO_19", "timeout_seconds": 1, "network_profile": "none"},), "tests": ({"command_id": "x6", "template_id": "t6", "template_version": 1, "executable": "npm", "arguments": [], "working_directory_alias": "STAGE_WORKSPACE_ANGULAR_18_TO_19", "timeout_seconds": 1, "network_profile": "none"},), "lint": ({"command_id": "x7", "template_id": "t7", "template_version": 1, "executable": "npm", "arguments": [], "working_directory_alias": "STAGE_WORKSPACE_ANGULAR_18_TO_19", "timeout_seconds": 1, "network_profile": "none"},)},
        build_system_decision={"decision_id": "d", "builder": "@angular-devkit/build-angular:application", "action": "preserve", "rationale": "observed", "checksum": "sha256:" + "4" * 64},
        validation_policy={"policy_id": "angular-stage-standard-v2"}, recovery_policy={"policy_id": "safe-boundary-v1"}, repair_policy={"policy_id": "proposer-reviewer-human-v1"}, forbidden_change_policy={"policy_id": "forbidden-modernization-v1"}, checksum="sha256:" + "5" * 64,
    )
    assert plan.evidence_set_checksum != plan.input_workspace_fingerprint


@pytest.mark.parametrize("value", [r"C:\unauthorized\path", r"\\server\share\path", "/unauthorized/path"])
def test_path_classification_is_host_independent(value):
    assert is_portable_absolute_path(value) is True
