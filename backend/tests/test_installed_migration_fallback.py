from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.command_execution.worker import CommandPolicy, CommandPolicyViolation
from app.domain.contracts import CancellationPolicy, CommandRequestDto


def _request(arguments: list[str]) -> CommandRequestDto:
    return CommandRequestDto(
        command_id="angular-migrate-installed",
        run_id="run-installed-fallback",
        stage_id="stage-18-to-19",
        requested_by="transformer",
        requester="transformer",
        executable="node",
        arguments=arguments,
        working_directory_alias="BASELINE_SANDBOX",
        runtime_profile_id="source-runtime-profile",
        timeout_seconds=30,
        network_profile="approved-registries-only",
        cancellation_policy=CancellationPolicy.TERMINATE_PROCESS_TREE,
        idempotency_key="installed-fallback",
        requested_at=datetime.now(UTC),
    )


def test_policy_normalizes_legacy_helper_to_factory_asset(tmp_path: Path):
    policy = CommandPolicy(
        sandbox_root=tmp_path,
        working_directory_aliases={"BASELINE_SANDBOX": tmp_path},
        runtime_profiles=frozenset({"source-runtime-profile"}),
        network_profiles=frozenset({"approved-registries-only"}),
    )
    structured = policy.validate(_request([
        "backend/app/command_execution/run_installed_migrations.cjs",
        "@angular/core",
        "18.2.13",
        "19.2.0",
    ]))
    assert Path(structured.command[1]).resolve() == (
        Path(__file__).resolve().parents[1] / "app" / "command_execution" / "run_installed_migrations.cjs"
    ).resolve()


@pytest.mark.parametrize("helper", ["../run.cjs", "C:/operator/run.cjs", "arbitrary.js"])
def test_policy_rejects_non_factory_helper(helper: str, tmp_path: Path):
    policy = CommandPolicy(
        sandbox_root=tmp_path,
        working_directory_aliases={"BASELINE_SANDBOX": tmp_path},
        runtime_profiles=frozenset({"source-runtime-profile"}),
        network_profiles=frozenset({"approved-registries-only"}),
    )
    with pytest.raises(CommandPolicyViolation, match="Factory-owned asset"):
        policy.validate(_request([helper, "@angular/core", "18.2.13", "19.2.0"]))
