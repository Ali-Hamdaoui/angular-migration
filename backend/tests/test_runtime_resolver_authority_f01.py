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


def _managed_bundle(tmp_path: Path, name: str, versions: dict[str, str]) -> Path:
    bundle = tmp_path / name
    bundle.mkdir()
    for executable, version in versions.items():
        (bundle / executable).write_text(version, encoding="utf-8")
    return bundle


def test_discover_managed_bundle_layout(tmp_path: Path):
    bundle = _managed_bundle(
        tmp_path,
        "node12-npm8",
        {"node.exe": "12.22.12", "npm.cmd": "8.19.4", "npx.cmd": "8.19.4"},
    )

    def probe(path: Path) -> str:
        return {"node.exe": "12.22.12", "npm.cmd": "8.19.4", "npx.cmd": "8.19.4"}[path.name]

    found = RuntimeResolverAuthority(
        RuntimeMatrix(node_install_root=tmp_path, angular_cli_root=tmp_path),
        probe=probe,
        now_provider=lambda: NOW,
    ).discover()

    assert {(item.kind, item.runtime_id, item.source, item.installation_variant, item.installation_root) for item in found} == {
        (RuntimeExecutableKind.NODE, "node12", "managed-bundle", "node12-npm8", str(bundle)),
        (RuntimeExecutableKind.NPM, "node12", "managed-bundle", "node12-npm8", str(bundle)),
        (RuntimeExecutableKind.NPX, "node12", "managed-bundle", "node12-npm8", str(bundle)),
    }


def test_managed_bundle_resolves_paired_candidate(tmp_path: Path):
    _managed_bundle(
        tmp_path,
        "node12-npm8",
        {"node.exe": "12.22.12", "npm.cmd": "8.19.4", "npx.cmd": "8.19.4"},
    )

    def probe(path: Path) -> str:
        return {"node.exe": "12.22.12", "npm.cmd": "8.19.4", "npx.cmd": "8.19.4"}[path.name]

    resolver = RuntimeResolverAuthority(
        RuntimeMatrix(node_install_root=tmp_path, angular_cli_root=tmp_path),
        probe=probe,
        now_provider=lambda: NOW,
    )
    bindings = resolver.resolve(
        [
            RuntimeRequirement(kind=RuntimeExecutableKind.NODE, runtime_id="node12", version_exact="12.22.12"),
            RuntimeRequirement(kind=RuntimeExecutableKind.NPM, runtime_id="node12", version_exact="8.19.4"),
            RuntimeRequirement(kind=RuntimeExecutableKind.NPX, runtime_id="node12", version_exact="8.19.4"),
        ]
    )

    assert all(binding.descriptor is not None for binding in bindings)
    assert {binding.descriptor.version_exact for binding in bindings} == {"12.22.12", "8.19.4"}
    assert len({binding.descriptor.installation_root for binding in bindings}) == 1
    assert all(binding.descriptor.installation_variant == "node12-npm8" for binding in bindings)


def test_two_managed_bundles_same_major_never_mix_installations(tmp_path: Path):
    _managed_bundle(
        tmp_path,
        "node12-npm8",
        {"node.exe": "12.22.12", "npm.cmd": "8.19.4", "npx.cmd": "8.19.4"},
    )
    _managed_bundle(
        tmp_path,
        "node12-npm10",
        {"node.exe": "12.22.12", "npm.cmd": "10.3.1", "npx.cmd": "10.3.1"},
    )

    def probe(path: Path) -> str:
        return {
            ("node12-npm8", "node.exe"): "12.22.12",
            ("node12-npm8", "npm.cmd"): "8.19.4",
            ("node12-npm8", "npx.cmd"): "8.19.4",
            ("node12-npm10", "node.exe"): "12.22.12",
            ("node12-npm10", "npm.cmd"): "10.3.1",
            ("node12-npm10", "npx.cmd"): "10.3.1",
        }[(path.parent.name, path.name)]

    resolver = RuntimeResolverAuthority(
        RuntimeMatrix(node_install_root=tmp_path, angular_cli_root=tmp_path),
        probe=probe,
        now_provider=lambda: NOW,
    )
    found = resolver.discover()
    assert {(item.runtime_id, item.installation_variant) for item in found} == {
        ("node12", "node12-npm8"),
        ("node12", "node12-npm10"),
    }

    bindings = resolver.resolve(
        [
            RuntimeRequirement(kind=RuntimeExecutableKind.NODE, runtime_id="node12", version_exact="12.22.12"),
            RuntimeRequirement(kind=RuntimeExecutableKind.NPM, runtime_id="node12", version_exact="8.19.4"),
            RuntimeRequirement(kind=RuntimeExecutableKind.NPX, runtime_id="node12", version_exact="8.19.4"),
        ]
    )
    assert all(binding.descriptor is not None for binding in bindings)
    assert all(binding.descriptor.installation_variant == "node12-npm8" for binding in bindings)
    assert len({binding.descriptor.installation_root for binding in bindings}) == 1


