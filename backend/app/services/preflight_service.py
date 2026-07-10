"""Runtime preflight validation for Sprint 0 setup inputs."""

from __future__ import annotations

import hashlib
import json
import shutil
from typing import Protocol
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.artifact_store import LocalFilesystemArtifactStore
from app.command_execution import CommandLogWriter, CommandPolicy, ExecutionWorker
from app.core.config import Settings, get_settings
from app.domain.contracts import (
    ArtifactType,
    CommandRequestDto,
    CommandResultDto,
    CommandStatus,
    PreflightFindingDto,
    PreflightRequestDto,
    PreflightResultDto,
    PreflightSeverity,
    PreflightStatus,
    RuntimeCapabilityDto,
)

class CommandExecutionLike(Protocol):
    result: CommandResultDto


class RunCommand(Protocol):
    def __call__(self, request: CommandRequestDto) -> CommandExecutionLike: ...

RUNTIME_TOOLS = ("python", "node", "npm", "npx", "git")
PREFLIGHT_RUN_ID = "mock-run-angular-18-to-21"
PREFLIGHT_TTL = timedelta(minutes=15)


def get_preflight_artifact_store() -> LocalFilesystemArtifactStore:
    return LocalFilesystemArtifactStore(get_settings().artifact_root)


def run_preflight(
    request: PreflightRequestDto,
    *,
    settings: Settings | None = None,
    artifact_store: LocalFilesystemArtifactStore | None = None,
    command_runner: RunCommand | None = None,
    now: datetime | None = None,
) -> PreflightResultDto:
    """Validate setup inputs before mock run creation."""
    settings = settings or get_settings()
    artifact_store = artifact_store or get_preflight_artifact_store()
    now = now or datetime.now(UTC)

    normalized = _normalize_request(request)
    checksum = _checksum(normalized)
    findings: list[PreflightFindingDto] = []
    findings.extend(_path_findings(normalized))

    sandbox_root = settings.sandbox_root.resolve()
    sandbox_root.mkdir(parents=True, exist_ok=True)
    runner = command_runner or _build_command_runner(settings, artifact_store, sandbox_root)
    capabilities = _check_capabilities(runner, sandbox_root, now, findings)

    status = _status_from_findings(findings)
    expires_at = now + PREFLIGHT_TTL
    result = PreflightResultDto(
        run_id=PREFLIGHT_RUN_ID,
        status=status,
        input_checksum=checksum,
        expires_at=expires_at,
        source_path=normalized["source_path"],
        target_output_path=normalized["target_output_path"],
        findings=findings,
        capabilities=capabilities,
        artifact=None,
    )
    artifact = artifact_store.write_text_artifact(
        PREFLIGHT_RUN_ID,
        "00_job_setup/preflight-result.json",
        result.model_dump_json(indent=2),
        ArtifactType.JSON,
        created_by="runtime-preflight",
        created_at=now,
    )
    return result.model_copy(update={"artifact": artifact.ref})


def is_preflight_current(request: PreflightRequestDto, result: PreflightResultDto, *, now: datetime | None = None) -> bool:
    """Return whether a result is still bound to these inputs and not expired."""
    now = now or datetime.now(UTC)
    return (
        result.input_checksum == _checksum(_normalize_request(request))
        and result.status != PreflightStatus.BLOCKED
        and result.expires_at > now
    )


def _build_command_runner(settings: Settings, artifact_store: LocalFilesystemArtifactStore, sandbox_root: Path) -> RunCommand:
    worker = ExecutionWorker(
        CommandPolicy(sandbox_root=sandbox_root),
        CommandLogWriter(artifact_store),
        timeout_seconds=settings.command_timeout_seconds,
    )
    return worker.run


def _normalize_request(request: PreflightRequestDto) -> dict[str, object]:
    return {
        "source_path": str(Path(request.source_path).expanduser().resolve()),
        "target_output_path": str(Path(request.target_output_path).expanduser().resolve()),
        "target_angular_family": request.target_angular_family.strip(),
        "migration_mode": request.migration_mode.strip(),
        "auto_approval_enabled": request.auto_approval_enabled,
    }


