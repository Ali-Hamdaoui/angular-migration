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
