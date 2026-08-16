"""Runtime preflight validation for Sprint 0."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterable

from app.artifact_store import LocalFilesystemArtifactStore
from app.command_execution import CommandLogWriter, CommandPolicy, ExecutionWorker
from app.core.config import Settings, get_settings
from app.domain.contracts import ArtifactType, CommandRequestDto, CommandStatus, PreflightRequestDto, PreflightResultDto

PREFLIGHT_EXPIRY_MINUTES = 15
PREFLIGHT_POLICY_VERSION = "sprint0-preflight-v1"


@dataclass(frozen=True)
class CapabilityCommand:
    name: str
    command_id: str
    executable: str


@dataclass(frozen=True)
class StoredPreflight:
    checksum: str
    status: str
    expires_at: datetime
    input_checksum: str


class PreflightService:
    """Validate setup inputs before a mock migration run can be created."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        artifact_store: LocalFilesystemArtifactStore | None = None,
        worker: ExecutionWorker | None = None,
        now_provider=None,
    ) -> None:
        self._settings = settings or get_settings()
        self._artifact_store = artifact_store or LocalFilesystemArtifactStore(self._settings.artifact_root)
        self._worker = worker or self._build_worker()
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._results: dict[str, StoredPreflight] = {}

    def validate(self, request: PreflightRequestDto) -> PreflightResultDto:
        normalized = self._normalize_request(request)
        checksum = self._checksum(normalized)
        preflight_id = f"preflight-{checksum.removeprefix('sha256:')[:16]}"
        expires_at = self._now_provider() + timedelta(minutes=PREFLIGHT_EXPIRY_MINUTES)

        blockers: list[str] = []
        warnings: list[str] = []
        capabilities: dict[str, str] = {}

        self._check_paths(normalized, blockers, warnings)
        self._check_capabilities(preflight_id, capabilities, blockers, warnings)

        if blockers:
            status = "blocked"
            message = "Preflight blocked by setup or runtime capability checks."
        elif warnings:
            status = "passed_with_warnings"
            message = "Preflight passed with Sprint 0 placeholder warnings."
        else:
            status = "passed"
            message = "Preflight passed for the controlled Sprint 0 flow."

        payload = {
            "preflight_id": preflight_id,
            "checksum": checksum,
            "status": status,
            "source_path": normalized["source_path"],
            "target_output_path": normalized["target_output_path"],
            "target_angular_family": normalized["target_angular_family"],
            "migration_mode": normalized["migration_mode"],
            "auto_approval_enabled": normalized["auto_approval_enabled"],
            "blockers": blockers,
            "warnings": warnings,
            "capabilities": capabilities,
            "runtime_profile_available": True,
            "registry_access": "placeholder_not_checked",
            "topology_status": "placeholder_not_scanned",
            "angular_eligibility": "placeholder_not_scanned",
            "policy_version": PREFLIGHT_POLICY_VERSION,
            "expires_at": expires_at.isoformat(),
        }
        artifact = self._artifact_store.write_text_artifact(
            preflight_id,
            "00_job_setup/preflight-result.json",
            json.dumps(payload, indent=2, sort_keys=True),
            ArtifactType.JSON,
            created_by="preflight-service",
            created_at=self._now_provider(),
            input_hashes={"preflight_input": checksum},
            policy_version=PREFLIGHT_POLICY_VERSION,
        )
        payload["artifact"] = artifact.ref.model_dump(mode="json")
        result = PreflightResultDto(
            preflight_id=preflight_id,
            checksum=checksum,
            expires_at=expires_at,
            source_path=normalized["source_path"],
            target_output_path=normalized["target_output_path"],
            status=status,
            message=message,
            blockers=blockers,
            warnings=warnings,
            capabilities=capabilities,
            runtime_profile_available=True,
            registry_access="placeholder_not_checked",
            topology_status="placeholder_not_scanned",
            angular_eligibility="placeholder_not_scanned",
            artifact=artifact.ref.model_dump(mode="json"),
        )
        self._results[checksum] = StoredPreflight(
            checksum=checksum,
            status=status,
            expires_at=expires_at,
            input_checksum=checksum,
        )
        return result

    def is_current_and_runnable(self, checksum: str) -> bool:
        stored = self._results.get(checksum)
        if stored is None:
            return False
        if stored.expires_at <= self._now_provider():
            return False
        return stored.status in {"passed", "passed_with_warnings"}

    def is_expired(self, checksum: str) -> bool:
        stored = self._results.get(checksum)
        return stored is not None and stored.expires_at <= self._now_provider()

    def _normalize_request(self, request: PreflightRequestDto) -> dict[str, object]:
        return {
            "source_path": str(Path(request.source_path).expanduser().resolve()),
            "target_output_path": str(Path(request.target_output_path).expanduser().resolve()),
            "target_angular_family": request.target_angular_family.strip(),
            "migration_mode": request.migration_mode.strip(),
            "auto_approval_enabled": request.auto_approval_enabled,
            "policy_version": PREFLIGHT_POLICY_VERSION,
        }

    def _checksum(self, normalized: dict[str, object]) -> str:
        payload = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return f"sha256:{hashlib.sha256(payload).hexdigest()}"

    def _check_paths(self, normalized: dict[str, object], blockers: list[str], warnings: list[str]) -> None:
        source = Path(str(normalized["source_path"])).resolve()
        target = Path(str(normalized["target_output_path"])).resolve()

        if not source.exists() or not source.is_dir():
            blockers.append("source_path_not_readable")
        elif not self._is_readable(source):
            blockers.append("source_path_not_readable")

        if source == target:
            blockers.append("source_target_same_path")
        if self._is_relative_to(target, source):
            blockers.append("target_nested_inside_source")
        workspace_root = self._settings.workspace_root.resolve()
        if self._is_relative_to(source, workspace_root):
            blockers.append("source_nested_inside_internal_workspace")

        if not self._is_under_any_root(source, self._settings.allowed_source_roots):
            blockers.append("source_path_outside_allowed_roots")
        if not self._is_under_any_root(target, self._settings.allowed_target_roots):
            blockers.append("target_path_outside_allowed_roots")

        nearest_parent = self._nearest_existing_parent(target)
        if nearest_parent is None or not self._is_writable(nearest_parent):
            blockers.append("target_parent_not_writable")

        usage = shutil.disk_usage(nearest_parent or Path.cwd())
        if usage.free <= 0:
            blockers.append("disk_space_unavailable")
        if len(str(source)) > 220 or len(str(target)) > 220:
            warnings.append("path_length_near_windows_limit")
        if not (source / "package.json").exists():
            warnings.append("package_json_not_detected_placeholder")

    def _check_capabilities(
        self,
        preflight_id: str,
        capabilities: dict[str, str],
        blockers: list[str],
        warnings: list[str],
    ) -> None:
        sandbox = self._settings.sandbox_root.resolve()
        sandbox.mkdir(parents=True, exist_ok=True)
        commands = (
            CapabilityCommand("python", "python-version", "python"),
            CapabilityCommand("node", "node-version", "node"),
            CapabilityCommand("npm", "npm-version", "npm"),
            CapabilityCommand("npx", "npx-version", "npx"),
            CapabilityCommand("git", "git-version", "git"),
        )
        for command in commands:
            execution = self._worker.run(
                CommandRequestDto(
                    command_id=command.command_id,
                    run_id=preflight_id,
                    requested_by="runtime_preflight_component",
                    requester="runtime_preflight_component",
                    executable=command.executable,
                    arguments=["--version"],
                    working_directory_alias="run_workspace",
                    runtime_profile_id="source-runtime-profile",
                    timeout_seconds=min(self._settings.command_timeout_seconds, 10),
                    network_profile="none",
                    idempotency_key=f"{preflight_id}-{command.command_id}",
                    requested_at=self._now_provider(),
                )
            )
            capabilities[command.name] = execution.result.status.value
            if execution.result.status is not CommandStatus.SUCCEEDED:
                blockers.append(f"runtime_tool_unavailable_{command.name}")
        warnings.append("registry_proxy_certificate_placeholder_not_checked")
        warnings.append("topology_and_angular_eligibility_placeholder_not_scanned")

    def _build_worker(self) -> ExecutionWorker:
        sandbox_root = self._settings.sandbox_root.resolve()
        return ExecutionWorker(
            CommandPolicy(
                sandbox_root=sandbox_root,
                working_directory_aliases={"run_workspace": sandbox_root},
            ),
            CommandLogWriter(
                self._artifact_store,
                max_output_bytes=self._settings.command_max_output_bytes,
            ),
            timeout_seconds=min(self._settings.command_timeout_seconds, 10),
        )

    def _is_under_any_root(self, path: Path, roots: Iterable[Path]) -> bool:
        return any(self._is_relative_to(path, root.resolve()) for root in roots)

    def _is_relative_to(self, path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except ValueError:
            return False

    def _nearest_existing_parent(self, path: Path) -> Path | None:
        current = path if path.exists() and path.is_dir() else path.parent
        while current != current.parent:
            if current.exists():
                return current
            current = current.parent
        return None

    def _is_readable(self, path: Path) -> bool:
        try:
            next(path.iterdir(), None)
            return True
        except (OSError, PermissionError):
            return False

    def _is_writable(self, path: Path) -> bool:
        return path.exists() and path.is_dir()