def test_real_managed_bundle_layout_executes_without_path_dependency(tmp_path: Path):
    """Prove runtime selection is independent from the developer machine PATH."""
    bundle = tmp_path / "node12-npm8"
    (bundle / "node_modules" / "npm" / "bin").mkdir(parents=True)
    (bundle / "node.exe").write_text("node", encoding="utf-8")
    (bundle / "npm.cmd").write_text('"%~dp0node.exe" "%~dp0node_modules\\npm\\bin\\npm-cli.js" %*', encoding="utf-8")
    (bundle / "npx.cmd").write_text('"%~dp0node.exe" "%~dp0node_modules\\npm\\bin\\npx-cli.js" %*', encoding="utf-8")
    (bundle / "node_modules" / "npm" / "bin" / "npm-cli.js").write_text("// npm cli", encoding="utf-8")

    def probe(path: Path) -> str:
        return {"node.exe": "12.22.12", "npm.cmd": "8.19.4", "npx.cmd": "8.19.4"}[path.name]

    resolver = RuntimeResolverAuthority(
        RuntimeMatrix(node_install_root=tmp_path, angular_cli_root=tmp_path),
        probe=probe,
        now_provider=lambda: NOW,
    )
    bindings = resolver.resolve(
        [
            RuntimeRequirement(kind=RuntimeExecutableKind.NODE, runtime_id="node12", version_exact="12.22.12"),
            RuntimeRequirement(kind=RuntimeExecutableKind.NPM, runtime_id="node12", version_exact="8.19.4"),
            RuntimeRequirement(kind=RuntimeExecutableKind.NPX, runtime_id="node12", version_exact="8.19.4"),
        ]
    )

    assert all(binding.descriptor is not None for binding in bindings)
    assert {binding.descriptor.version_exact for binding in bindings} == {"12.22.12", "8.19.4"}
    assert len({binding.descriptor.installation_root for binding in bindings}) == 1
    assert all(binding.descriptor.installation_variant == "node12-npm8" for binding in bindings)
    assert all(binding.descriptor.source == "managed-bundle" for binding in bindings)
    assert all(str(bundle) in binding.descriptor.resolved_path for binding in bindings)


def test_legacy_nvm_layout_still_resolves(tmp_path: Path):
    _managed_bundle(
        tmp_path,
        "v12.22.12",
        {"node.exe": "12.22.12", "npm.cmd": "8.19.4", "npx.cmd": "8.19.4"},
    )

    def probe(path: Path) -> str:
        return {"node.exe": "12.22.12", "npm.cmd": "8.19.4", "npx.cmd": "8.19.4"}[path.name]

    resolver = RuntimeResolverAuthority(
        RuntimeMatrix(node_install_root=tmp_path, angular_cli_root=tmp_path),
        probe=probe,
        now_provider=lambda: NOW,
    )
    found = resolver.discover()

    assert {(item.kind, item.source, item.runtime_id) for item in found} == {
        (RuntimeExecutableKind.NODE, "nvm", "v12.22.12"),
        (RuntimeExecutableKind.NPM, "nvm", "v12.22.12"),
        (RuntimeExecutableKind.NPX, "nvm", "v12.22.12"),
    }
    assert all(item.installation_variant is None for item in found)
    bindings = resolver.resolve(
        [
            RuntimeRequirement(kind=RuntimeExecutableKind.NODE, runtime_id="v12.22.12", version_exact="12.22.12"),
            RuntimeRequirement(kind=RuntimeExecutableKind.NPM, runtime_id="v12.22.12", version_exact="8.19.4"),
            RuntimeRequirement(kind=RuntimeExecutableKind.NPX, runtime_id="v12.22.12", version_exact="8.19.4"),
        ]
    )
    assert all(binding.descriptor is not None for binding in bindings)


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


def test_grouped_runtime_resolution_never_mixes_installations(monkeypatch):
    resolver = authority()
    monkeypatch.setattr(
        resolver,
        "discover",
        lambda: [
            descriptor(RuntimeExecutableKind.NODE, runtime_id="v18.20.8", version_exact="18.20.8"),
            descriptor(RuntimeExecutableKind.NPM, runtime_id="v20.20.2", version_exact="10.8.2"),
            descriptor(RuntimeExecutableKind.NPX, runtime_id="v20.20.2", version_exact="10.8.2"),
        ],
    )
    bindings = resolver.resolve([
        RuntimeRequirement(kind=RuntimeExecutableKind.NODE, runtime_id="angular-stage-runtime", minimum_version="18.0.0"),
        RuntimeRequirement(kind=RuntimeExecutableKind.NPM, runtime_id="angular-stage-runtime", minimum_version="10.0.0"),
        RuntimeRequirement(kind=RuntimeExecutableKind.NPX, runtime_id="angular-stage-runtime", minimum_version="10.0.0"),
    ])
    assert all(binding.descriptor is None for binding in bindings)


def test_runtime_candidate_ordering_is_semantic(monkeypatch):
    resolver = authority()
    monkeypatch.setattr(
        resolver,
        "discover",
        lambda: [
            descriptor(runtime_id="v9.9.9", version_exact="9.9.9"),
            descriptor(runtime_id="v12.0.0", version_exact="12.0.0"),
            descriptor(runtime_id="v20.0.0", version_exact="20.0.0"),
        ],
    )
    binding = resolver.resolve([
        RuntimeRequirement(kind=RuntimeExecutableKind.NODE, runtime_id="angular-stage-runtime", minimum_version="9.0.0")
    ])[0]
    assert binding.descriptor is not None
    assert binding.descriptor.version_exact == "20.0.0"


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
        "node_exact": "12.22.12",
        "package_manager": "npm",
        "package_manager_executable": "npm",
        "package_manager_exact": "8.19.4",
        "npx_executable": "npx",
        "npx_exact": "8.19.4",
        "environment_allowlist": ["PATH"],
    }
    bindings = _runtime_bindings_from_profile(profile)
    assert set(bindings) == {"node", "npm", "npx"}
    assert bindings["node"].runtime_id == "node12"
    assert bindings["npm"].runtime_id == "node12"
    assert bindings["npm"].version_exact == "8.19.4"
    assert bindings["npx"].runtime_id == "node12"


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
