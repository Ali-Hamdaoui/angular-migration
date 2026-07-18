from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from app.artifact_store import LocalFilesystemArtifactStore
from app.core.config import Settings
from app.domain.contracts import CommandStatus
from app.services.environment_capability_service import EnvironmentCapabilityService


class FakeWorker:
    def __init__(self, failures: dict[str, str] | None = None):
        self.requests = []
        self.failures = failures or {}

    def run(self, request):
        self.requests.append(request)
        failure = self.failures.get(request.command_id)
        if failure:
            return SimpleNamespace(
                result=SimpleNamespace(status=CommandStatus.FAILED),
                stdout_artifact=None,
                stderr_artifact=SimpleNamespace(content=failure),
            )
        return SimpleNamespace(
            result=SimpleNamespace(status=CommandStatus.SUCCEEDED),
            stdout_artifact=SimpleNamespace(content=f"{request.command_id} 1.2.3\n"),
            stderr_artifact=None,
        )


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'state.db'}",
        artifact_root=tmp_path / "runs",
        workspace_root=tmp_path / "workspaces",
        snapshot_root=tmp_path / "snapshots",
        delivery_root=tmp_path / "delivery",
        sandbox_root=tmp_path / "sandboxes",
        allowed_source_roots=[tmp_path / "source"],
        allowed_target_roots=[tmp_path / "target"],
        minimum_free_disk_bytes=0,
    )


def make_service(
    tmp_path: Path,
    locations: dict[str, Path],
    *,
    failures: dict[str, str] | None = None,
    is_windows: bool = False,
) -> tuple[EnvironmentCapabilityService, FakeWorker]:
    worker = FakeWorker(failures)
    service = EnvironmentCapabilityService(
        make_settings(tmp_path),
        worker,
        LocalFilesystemArtifactStore(tmp_path / "artifact-store"),
        which=lambda name: str(locations[name]) if name in locations else None,
        now_provider=lambda: datetime(2026, 7, 14, tzinfo=UTC),
        is_windows=is_windows,
    )
    return service, worker


def test_diagnose_reports_paired_runtimes_and_persists_redacted_artifacts(tmp_path, monkeypatch):
    root = tmp_path / "nodejs"
    locations = {name: root / f"{name}.exe" for name in ("node", "npm", "npx", "git", "python")}
    monkeypatch.setenv("NPM_CONFIG_REGISTRY", "https://registry.example.invalid")
    monkeypatch.setenv("HTTP_PROXY", "http://user:secret@proxy.example.invalid:8080")
    monkeypatch.setenv("HTTPS_PROXY", "https://user:secret@proxy.example.invalid:8443")
    monkeypatch.setenv("NPM_CONFIG_STRICT_SSL", "true")
    monkeypatch.setenv("NODE_EXTRA_CA_CERTS", str(tmp_path / "corp-ca.pem"))

    service, worker = make_service(tmp_path, locations)
    result = service.diagnose("test-refresh")

    assert result.snapshot.status == "available"
    assert result.snapshot.node_npm_npx_paired is True
    assert result.snapshot.git_ready is True
    assert result.snapshot.python_ready is True
    assert result.snapshot.network.proxy_configured is True
    assert result.snapshot.network.custom_ca_configured is True
    assert len(worker.requests) == 5
    assert result.artifact is not None
    assert "secret" not in result.snapshot.model_dump_json()
    assert result.snapshot.checksum
    assert result.artifact["summary"].startswith("artifact-")


def test_diagnose_blocks_mixed_node_npm_npx_installation_roots(tmp_path, monkeypatch):
    root = tmp_path / "nodejs"
    other_root = tmp_path / "other-nodejs"
    locations = {
        "node": root / "node.exe",
        "npm": other_root / "npm.cmd",
        "npx": root / "npx.cmd",
        "git": root / "git.exe",
        "python": root / "python.exe",
    }
    monkeypatch.setenv("NPM_CONFIG_REGISTRY", "https://registry.example.invalid")

    service, _ = make_service(tmp_path, locations)
    result = service.diagnose("mismatch-refresh")

    assert result.snapshot.status == "blocked"
    assert result.snapshot.node_npm_npx_paired is False
    assert "RUNTIME_PAIR_MISMATCH" in result.snapshot.blockers


def test_diagnose_reports_missing_worker_runtime_and_rejects_blank_idempotency(tmp_path):
    service, _ = make_service(tmp_path, {})

    result = service.diagnose("missing-refresh")

    assert result.snapshot.status == "blocked"
    assert "RUNTIME_NODE_NPM_NPX_UNAVAILABLE" in result.snapshot.blockers
    assert "GIT_UNAVAILABLE" in result.snapshot.blockers
    assert "PYTHON_WORKER_UNAVAILABLE" in result.snapshot.blockers

    try:
        service.diagnose(" ")
    except ValueError as exc:
        assert "idempotency_key" in str(exc)
    else:
        raise AssertionError("blank idempotency key must be rejected")


def test_windows_discovery_uses_executable_extensions_and_py_fallback(tmp_path, monkeypatch):
    root = tmp_path / "nodejs"
    locations = {
        "node.exe": root / "node.exe",
        "npm.cmd": root / "npm.cmd",
        "npx.cmd": root / "npx.cmd",
        "git.exe": root / "git.exe",
        "py": tmp_path / "python" / "py.exe",
    }
    monkeypatch.setenv("NPM_CONFIG_REGISTRY", "https://registry.example.invalid")

    service, worker = make_service(tmp_path, locations, is_windows=True)
    result = service.diagnose("windows-refresh")

    assert result.snapshot.status == "available"
    assert [request.executable for request in worker.requests] == ["node.exe", "npm.cmd", "npx.cmd", "git.exe", "py"]
    assert result.snapshot.runtimes[-1].executable == str(locations["py"])
    assert result.snapshot.runtimes[-1].attempted_executable == "py"


def test_missing_windows_tools_include_attempt_and_remediation(tmp_path):
    service, _ = make_service(tmp_path, {}, is_windows=True)

    result = service.diagnose("missing-windows-tools")
    runtimes = {runtime.name: runtime for runtime in result.snapshot.runtimes}

    assert runtimes["npm"].attempted_executable == "npm.cmd"
    assert runtimes["npm"].reason == "The executable was not found in the backend process PATH."
    assert "restart the backend" in runtimes["npm"].remediation
    assert runtimes["python"].attempted_executable == "python.exe"
    assert "py launcher" in runtimes["python"].remediation
    assert len(result.snapshot.blockers) == 3


def test_failed_version_probe_keeps_executor_detail_and_blocks_readiness(tmp_path, monkeypatch):
    root = tmp_path / "tools"
    locations = {
        "node.exe": root / "node.exe",
        "npm.cmd": root / "npm.cmd",
        "npx.cmd": root / "npx.cmd",
        "git.exe": root / "git.exe",
        "python.exe": root / "python.exe",
    }
    monkeypatch.setenv("NPM_CONFIG_REGISTRY", "https://registry.example.invalid")

    service, _ = make_service(
        tmp_path,
        locations,
        failures={"git-version": "Access is denied"},
        is_windows=True,
    )
    result = service.diagnose("failed-git-probe")
    git = next(runtime for runtime in result.snapshot.runtimes if runtime.name == "git")

    assert git.status == "failed"
    assert git.attempted_executable == "git.exe"
    assert git.reason == "The authoritative version probe failed: Access is denied"
    assert "captured command stderr" in git.remediation
    assert result.snapshot.status == "blocked"
    assert result.snapshot.blockers == ["GIT_UNAVAILABLE"]
