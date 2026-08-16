"""Tests for F01-02 PATH-independent resolver authority and F01-03 fail-closed guard."""

import dataclasses
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.artifact_store import LocalFilesystemArtifactStore
from app.command_execution.worker import (
    CommandLogWriter,
    CommandPolicy,
    CommandPolicyViolation,
    ExecutionWorker,
    WorkerSupervisor,
)
from app.domain.contracts import CancellationPolicy, CommandRequestDto, CommandStatus
from app.domain.runtime_execution import (
    RuntimeExecutableDescriptor,
    RuntimeExecutableKind,
    RuntimeRequirement,
)
from app.services.runtime_resolver_authority import (
    RuntimeMatrix,
    RuntimeResolverAuthority,
    sha256_of,
)

NOW = datetime(2026, 8, 15, tzinfo=UTC)
NVM_ROOT = Path.home() / ".nvm" / "versions" / "node"


def make_matrix() -> RuntimeMatrix:
    return RuntimeMatrix(node_install_root=NVM_ROOT, angular_cli_root=Path.home() / "migration-lab" / "runtimes")


def static_probe(path: Path) -> str | None:
    text = path.read_text(errors="ignore")
    if path.name == "node":
        return "18.20.8"
    if path.name in {"npm", "npx"}:
        return "10.8.2"
    return None


def authority() -> RuntimeResolverAuthority:
    return RuntimeResolverAuthority(make_matrix(), probe=static_probe, now_provider=lambda: NOW)


def descriptor(kind=RuntimeExecutableKind.NODE, **changes) -> RuntimeExecutableDescriptor:
    values = {
        "kind": kind,
        "executable_name": kind.value,
        "resolved_path": str(NVM_ROOT / "v18.20.8" / "bin" / kind.value),
        "version_exact": "18.20.8",
        "sha256": "a" * 64,
        "operating_system": "linux",
        "architecture": "amd64",
        "installation_root": str(NVM_ROOT / "v18.20.8"),
        "source": "nvm",
        "runtime_id": "v18.20.8",
        "probed_at": NOW,
    }
    values.update(changes)
    return RuntimeExecutableDescriptor(**values)


def test_discover_enumerates_runtime_matrix():
    found = authority().discover()
    assert {item.kind for item in found} == {RuntimeExecutableKind.NODE, RuntimeExecutableKind.NPM, RuntimeExecutableKind.NPX}
    assert all(item.resolved_path.startswith(str(NVM_ROOT)) for item in found)
    assert all(len(item.sha256) == 64 for item in found)


def test_discover_enumerates_windows_nvm_layout(tmp_path: Path):
    version_dir = tmp_path / "v22.23.1"
    version_dir.mkdir()
    for name in ("node.exe", "npm.cmd", "npx.cmd"):
        (version_dir / name).write_text(name, encoding="utf-8")

    def probe(path: Path) -> str:
        return {"node.exe": "22.23.1", "npm.cmd": "10.9.8", "npx.cmd": "10.9.8"}[path.name]

    found = RuntimeResolverAuthority(
        RuntimeMatrix(node_install_root=tmp_path, angular_cli_root=tmp_path),
        probe=probe,
        now_provider=lambda: NOW,
    ).discover()

    assert {(item.kind, Path(item.resolved_path).name) for item in found} == {
        (RuntimeExecutableKind.NODE, "node.exe"),
        (RuntimeExecutableKind.NPM, "npm.cmd"),
        (RuntimeExecutableKind.NPX, "npx.cmd"),
    }


def test_resolve_exact_node_version_is_path_independent():
    bindings = authority().resolve(
        [RuntimeRequirement(kind=RuntimeExecutableKind.NODE, runtime_id="node18", version_exact="18.20.8")]
    )
    assert len(bindings) == 1
    assert bindings[0].descriptor is not None
    assert bindings[0].descriptor.runtime_id == "v18.20.8"


def test_resolve_pairs_npm_npx_with_named_install():
    resolver = authority()
    bindings = resolver.resolve(
        [
            RuntimeRequirement(kind=RuntimeExecutableKind.NODE, runtime_id="node18", version_exact="18.20.8"),
            RuntimeRequirement(kind=RuntimeExecutableKind.NPM, runtime_id="node18", minimum_version="9.0.0"),
            RuntimeRequirement(kind=RuntimeExecutableKind.NPX, runtime_id="node18", minimum_version="9.0.0"),
        ]
    )
    installs = {b.descriptor.runtime_id for b in bindings}
    assert installs == {"v18.20.8"}