def _checksum(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _path_findings(normalized: dict[str, object]) -> list[PreflightFindingDto]:
    findings: list[PreflightFindingDto] = []
    source = Path(str(normalized["source_path"]))
    target = Path(str(normalized["target_output_path"]))

    if source == target:
        findings.append(_finding("PATH_SOURCE_EQUALS_TARGET", PreflightSeverity.BLOCKER, "Source and target output paths must be different."))
    if _is_relative_to(target, source):
        findings.append(_finding("PATH_TARGET_INSIDE_SOURCE", PreflightSeverity.BLOCKER, "Target output path must not be nested inside the source path."))
    if not source.is_dir():
        findings.append(_finding("SOURCE_NOT_READABLE", PreflightSeverity.BLOCKER, "Source path must exist and be readable."))
    else:
        try:
            next(source.iterdir(), None)
        except OSError:
            findings.append(_finding("SOURCE_NOT_READABLE", PreflightSeverity.BLOCKER, "Source path must be readable."))

    writable_root = target if target.exists() else target.parent
    if not writable_root.exists():
        findings.append(_finding("TARGET_PARENT_MISSING", PreflightSeverity.BLOCKER, "Target parent directory must exist before Sprint 0 preflight."))
    else:
        try:
            probe = writable_root / ".amf-preflight-write-check"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError:
            findings.append(_finding("TARGET_NOT_WRITABLE", PreflightSeverity.BLOCKER, "Target output location must be writable."))
        try:
            usage = shutil.disk_usage(writable_root)
            if usage.free < 100 * 1024 * 1024:
                findings.append(_finding("LOW_DISK_SPACE", PreflightSeverity.WARNING, "Less than 100 MB free space is available for the mock output."))
        except OSError:
            findings.append(_finding("DISK_SPACE_UNKNOWN", PreflightSeverity.WARNING, "Disk space could not be estimated."))

    findings.append(_finding("RUNTIME_PROFILE_PLACEHOLDER", PreflightSeverity.INFO, "Runtime profile, registry, proxy, certificate, topology, and Angular eligibility checks are placeholders in Sprint 0."))
    return findings


def _check_capabilities(
    runner: RunCommand,
    sandbox_root: Path,
    now: datetime,
    findings: list[PreflightFindingDto],
) -> list[RuntimeCapabilityDto]:
    capabilities: list[RuntimeCapabilityDto] = []
    for tool in RUNTIME_TOOLS:
        command_id = f"preflight-{tool}-version"
        request = CommandRequestDto(
            command_id=command_id,
            run_id=PREFLIGHT_RUN_ID,
            stage_id=None,
            requester="runtime-preflight",
            executable=tool,
            arguments=["--version"],
            working_directory=str(sandbox_root),
            requested_at=now,
        )
        execution = runner(request)
        result = execution.result
        available = result.status == CommandStatus.SUCCEEDED
        code = None if available else f"MISSING_{tool.upper()}"
        if not available:
            findings.append(_finding(code or "MISSING_TOOL", PreflightSeverity.BLOCKER, f"{tool} --version is unavailable through the structured worker."))
        capabilities.append(RuntimeCapabilityDto(tool=tool, available=available, version=None, finding_code=code))
    return capabilities


def _status_from_findings(findings: list[PreflightFindingDto]) -> PreflightStatus:
    if any(finding.severity == PreflightSeverity.BLOCKER for finding in findings):
        return PreflightStatus.BLOCKED
    if any(finding.severity == PreflightSeverity.WARNING for finding in findings):
        return PreflightStatus.PASSED_WITH_WARNINGS
    return PreflightStatus.PASSED


def _finding(code: str, severity: PreflightSeverity, message: str) -> PreflightFindingDto:
    return PreflightFindingDto(code=code, severity=severity, message=message)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return path != parent
