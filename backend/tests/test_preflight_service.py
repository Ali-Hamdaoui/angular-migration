"""Tests for Sprint 0 runtime preflight validation."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.artifact_store import LocalFilesystemArtifactStore
from app.core.config import Settings
from app.domain.contracts import CommandRequestDto, CommandResultDto, CommandStatus, PreflightRequestDto, PreflightStatus
from app.main import app
from app.services.preflight_service import is_preflight_current, run_preflight


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        artifact_root=tmp_path / "runs",
        sandbox_root=tmp_path / "sandboxes",
        command_timeout_seconds=5,
    )


def _request(source: Path, target: Path, *, target_family: str = "21.x") -> PreflightRequestDto:
    return PreflightRequestDto(
        source_path=str(source),
        target_output_path=str(target),
        target_angular_family=target_family,
        migration_mode="strict-functional-parity",
        auto_approval_enabled=False,
    )


def _successful_runner(request: CommandRequestDto) -> SimpleNamespace:
    result = CommandResultDto(
        command_id=request.command_id,
        run_id=request.run_id,
        stage_id=request.stage_id,
        status=CommandStatus.SUCCEEDED,
        started_at=request.requested_at,
        finished_at=request.requested_at,
        duration_ms=1,
        exit_code=0,
    )
    return SimpleNamespace(result=result)


def test_valid_fixture_preflight_returns_checksum_and_artifact(tmp_path: Path) -> None:
    source = tmp_path / "fixture-source"
    target_parent = tmp_path / "outputs"
    source.mkdir()
    target_parent.mkdir()
    (source / "package.json").write_text('{"name":"fixture"}', encoding="utf-8")
    artifact_store = LocalFilesystemArtifactStore(tmp_path / "runs")

    result = run_preflight(
        _request(source, target_parent / "migrated-app"),
        settings=_settings(tmp_path),
        artifact_store=artifact_store,
        command_runner=_successful_runner,
        now=datetime(2026, 7, 10, tzinfo=UTC),
    )

    assert result.status == PreflightStatus.PASSED
    assert result.input_checksum.startswith("sha256:")
    assert result.artifact is not None
    assert result.artifact.relative_path == "00_job_setup/preflight-result.json"
    stored = artifact_store.read_artifact(result.run_id, result.artifact.relative_path)
    assert result.input_checksum in stored.content
    assert (source / "package.json").read_text(encoding="utf-8") == '{"name":"fixture"}'


def test_preflight_checksum_changes_when_bound_inputs_change(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target_parent = tmp_path / "target"
    source.mkdir()
    target_parent.mkdir()
    settings = _settings(tmp_path)
    store = LocalFilesystemArtifactStore(tmp_path / "runs")

    first_request = _request(source, target_parent / "app", target_family="21.x")
    second_request = _request(source, target_parent / "app", target_family="22.x")
    first = run_preflight(first_request, settings=settings, artifact_store=store, command_runner=_successful_runner)
    second = run_preflight(second_request, settings=settings, artifact_store=store, command_runner=_successful_runner)

    assert first.input_checksum != second.input_checksum
    assert is_preflight_current(first_request, first)
    assert not is_preflight_current(second_request, first)


def test_preflight_blocks_target_inside_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()

    result = run_preflight(
        _request(source, source / "nested-output"),
        settings=_settings(tmp_path),
        artifact_store=LocalFilesystemArtifactStore(tmp_path / "runs"),
        command_runner=_successful_runner,
    )

    assert result.status == PreflightStatus.BLOCKED
    assert "PATH_TARGET_INSIDE_SOURCE" in {finding.code for finding in result.findings}


def test_preflight_reports_missing_tool_as_structured_blocker(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target_parent = tmp_path / "target"
    source.mkdir()
    target_parent.mkdir()

    def missing_node_runner(request: CommandRequestDto) -> SimpleNamespace:
        status = CommandStatus.FAILED if request.executable == "node" else CommandStatus.SUCCEEDED
        return SimpleNamespace(
            result=CommandResultDto(
                command_id=request.command_id,
                run_id=request.run_id,
                stage_id=request.stage_id,
                status=status,
                started_at=request.requested_at,
                finished_at=request.requested_at,
                duration_ms=1,
                exit_code=1 if status == CommandStatus.FAILED else 0,
            )
        )

    result = run_preflight(
        _request(source, target_parent / "app"),
        settings=_settings(tmp_path),
        artifact_store=LocalFilesystemArtifactStore(tmp_path / "runs"),
        command_runner=missing_node_runner,
    )

    assert result.status == PreflightStatus.BLOCKED
    assert "MISSING_NODE" in {finding.code for finding in result.findings}
    assert any(capability.tool == "node" and not capability.available for capability in result.capabilities)


def test_preflight_endpoint_returns_public_contract(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source"
    target_parent = tmp_path / "target"
    source.mkdir()
    target_parent.mkdir()
    monkeypatch.setattr("app.services.preflight_service.get_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr("app.api.routes.migrations.run_preflight", lambda request: run_preflight(
        request,
        settings=_settings(tmp_path),
        artifact_store=LocalFilesystemArtifactStore(tmp_path / "runs"),
        command_runner=_successful_runner,
    ))

    response = TestClient(app).post("/migrations/preflight", json={
        "source_path": str(source),
        "target_output_path": str(target_parent / "app"),
        "target_angular_family": "21.x",
        "migration_mode": "strict-functional-parity",
        "auto_approval_enabled": False,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "passed"
    assert body["artifact"]["relative_path"] == "00_job_setup/preflight-result.json"