def test_resolve_unknown_version_blocked_without_payload():
    bindings = authority().resolve(
        [RuntimeRequirement(kind=RuntimeExecutableKind.NODE, runtime_id="node99", version_exact="99.0.0")]
    )
    assert bindings[0].descriptor is None
    assert bindings[0].blocked_reason is not None


def test_resolution_is_deterministic():
    first = authority().resolve([RuntimeRequirement(kind=RuntimeExecutableKind.NODE, runtime_id="node18", version_exact="18.20.8")])
    second = authority().resolve([RuntimeRequirement(kind=RuntimeExecutableKind.NODE, runtime_id="node18", version_exact="18.20.8")])
    assert first[0].descriptor.model_dump() == second[0].descriptor.model_dump()


# --- F01-03 fail-closed guard -------------------------------------------------

def make_worker(policy: CommandPolicy) -> ExecutionWorker:
    return ExecutionWorker(policy, CommandLogWriter(LocalFilesystemArtifactStore(Path(tempfile.mkdtemp()))), supervisor=WorkerSupervisor())


def node_version_request() -> CommandRequestDto:
    return CommandRequestDto(
        command_id="node-version",
        run_id="guard-test",
        requester="test",
        executable="node",
        arguments=["--version"],
        shell=False,
        working_directory_alias="run_workspace",
        runtime_profile_id="source-runtime-profile",
        timeout_seconds=10,
        network_profile="none",
        cancellation_policy=CancellationPolicy.TERMINATE_PROCESS_TREE,
        idempotency_key="guard:node-version",
        requested_at=NOW,
    )


def test_guard_rejects_checksum_mismatch_fail_closed():
    binding = descriptor(sha256="f" * 64)
    with tempfile.TemporaryDirectory() as tmp:
        sandbox = Path(tmp)
        policy = CommandPolicy(
            sandbox_root=sandbox,
            working_directory_aliases={"run_workspace": sandbox},
            runtime_bindings={"node": binding},
        )
        worker = make_worker(policy)
        result = worker.run(node_version_request())
        assert result.result.status is CommandStatus.REJECTED
        assert result.stderr_artifact is not None
        assert "RUNTIME_EXECUTABLE_CHECKSUM_MISMATCH" in result.stderr_artifact.content


def test_guard_runs_bound_executable_when_checksum_matches():
    real = next(item for item in authority().discover() if item.kind is RuntimeExecutableKind.NODE and item.runtime_id == "v18.20.8")
    with tempfile.TemporaryDirectory() as tmp:
        sandbox = Path(tmp)
        policy = CommandPolicy(
            sandbox_root=sandbox,
            working_directory_aliases={"run_workspace": sandbox},
            runtime_bindings={"node": real},
        )
        worker = make_worker(policy)
        result = worker.run(node_version_request())
        assert result.result.status is CommandStatus.SUCCEEDED
        assert result.stdout_artifact is not None
        assert result.stdout_artifact.content.strip() == "v18.20.8"


def test_guard_accepts_absolute_path_binding():
    real = next(item for item in authority().discover() if item.kind is RuntimeExecutableKind.NODE and item.runtime_id == "v18.20.8")
    with tempfile.TemporaryDirectory() as tmp:
        sandbox = Path(tmp)
        policy = CommandPolicy(
            sandbox_root=sandbox,
            working_directory_aliases={"run_workspace": sandbox},
            runtime_bindings={"node": real},
        )
        request = node_version_request()
        request = request.model_copy(update={"executable": real.resolved_path})
        worker = make_worker(policy)
        result = worker.run(request)
        assert result.result.status is CommandStatus.SUCCEEDED


def test_policy_rejects_probe_outside_runtime_roots():
    with tempfile.TemporaryDirectory() as tmp:
        sandbox = Path(tmp)
        rogue = sandbox / "node"
        rogue.write_text("#!/bin/sh\necho fake\n")
        rogue.chmod(0o755)
        policy = CommandPolicy(
            sandbox_root=sandbox,
            working_directory_aliases={"run_workspace": sandbox},
            runtime_probe_roots=frozenset({NVM_ROOT}),
        )
        request = CommandRequestDto(
            command_id="runtime-executable-probe",
            run_id="probe-test",
            requester="test",
            executable=str(rogue),
            arguments=["--version"],
            shell=False,
            working_directory_alias="run_workspace",
            runtime_profile_id="source-runtime-profile",
            timeout_seconds=10,
            network_profile="none",
            cancellation_policy=CancellationPolicy.TERMINATE_PROCESS_TREE,
            idempotency_key="probe:rogue",
            requested_at=NOW,
        )
        with pytest.raises(CommandPolicyViolation, match="outside the configured runtime roots"):
            policy.validate(request)


