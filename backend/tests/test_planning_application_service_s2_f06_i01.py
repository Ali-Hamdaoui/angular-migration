from __future__ import annotations

import pytest

from app.domain.command import DEFAULT_COMMAND_TEMPLATES
from app.domain.planning import PlanGenerationRequest
from app.services.planning_application_service import PlanningApplicationError, PlanningApplicationService


def request(**updates) -> PlanGenerationRequest:
    value = dict(
        run_id="run-1", expected_state_version=4, idempotency_key="plan-1", actor="operator",
        source_exact="18.2.13", source_family="angular-18.x", target_family="angular-21.x",
        catalogue_version="catalog-v1", input_fingerprint="sha256:" + "1" * 64,
        execution_profile_id="profile-node22-npm10", execution_profile_checksum="sha256:" + "4" * 64,
        builder="@angular-devkit/build-angular:application",
        resolved_scripts={"build": "build", "test": "test"},
        target_cli_exact="19.2.0",
        stage_route=(("angular-18.x", "angular-19.x", "stage-18-to-19", "19.2.0"), ("angular-19.x", "angular-20.x", "stage-19-to-20", "20.0.0"), ("angular-20.x", "angular-21.x", "stage-20-to-21", "21.0.0")),
    )
    value.update(updates)
    return PlanGenerationRequest(**value)


def test_generates_immutable_plan_and_exact_first_stage_contract():
    result = PlanningApplicationService().generate(request())
    assert result.status == "generated"
    assert result.plan.route == (
        "stage-18-to-19--0754a3f73c516f2f",
        "stage-19-to-20--09fa6cc3c16d9bd0",
        "stage-20-to-21--f1e09ef760f5942b",
    )
    assert result.first_stage_plan.target_exact == "19.2.0"
    assert result.first_stage_plan.commands["angular_update"][0].shell is False
    update = result.first_stage_plan.commands["angular_update"][0]
    assert update.template_id == "tpl-angular-update-exact-v5"
    assert update.template_version == 5
    assert "--allow-dirty" not in update.arguments
    assert "--force" not in update.arguments
    assert "--legacy-peer-deps" not in update.arguments
    assert result.first_stage_plan.forbidden_change_policy.actions
    assert result.plan.checksum.startswith("sha256:")
    assert result.first_stage_plan.checksum.startswith("sha256:")
    assert result.first_stage_plan.commands["lint"] == ()
    assert "installed_migration_fallback" not in result.first_stage_plan.commands
    assert {
        command.runtime_profile_checksum
        for commands in result.first_stage_plan.commands.values()
        for command in commands
    } == {"sha256:" + "4" * 64}


def test_generates_real_angular_11_to_21_route_with_migrate_packages_group():
    route = tuple(
        (f"angular-{major}.x", f"angular-{major + 1}.x", f"angular-{major}-to-{major + 1}", f"{major + 1}.0.0", f"{major + 1}.0.0")
        for major in range(11, 21)
    )

    result = PlanningApplicationService().generate(
        request(
            run_id="run-angular-11-real-facts",
            idempotency_key="plan-angular-11-real-facts",
            source_exact="11.0.4",
            source_family="angular-11.x",
            builder="@angular-devkit/build-angular:browser",
            resolved_scripts={"build": "build", "test": "test", "lint": "lint"},
            project_targets={
                "build": "angular-crud-example:build",
                "test": "angular-crud-example:test",
                "lint": "angular-crud-example:lint",
            },
            target_cli_exact="12.0.0",
            stage_route=route,
            capability_facts=(
                {"key": "package:codelyzer", "value": "present"},
                {"key": "package:tslint", "value": "present"},
                {"key": "package:karma", "value": "present"},
                {"key": "package:karma-jasmine-html-reporter", "value": "present"},
                {"key": "lockfile_format:v1", "value": "present"},
            ),
        )
    )

    assert len(result.plan.route) == 10
    assert [stage.rsplit("--", 1)[0] for stage in result.plan.route] == [
        f"angular-{major}-to-{major + 1}" for major in range(11, 21)
    ]
    assert result.first_stage_plan.source_family == "angular-11.x"
    assert result.first_stage_plan.target_family == "angular-12.x"
    assert result.first_stage_plan.target_exact == "12.0.0"
    assert result.first_stage_plan.target_cli_exact == "12.0.0"
    assert result.first_stage_plan.build_system_decision.builder == "@angular-devkit/build-angular:browser"
    assert set(result.first_stage_plan.commands) >= {
        "bootstrap_install",
        "angular_update",
        "target_version_check",
        "lockfile_generation",
        "final_install",
        "migrate_packages",
        "builds",
        "tests",
        "lint",
    }


def test_stage_knowledge_changes_only_capability_applicable_dispositions():
    legacy = PlanningApplicationService().generate(
        request(
            run_id="run-capabilities-legacy",
            idempotency_key="plan-capabilities-legacy",
            capability_facts=(
                {"key": "package:tslint", "value": "present"},
                {"key": "package:codelyzer", "value": "present"},
                {"key": "lockfile_format:v1", "value": "present"},
            ),
        )
    )
    clean = PlanningApplicationService().generate(
        request(
            run_id="run-capabilities-clean",
            idempotency_key="plan-capabilities-clean",
            capability_facts=({"key": "lockfile_format:v3", "value": "present"},),
        )
    )

    legacy_changes = legacy.first_stage_plan.expected_dependency_changes
    clean_changes = clean.first_stage_plan.expected_dependency_changes
    assert {item["package"] for item in legacy_changes} >= {"tslint", "codelyzer", "package-lock"}
    assert not {"tslint", "codelyzer", "package-lock"} & {item["package"] for item in clean_changes}
    assert legacy.plan.stage_dependency_dispositions
    assert legacy.plan.checksum != clean.plan.checksum


