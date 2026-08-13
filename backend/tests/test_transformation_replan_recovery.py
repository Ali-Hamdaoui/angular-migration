from types import SimpleNamespace

from app.api.transformation_replan_contracts import TransformationReplanRecoveryRequest
from app.services.planning_application_service import PlanningApplicationService
from app.services.transformation_replan_recovery_service import TransformationReplanRecoveryService
from app.services.transformer_stage_service import TransformerStageService


def test_regeneration_includes_proven_karma_disposition():
    checksum = "sha256:" + "a" * 64
    stage = {
        "source_family": "angular-11.x",
        "source_exact": "11.2.14",
        "target_family": "angular-12.x",
        "execution_profile_id": "node-14",
        "package_manager": "npm",
        "resolved_scripts": {"build": "build", "test": "test"},
        "project_targets": {},
        "commands": {"bootstrap_install": [{"runtime_profile_checksum": checksum}]},
        "build_system_decision": {"builder": "@angular-devkit/build-angular:browser"},
        "validation_policy": {"policy_id": "angular-stage-standard-v2"},
        "recovery_policy": {"policy_id": "safe-boundary-v1"},
        "repair_policy": {"policy_id": "proposer-reviewer-human-v1"},
    }
    route = [
        {
            "source_family": f"angular-{major}.x",
            "target_family": f"angular-{major + 1}.x",
            "stage_id": f"angular-{major}-to-{major + 1}",
            "target_angular_exact": "12.2.17" if major == 11 else f"{major + 1}.0.0",
            "target_cli_exact": "12.2.18" if major == 11 else f"{major + 1}.0.0",
        }
        for major in range(11, 21)
    ]
    context = {
        "run": SimpleNamespace(id="run-1"),
        "old_plan": SimpleNamespace(plan={
            "source_exact": "11.2.14", "source_family": "angular-11.x",
            "target_family": "angular-21.x", "catalogue_version": "catalog-v3",
        }),
        "old_stage": SimpleNamespace(stage_plan=stage),
        "checkpoint": SimpleNamespace(workspace_fingerprint="sha256:" + "b" * 64),
        "resolution": SimpleNamespace(package={"route": route}),
        "g05": SimpleNamespace(
            artifact_set_checksum="sha256:" + "c" * 64,
            prerequisite_artifact_ids=[], prerequisite_artifact_checksums={},
        ),
    }
    payload = TransformationReplanRecoveryRequest(
        expected_state_version=10, expected_continuation_state_version=20,
        idempotency_key="recover-1", failed_execution_id="exec-1",
        failed_result_checksum="sha256:" + "d" * 64,
        approved_plan_checksum="sha256:" + "e" * 64,
        approved_stage_plan_checksum="sha256:" + "f" * 64,
    )

    request = TransformationReplanRecoveryService._generation_request(
        context, payload, "operator"
    )
    generated = PlanningApplicationService().generate(request, plan_version=2)

    commands = generated.first_stage_plan.commands["angular_update"]
    karma = [item for item in commands if "devDependencies[karma]=6.4.4" in item.arguments]
    assert len(karma) == 1
    assert karma[0].command_id == "npm-pkg-set"
    assert generated.plan.version == 2
    assert generated.first_stage_plan.plan_version == 2


def test_replan_execution_epoch_scopes_preparation_idempotency():
    run = SimpleNamespace(state_version=12)
    gate = SimpleNamespace(
        artifact_set_checksum="sha256:" + "1" * 64,
        workspace_fingerprint="sha256:" + "2" * 64,
    )
    original = SimpleNamespace(
        id="continuation-1", current_stage_id="stage-1", attempt=0,
        plan_checksum="sha256:" + "3" * 64,
        stage_plan_checksum="sha256:" + "4" * 64,
    )
    regenerated = SimpleNamespace(**{**vars(original), "attempt": 1})

    first = TransformerStageService._request(run, original, gate)
    second = TransformerStageService._request(run, regenerated, gate)

    assert first.idempotency_key == "continuation-1:stage-1:prepare"
    assert second.idempotency_key == "continuation-1:stage-1:replan-1:prepare"