def test_probe_allowed_inside_runtime_roots():
    real = next(item for item in authority().discover() if item.kind is RuntimeExecutableKind.NODE and item.runtime_id == "v18.20.8")
    with tempfile.TemporaryDirectory() as tmp:
        sandbox = Path(tmp)
        policy = CommandPolicy(
            sandbox_root=sandbox,
            working_directory_aliases={"run_workspace": sandbox},
            runtime_probe_roots=frozenset({NVM_ROOT}),
        )
        request = CommandRequestDto(
            command_id="runtime-executable-probe",
            run_id="probe-test",
            requester="test",
            executable=real.resolved_path,
            arguments=["--version"],
            shell=False,
            working_directory_alias="run_workspace",
            runtime_profile_id="source-runtime-profile",
            timeout_seconds=10,
            network_profile="none",
            cancellation_policy=CancellationPolicy.TERMINATE_PROCESS_TREE,
            idempotency_key="probe:real",
            requested_at=NOW,
        )
        structured = policy.validate(request)
        assert structured.command[0] == real.resolved_path


def test_supervisor_fails_closed_on_path_swap():
    real = next(item for item in authority().discover() if item.kind is RuntimeExecutableKind.NODE and item.runtime_id == "v18.20.8")
    sandbox = Path(tempfile.mkdtemp())
    from app.command_execution.worker import StructuredCommandRequest
    from app.domain.contracts import CommandRequestDto

    request = node_version_request().model_copy(update={"executable": real.resolved_path})
    structured = StructuredCommandRequest(
        dto=request,
        definition=None,
        command=(real.resolved_path, "--version"),
        working_directory=sandbox,
        runtime_bindings={"node": real.model_copy(update={"sha256": "0" * 64})},
    )
    with pytest.raises(OSError, match="RUNTIME_EXECUTABLE_CHECKSUM_MISMATCH"):
        WorkerSupervisor()._verify_bound_executable(structured)
    # path swap fails closed too
    other_node = str(NVM_ROOT / "v20.20.2" / "bin" / "node")
    swapped = dataclasses.replace(structured, command=(other_node, "--version"))
    with pytest.raises(OSError, match="RUNTIME_BINDING_PATH_MISMATCH"):
        WorkerSupervisor()._verify_bound_executable(swapped)


def test_sha256_helper_reads_resolved_target():
    digest = sha256_of(NVM_ROOT / "v18.20.8" / "bin" / "node")
    assert len(digest) == 64


# --- F01-03/04 integration: profile -> binding -> policy seam -----------------

def test_runtime_bindings_from_real_serialized_profile():
    """A real ExecutionProfile.model_dump() payload must bind cleanly (npm uses package_manager_exact)."""
    from app.services.command_executor_service import _runtime_bindings_from_profile

    profile = {
        "profile_id": "profile-1",
        "checksum": "sha256:runtime",
        "node_executable": "node",
        "node_exact": "18.20.8",
        "package_manager": "npm",
        "package_manager_executable": "npm",
        "package_manager_exact": "10.8.2",
        "npx_executable": "npx",
        "npx_exact": "10.8.2",
        "environment_allowlist": ["PATH"],
    }
    bindings = _runtime_bindings_from_profile(profile)
    assert set(bindings) == {"node", "npm", "npx"}
    assert bindings["node"].runtime_id == "v18.20.8"
    assert bindings["npm"].runtime_id == "v18.20.8"
    assert bindings["npm"].version_exact == "10.8.2"
    assert bindings["npx"].runtime_id == "v18.20.8"


def test_runtime_bindings_legacy_profile_without_node_exact_returns_empty():
    """A profile without an explicit node version keeps legacy resolution behavior."""
    from app.services.command_executor_service import _runtime_bindings_from_profile

    assert _runtime_bindings_from_profile({"node_executable": "node"}) == {}


def test_runtime_bindings_fail_closed_on_unbindable_declared_runtime():
    """A profile that declares a runtime absent from the matrix must fail closed."""
    from app.services.command_executor_service import (
        CommandExecutorError,
        _runtime_bindings_from_profile,
    )

    profile = {
        "node_exact": "99.99.99",
        "package_manager_exact": "99.0.0",
        "npx_exact": "99.0.0",
    }
    with pytest.raises(CommandExecutorError) as exc:
        _runtime_bindings_from_profile(profile)
    assert exc.value.code == "EXECUTION_PROFILE_RUNTIME_UNBINDABLE"