def test_accepts_current_catalogue_version():
    result = PlanningApplicationService().generate(request(catalogue_version="catalog-v3"))
    assert result.status == "generated"


def test_fallback_is_opt_in_and_uses_bounded_installed_migration_command():
    result = PlanningApplicationService().generate(
        request(
            installed_migration_fallback=True,
            capability_facts=({"key": "policy:installed-migration-fallback", "value": "approved"},),
        )
    )
    fallback = result.first_stage_plan.commands["installed_migration_fallback"][0]
    assert fallback.command_id == "angular-migrate-installed"
    assert fallback.executable == "node"
    assert fallback.arguments == (
        "backend/app/command_execution/run_installed_migrations.cjs",
        "@angular/core",
        "18.2.13",
        "19.2.0",
    )
    assert fallback.shell is False


def test_fallback_requires_an_approved_stage_policy():
    with pytest.raises(PlanningApplicationError, match="approved stage-plan policy"):
        PlanningApplicationService().generate(request(installed_migration_fallback=True))


def test_fallback_rejects_unbounded_bindings():
    from app.domain.command import ANGULAR_INSTALLED_MIGRATION_RENDERER

    with pytest.raises(ValueError):
        ANGULAR_INSTALLED_MIGRATION_RENDERER.render_arguments(
            {"package": "../../package.json", "from_version": "18.2.13", "to_version": "19.2.0"}
        )


def test_generates_checksum_bound_lockfile_generation_authority():
    result = PlanningApplicationService().generate(request())

    reference = result.first_stage_plan.commands["lockfile_generation"][0]
    assert reference.command_id == "npm-lockfile-generate"
    assert reference.template_id == "tpl-npm-lockfile-generate"
    assert reference.executable == "npm"
    assert reference.arguments == (
        "install",
        "--package-lock-only",
        "--ignore-scripts",
        "--no-audit",
        "--no-fund",
    )
    assert reference.shell is False
    assert reference.runtime_profile_checksum == "sha256:" + "4" * 64
    assert "npm-lockfile-generate" in {
        template.command_id for template in DEFAULT_COMMAND_TEMPLATES
    }


def test_run_scopes_stage_instance_ids_for_repeated_catalogue_route():
    first = PlanningApplicationService().generate(
        request(run_id="run-alpha", idempotency_key="plan-alpha")
    )
    second = PlanningApplicationService().generate(
        request(run_id="run-beta", idempotency_key="plan-beta")
    )

    assert first.plan.route[0] == "stage-18-to-19--6e0f97f2570683f4"
    assert second.plan.route[0] == "stage-18-to-19--a1afaab0de755ac4"
    assert first.plan.route[0] != second.plan.route[0]
    assert first.first_stage_plan.stage_id == first.plan.route[0]
    assert (
        first.first_stage_plan.commands["angular_update"][0].working_directory_alias
        == "STAGE_WORKSPACE_STAGE_18_TO_19__6E0F97F2570683F4"
    )


def test_generates_lint_only_when_a_lint_script_was_resolved():
    result = PlanningApplicationService().generate(
        request(resolved_scripts={"build": "build", "test": "test", "lint": "lint:app"})
    )

    assert result.first_stage_plan.commands["lint"][0].arguments == ("run", "lint:app")


def test_rejects_missing_required_build_or_test_script():
    with pytest.raises(PlanningApplicationError) as error:
        PlanningApplicationService().generate(request(resolved_scripts={"build": "build"}))

    assert error.value.code == "REQUIRED_SCRIPT_NOT_RESOLVED"


def test_rejects_stale_state_and_does_not_generate():
    service = PlanningApplicationService(state_version_reader=lambda _run_id: 5)
    with pytest.raises(PlanningApplicationError, match="stale") as error:
        service.generate(request())
    assert error.value.code == "STALE_STATE_VERSION"


def test_idempotent_retry_replays_and_payload_mismatch_is_rejected():
    service = PlanningApplicationService()
    first = service.generate(request())
    replay = service.generate(request())
    assert replay.idempotent_replay is True
    assert replay.plan.checksum == first.plan.checksum
    with pytest.raises(PlanningApplicationError) as error:
        service.generate(request(source_exact="18.2.14"))
    assert error.value.code == "IDEMPOTENCY_PAYLOAD_MISMATCH"


def test_rejects_prerequisite_checksum_mismatch():
    service = PlanningApplicationService(artifact_checksum_reader=lambda _artifact_id: "sha256:" + "2" * 64)
    with pytest.raises(PlanningApplicationError) as error:
        service.generate(request(prerequisite_artifacts=({"artifact_id": "artifact-analysis", "checksum": "sha256:" + "3" * 64},)))
    assert error.value.code == "PREREQUISITE_ARTIFACT_CHECKSUM_MISMATCH"


def test_accepts_runtime_profile_identifier_from_execution_profile_service():
    result = PlanningApplicationService().generate(request(execution_profile_id="environment-env-123"))
    assert result.first_stage_plan.execution_profile_id == "environment-env-123"


def test_blocks_unsupported_builder_before_stage_plan_is_returned():
    with pytest.raises(PlanningApplicationError) as error:
        PlanningApplicationService().generate(request(builder="vendor:custom"))
    assert error.value.code == "UNSUPPORTED_BUILD_SYSTEM"


def test_rejects_shell_syntax_in_structured_command_reference():
    with pytest.raises(ValueError, match="shell syntax"):
        request(stage_route=(("angular-18.x", "angular-19.x", "stage-18-to-19;echo", "19.2.0"),))