def test_historical_core_migration_version_failure_is_exactly_recognized():
    execution = SimpleNamespace(
        command_id="angular-migrate-only",
        arguments=[
            "C:\\factory\\run_installed_migrations.cjs",
            "@angular/core",
            "11.0.0",
            "12.2.17",
        ],
    )
    failure = (
        "TypeError: Invalid Version: 9-beta\n"
        "at node_modules\\semver\\classes\\semver.js:38\n"
        "at C:\\factory\\run_installed_migrations.cjs:36:50"
    )

    assert (
        TransformationReplanRecoveryService._failure_profile(execution, failure)
        == "angular-core-historical-migration-version"
    )
    execution.arguments[-1] = "12.2.16"
    assert TransformationReplanRecoveryService._failure_profile(execution, failure) is None


def test_angular_eslint_18_parser_guard_failure_is_exactly_recognized():
    execution = SimpleNamespace(
        command_id="angular-migrate-only",
        arguments=[
            "C:\\factory\\run_installed_migrations.cjs",
            "@angular-eslint/schematics",
            "17.0.0",
            "18.4.3",
        ],
    )
    failure = (
        "TypeError: Cannot read properties of undefined (reading 'startsWith')\n"
        "at node_modules\\@angular-eslint\\schematics\\dist\\migrations\\"
        "update-18-2-0\\update-18-2-0.js:13:74"
    )

    assert (
        TransformationReplanRecoveryService._failure_profile(execution, failure)
        == "angular-eslint-18-parser-guard"
    )
    execution.arguments[-1] = "18.4.2"
    assert TransformationReplanRecoveryService._failure_profile(execution, failure) is None


def test_successor_replan_starts_at_the_blocked_stage_and_keeps_remaining_route():
    checksum = "sha256:" + "a" * 64
    route = [
        {
            "source_family": f"angular-{major}.x",
            "target_family": f"angular-{major + 1}.x",
            "stage_id": f"angular-{major}-to-{major + 1}",
            "target_angular_exact": "18.2.14" if major == 17 else f"{major + 1}.0.0",
            "target_cli_exact": "18.2.21" if major == 17 else f"{major + 1}.0.0",
        }
        for major in range(11, 21)
    ]
    context = {
        "run": SimpleNamespace(id="run-1"),
        "old_plan": SimpleNamespace(plan={
            "source_exact": "11.0.4", "source_family": "angular-11.x",
            "target_family": "angular-21.x", "catalogue_version": "catalog-v3",
        }),
        "old_stage": SimpleNamespace(stage_plan={
            "source_family": "angular-17.x", "source_exact": "17.3.12",
            "target_family": "angular-18.x", "execution_profile_id": "node-22",
            "package_manager": "npm", "resolved_scripts": {"build": "build", "test": "test"},
            "project_targets": {},
            "commands": {"bootstrap_install": [{"runtime_profile_checksum": checksum}]},
            "build_system_decision": {"builder": "@angular-devkit/build-angular:browser"},
            "validation_policy": {"policy_id": "angular-stage-standard-v2"},
            "recovery_policy": {"policy_id": "safe-boundary-v1"},
            "repair_policy": {"policy_id": "proposer-reviewer-human-v1"},
        }),
        "checkpoint": SimpleNamespace(workspace_fingerprint="sha256:" + "b" * 64),
        "resolution": SimpleNamespace(package={"route": route}),
        "g05": SimpleNamespace(
            artifact_set_checksum="sha256:" + "c" * 64,
            prerequisite_artifact_ids=[], prerequisite_artifact_checksums={},
        ),
    }
    payload = TransformationReplanRecoveryRequest(
        expected_state_version=10, expected_continuation_state_version=20,
        idempotency_key="recover-successor", failed_execution_id="exec-1",
        failed_result_checksum="sha256:" + "d" * 64,
        approved_plan_checksum="sha256:" + "e" * 64,
        approved_stage_plan_checksum="sha256:" + "f" * 64,
    )

    request = TransformationReplanRecoveryService._generation_request(
        context, payload, "operator"
    )
    generated = PlanningApplicationService().generate(request, plan_version=4)

    assert generated.plan.source_family == "angular-17.x"
    assert len(generated.plan.route) == 4
    assert generated.first_stage_plan.source_exact == "17.3.12"
    assert generated.first_stage_plan.target_exact == "18.2.14"
    assert TransformationReplanRecoveryService._proven_disposition_planned(
        "angular-eslint-18-parser-guard", generated.first_stage_plan
    )
