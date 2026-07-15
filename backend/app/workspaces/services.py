"""Internal run workspace services for Sprint 0."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from app.snapshots.services import ensure_non_overlapping_paths


@dataclass(frozen=True)
class WorkspaceRecord:
    run_id: str
    workspace_root: Path
    repository_path: Path


class BaselineBoundaryError(ValueError):
    """Raised when baseline creation is attempted without an approved G02 boundary."""


class WorkspaceService:
    """Create backend-owned mutable workspaces from immutable snapshots."""

    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = workspace_root

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    def create_workspace_from_snapshot(self, *, run_id: str, snapshot_root: Path, source_root: Path) -> WorkspaceRecord:
        workspace_root = (self._workspace_root / run_id).resolve()
        repository_path = workspace_root / "repository"
        ensure_non_overlapping_paths(source_root, snapshot_root, workspace_root)
        if repository_path.exists():
            raise FileExistsError(f"workspace repository already exists: {repository_path}")
        workspace_root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(snapshot_root, repository_path, ignore=shutil.ignore_patterns("source-manifest.json"))
        return WorkspaceRecord(run_id=run_id, workspace_root=workspace_root, repository_path=repository_path)

    def create_baseline_workspace_from_snapshot(
        self,
        *,
        run_id: str,
        snapshot_root: Path,
        source_root: Path,
        g02_service,
        execution_profile_service=None,
        expected_state_version: int | None = None,
        profile_idempotency_key: str | None = None,
        actor: str = "system",
    ) -> WorkspaceRecord:
        """Create a baseline only after G02 and the runtime profile authorize it."""
        if g02_service is None or not hasattr(g02_service, "authorize_baseline"):
            raise BaselineBoundaryError("An authoritative G02 service is required")
        try:
            package = g02_service.authorize_baseline(run_id)
        except Exception as error:
            if error.__class__.__name__ == "G02ApplicationError":
                raise BaselineBoundaryError(str(error)) from error
            raise
        if package.snapshot_id is None:
            raise BaselineBoundaryError("G02 package must identify the immutable snapshot boundary")
        if execution_profile_service is None or not hasattr(execution_profile_service, "validate_for_baseline"):
            raise BaselineBoundaryError("An authoritative ExecutionProfile service is required")
        if expected_state_version is None or not profile_idempotency_key:
            raise BaselineBoundaryError("Baseline start requires the current run state version and an idempotency key")
        try:
            execution_profile_service.validate_for_baseline(
                run_id,
                expected_state_version=expected_state_version,
                idempotency_key=profile_idempotency_key,
                actor=actor,
            )
        except Exception as error:
            if error.__class__.__name__ == "ExecutionProfileApplicationError":
                raise BaselineBoundaryError(str(error)) from error
            raise
        return self.create_workspace_from_snapshot(run_id=run_id, snapshot_root=snapshot_root, source_root=source_root)

