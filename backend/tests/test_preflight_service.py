"""Tests for AMF-S0-13 runtime preflight validation."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from app.artifact_store import LocalFilesystemArtifactStore
from app.core.config import Settings
from app.domain.contracts import CommandResultDto, CommandStatus, PreflightRequestDto
from app.preflight import PreflightService


class FakeWorker:
    def __init__(self, statuses: dict[str, CommandStatus] | None = None) -> None:
        self.statuses = statuses or {}
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        status = self.statuses.get(request.command_id, CommandStatus.SUCCEEDED)
        return SimpleNamespace(
            result=CommandResultDto(
                command_id=request.command_id,
                run_id=request.run_id,
                status=status,
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                exit_code=0 if status is CommandStatus.SUCCEEDED else None,
            )
        )


def _settings(tmp_path: Path, source_root: Path, target_root: Path) -> Settings:
    return Settings(
        _env_file=None,
        artifact_root=tmp_path / "runs",
        workspace_root=tmp_path / "workspaces",
        snapshot_root=tmp_path / "snapshots",
        delivery_root=tmp_path / "delivery",
        sandbox_root=tmp_path / "sandboxes",
        allowed_source_roots=[source_root],
        allowed_target_roots=[target_root],
        command_timeout_seconds=5,
    )


def _request(source: Path, target: Path, *, target_family: str = "21.x", mode: str = "strict-functional-parity") -> PreflightRequestDto:
    return PreflightRequestDto(
        source_path=str(source),
        target_output_path=str(target),
        target_angular_family=target_family,
        migration_mode=mode,
    )


def test_valid_fixture_setup_returns_checksum_artifact_and_capabilities(tmp_path: Path) -> None:
    source_root = tmp_path / "sources"
    target_root = tmp_path / "targets"
    source = source_root / "angular-app"
    target = target_root / "output"
    source.mkdir(parents=True)
    target_root.mkdir()
    (source / "package.json").write_text('{"dependencies":{"@angular/core":"18.2.0"}}', encoding="utf-8")
    artifact_store = LocalFilesystemArtifactStore(tmp_path / "runs")
    worker = FakeWorker()
    service = PreflightService(
        settings=_settings(tmp_path, source_root, target_root),
        artifact_store=artifact_store,
        worker=worker,
    )

    result = service.validate(_request(source, target))

    assert result.status == "passed_with_warnings"
    assert result.checksum.startswith("sha256:")
    assert result.artifact is not None
    assert result.capabilities == {
        "python": "succeeded",
        "node": "succeeded",
        "npm": "succeeded",
        "npx": "succeeded",
        "git": "succeeded",
    }
    assert service.is_current_and_runnable(result.checksum) is True
    assert [request.command_id for request in worker.requests] == [
        "python-version",
        "node-version",
        "npm-version",
        "npx-version",
        "git-version",
    ]
    stored = artifact_store.read_artifact_by_id(result.artifact["artifact_id"])
    assert '"policy_version": "sprint0-preflight-v1"' in stored.content


def test_changing_setup_inputs_changes_checksum(tmp_path: Path) -> None:
    source_root = tmp_path / "sources"
    target_root = tmp_path / "targets"
    source = source_root / "angular-app"
    target = target_root / "output"
    source.mkdir(parents=True)
    target_root.mkdir()
    service = PreflightService(
        settings=_settings(tmp_path, source_root, target_root),
        artifact_store=LocalFilesystemArtifactStore(tmp_path / "runs"),
        worker=FakeWorker(),
    )

    first = service.validate(_request(source, target, target_family="21.x"))
    second = service.validate(_request(source, target, target_family="22.x"))
    third = service.validate(_request(source, target, mode="preview"))

    assert len({first.checksum, second.checksum, third.checksum}) == 3


def test_unsafe_source_target_relationships_are_blocked(tmp_path: Path) -> None:
    source_root = tmp_path / "sources"
    target_root = tmp_path / "targets"
    source = source_root / "angular-app"
    nested_target = source / "dist" / "migration"
    source.mkdir(parents=True)
    target_root.mkdir()
    service = PreflightService(
        settings=_settings(tmp_path, source_root, target_root),
        artifact_store=LocalFilesystemArtifactStore(tmp_path / "runs"),
        worker=FakeWorker(),
    )

    same_path = service.validate(_request(source, source))
    nested = service.validate(_request(source, nested_target))

    assert same_path.status == "blocked"
    assert "source_target_same_path" in same_path.blockers
    assert nested.status == "blocked"
    assert "target_nested_inside_source" in nested.blockers


def test_missing_runtime_tool_returns_structured_blocker(tmp_path: Path) -> None:
    source_root = tmp_path / "sources"
    target_root = tmp_path / "targets"
    source = source_root / "angular-app"
    target = target_root / "output"
    source.mkdir(parents=True)
    target_root.mkdir()
    service = PreflightService(
        settings=_settings(tmp_path, source_root, target_root),
        artifact_store=LocalFilesystemArtifactStore(tmp_path / "runs"),
        worker=FakeWorker({"git-version": CommandStatus.FAILED}),
    )

    result = service.validate(_request(source, target))

    assert result.status == "blocked"
    assert "runtime_tool_unavailable_git" in result.blockers
    assert result.capabilities["git"] == "failed"


def test_expired_preflight_is_not_runnable(tmp_path: Path) -> None:
    source_root = tmp_path / "sources"
    target_root = tmp_path / "targets"
    source = source_root / "angular-app"
    target = target_root / "output"
    source.mkdir(parents=True)
    target_root.mkdir()
    now = datetime.now(UTC)
    current = {"value": now}
    service = PreflightService(
        settings=_settings(tmp_path, source_root, target_root),
        artifact_store=LocalFilesystemArtifactStore(tmp_path / "runs"),
        worker=FakeWorker(),
        now_provider=lambda: current["value"],
    )

    result = service.validate(_request(source, target))
    current["value"] = now + timedelta(minutes=16)

    assert service.is_current_and_runnable(result.checksum) is False
    assert service.is_expired(result.checksum) is True
