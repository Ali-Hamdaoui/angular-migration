from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.domain.execution_profile import RuntimeCandidate, RuntimeResolutionRequest, SourceRuntimeResolver
from app.domain.planning import PlanGenerationRequest
from app.services.command_executor_service import bind_runtime_executable
from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider
from app.services.planning_application_service import StageExecutionPlanService


def _route(catalogue):
    return tuple(
        (entry.source_family, entry.target_family, entry.stage_id, entry.target_angular_exact, entry.target_cli_exact)
        for entry in catalogue.entries
    )


def _plan_request(**changes):
    catalogue = CompatibilityCatalogueProvider().load("catalog-v3")
    values = dict(
        run_id="angular-11-to-21", expected_state_version=1, idempotency_key="route", actor="operator",
        source_exact="11.0.4", source_family="angular-11.x", target_family="angular-21.x",
        catalogue_version="catalog-v3", input_fingerprint="sha256:" + "1" * 64,
        execution_profile_id="node-12-npm-8", execution_profile_checksum="sha256:" + "2" * 64,
        builder="@angular-devkit/build-angular:browser",
        resolved_scripts={"build": "build", "test": "test", "lint": "lint"},
        stage_route=_route(catalogue), target_cli_exact=catalogue.entries[0].target_cli_exact,
    )
    values.update(changes)
    return PlanGenerationRequest(**values)


def test_catalog_v3_is_the_exact_ten_stage_proven_route_and_v2_remains_loadable():
    provider = CompatibilityCatalogueProvider()
    catalogue = provider.load("catalog-v3")

    assert len(catalogue.entries) == 10
    assert catalogue.entries[0].source_family == "angular-11.x"
    assert catalogue.entries[0].target_angular_exact == "12.2.17"
    assert catalogue.entries[-1].target_angular_exact == "21.2.19"
    assert catalogue.entries[-1].target_cli_exact == "21.2.20"
    assert provider.load("catalog-v2").entry_for("angular-18.x", "angular-19.x").target_angular_exact == "19.0.0"


def test_full_route_is_accepted_while_skip_reverse_and_pre_11_are_rejected():
    request = _plan_request()
    assert len(request.stage_route) == 10

    route = list(request.stage_route)
    route[0] = ("angular-11.x", "angular-13.x", "skip", "13.3.12", "13.3.11")
    with pytest.raises(ValidationError):
        _plan_request(stage_route=tuple(route))
    with pytest.raises(ValidationError):
        _plan_request(source_family="angular-10.x", source_exact="10.2.5")
    with pytest.raises(ValidationError):
        _plan_request(source_family="angular-12.x", target_family="angular-11.x")


def test_angular_11_runtime_policy_resolves_exact_configured_profile():
    candidate = RuntimeCandidate(
        profile_id="node-12-npm-8", node_executable=r"C:\runtime\node.exe", node_exact="12.22.12",
        npm_executable=r"C:\runtime\npm.cmd", npm_exact="8.19.4",
        npx_executable=r"C:\runtime\npx.cmd", npx_exact="8.19.4",
    )
    result = SourceRuntimeResolver().resolve(RuntimeResolutionRequest(
        source_angular_exact="11.0.4", source_typescript_exact="4.0.5", source_rxjs_exact="6.6.3",
        candidates=(candidate,), validated_at=datetime.now(UTC),
    ))

    assert result.status == "resolved"
    assert result.selected_profile.node_executable == candidate.node_executable
    assert result.policy_version == "angular-11-source-runtime-v1"


def test_catalog_v3_stage_plan_has_no_forbidden_bypass_and_uses_installed_migrations():
    plan = StageExecutionPlanService().create(_plan_request())
    commands = plan.commands["angular_update"]
    flattened = [argument for command in commands for argument in command.arguments]

    assert "--force" not in flattened
    assert "--legacy-peer-deps" not in flattened
    assert "--allow-dirty" not in flattened
    lock = next(command for command in commands if command.command_id == "npm-lockfile-generate")
    assert lock.template_version == 2
    assert lock.arguments[0] == "update"
    assert [command.command_id for command in commands].count("angular-migrate-only") == 2
    migrations = [command for command in commands if command.command_id == "angular-migrate-only"]
    karma = next(
        command
        for command in commands
        if "devDependencies[karma]=6.4.4" in command.arguments
    )
    assert karma.command_id == "npm-pkg-set"
    assert all(command.executable == "node" for command in migrations)
    assert all(command.arguments[0].endswith("run_installed_migrations.cjs") for command in migrations)
    assert all(command.runtime_profile_checksum == "sha256:" + "2" * 64 for command in commands)


def test_17_to_18_plan_primes_the_proven_angular_eslint_parser_guard_dependencies():
    catalogue = CompatibilityCatalogueProvider().load("catalog-v3")
    route = _route(catalogue)[6:]
    plan = StageExecutionPlanService().create(_plan_request(
        source_exact="17.3.12",
        source_family="angular-17.x",
        stage_route=route,
        target_cli_exact="18.2.21",
    ))
    arguments = {
        argument
        for command in plan.commands["angular_update"]
        if command.command_id == "npm-pkg-set"
        for argument in command.arguments
    }

    assert "devDependencies[@typescript-eslint/eslint-plugin]=^7.2.0" in arguments
    assert "devDependencies[@typescript-eslint/parser]=^7.2.0" in arguments
    assert "devDependencies[eslint]=^8.57.0" in arguments


def test_selected_runtime_executable_replaces_ambient_alias(tmp_path):
    selected = tmp_path / "approved" / "npm.cmd"
    selected.parent.mkdir()
    selected.write_text("@echo approved", encoding="utf-8")

    assert bind_runtime_executable("npm", {"package_manager_executable": str(selected)}) == str(selected.resolve())
    assert bind_runtime_executable("git", {"package_manager_executable": str(selected)}) == "git"
