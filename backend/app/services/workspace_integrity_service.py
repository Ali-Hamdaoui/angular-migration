"""Verify the physical workspace still matches the G05-approved tree."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.workspace_fingerprint import PLANNING_FINGERPRINT_PROFILE


@dataclass(frozen=True)
class WorkspaceIntegrityResult:
    workspace: Path
    expected_fingerprint: str
    actual_fingerprint: str


class WorkspaceIntegrityError(ValueError):
    def __init__(self, workspace: Path, expected_fingerprint: str, actual_fingerprint: str) -> None:
        self.code = "PLANNING_WORKSPACE_FINGERPRINT_MISMATCH"
        self.workspace = workspace
        self.expected_fingerprint = expected_fingerprint
        self.actual_fingerprint = actual_fingerprint
        super().__init__(self.code)


class WorkspaceIntegrityService:
    @staticmethod
    def fingerprint(root: Path) -> str:
        return PLANNING_FINGERPRINT_PROFILE.fingerprint(root)

    def verify(self, workspace: Path, *, expected_fingerprint: str) -> WorkspaceIntegrityResult:
        workspace = Path(workspace).resolve(strict=True)
        actual = self.fingerprint(workspace)
        if actual != expected_fingerprint:
            raise WorkspaceIntegrityError(workspace, expected_fingerprint, actual)
        return WorkspaceIntegrityResult(workspace, expected_fingerprint, actual)
