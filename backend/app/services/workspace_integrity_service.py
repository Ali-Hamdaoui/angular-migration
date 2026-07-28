"""Verify the physical workspace still matches the G05-approved tree."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path


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
        root = Path(root).resolve(strict=True)
        digest = hashlib.sha256()
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            relative = path.relative_to(root).as_posix().encode("utf-8")
            content = path.read_bytes()
            digest.update(len(relative).to_bytes(8, "big"))
            digest.update(relative)
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
        return f"sha256:{digest.hexdigest()}"

    def verify(self, workspace: Path, *, expected_fingerprint: str) -> WorkspaceIntegrityResult:
        workspace = Path(workspace).resolve(strict=True)
        actual = self.fingerprint(workspace)
        if actual != expected_fingerprint:
            raise WorkspaceIntegrityError(workspace, expected_fingerprint, actual)
        return WorkspaceIntegrityResult(workspace, expected_fingerprint, actual)
