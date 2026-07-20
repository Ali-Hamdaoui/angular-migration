from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.command_execution.worker import CommandDefinition, CommandPolicy, CommandPolicyViolation, CommandRegistry
from app.domain.contracts import CancellationPolicy, CommandRequestDto


def _request(arguments, *, command_id="angular-update"):
    return CommandRequestDto(
        command_id=command_id,
        run_id="run-1",
        stage_id="stage-1",
        executable="npx",
        arguments=arguments,
        working_directory_alias="STAGE_SANDBOX",
        runtime_profile_id="profile-1",
        cancellation_policy=CancellationPolicy.TERMINATE_PROCESS_TREE,
        idempotency_key="key-1",
        requested_at=datetime.now(UTC),
    )


def _angular_registry() -> CommandRegistry:
    return CommandRegistry(definitions=(
        CommandDefinition("python-version", "python", ("--version",), ("python.exe", "py", "py.exe")),
        CommandDefinition("angular-update", "npx", ("--no-install", "ng", "update", "@angular/core@18.2.0", "@angular/cli@18.2.0"), ("npx.cmd",)),
        CommandDefinition("angular-version", "npx", ("ng", "version"), ("npx.cmd",)),
        CommandDefinition("angular-dependency-tree", "npm", ("ls", "--json", "--depth=0"), ("npm.cmd",)),
    ))


def _policy(tmp_path: Path):
    sandbox = tmp_path / "stage"
    sandbox.mkdir()
    return CommandPolicy(
        sandbox_root=tmp_path,
        registry=_angular_registry(),
        working_directory_aliases={"STAGE_SANDBOX": sandbox},
        runtime_profiles=frozenset({"profile-1"}),
    )


def test_angular_update_accepts_exact_local_cli_shape(tmp_path):
    request = _request(["--no-install", "ng", "update", "@angular/core@18.2.0", "@angular/cli@18.2.0"])
    assert _policy(tmp_path).validate(request).command == ("npx", *request.arguments)


@pytest.mark.parametrize("flag", ["--force", "--legacy-peer-deps", "--migrate-only", "--from=17.0.0", "--to=18.2.0"])
def test_angular_update_rejects_forbidden_or_legacy_shape(tmp_path, flag):
    request = _request(["--no-install", "ng", "update", "@angular/core@18.2.0", "@angular/cli@18.2.0", flag])
    with pytest.raises(CommandPolicyViolation):
        _policy(tmp_path).validate(request)


def test_angular_version_is_registered_as_local_cli_check(tmp_path):
    request = _request(["ng", "version"], command_id="angular-version")
    assert _policy(tmp_path).validate(request).command == ("npx", "ng", "version")
