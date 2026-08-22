"""Prepare a contained, fingerprinted workspace for one approved migration stage."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Mapping
from uuid import uuid4

from app.services.stage_preparation_primitives import StageSandboxCopier


class StagePreparationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class StagePreparationResult:
    workspace_alias: str
    workspace_path: str
    fingerprint: str
    copied_files: int
    created: bool


class StagePreparationApplicationService:
    def __init__(self, *, copier: StageSandboxCopier | None = None) -> None:
        self._copier = copier or StageSandboxCopier()

    def prepare(
        self,
        aliases: Mapping[str, str],
        stage_id: str,
        *,
        expected_fingerprint: str | None = None,
        expected_source_fingerprint: str | None = None,
    ) -> StagePreparationResult:
        source = aliases.get("BASELINE_SANDBOX")
        root = aliases.get("STAGE_SANDBOX")
        if not source or not root:
            raise StagePreparationError("PREPARATION_ALIASES_REQUIRED", "BASELINE_SANDBOX and STAGE_SANDBOX aliases are required")
        source_path = Path(source).resolve(strict=True)
        if expected_source_fingerprint is not None and self._copier.fingerprint(source_path) != expected_source_fingerprint:
            raise StagePreparationError(
                "SEALED_SOURCE_FINGERPRINT_MISMATCH",
                "The sealed predecessor fingerprint changed and cannot be used for reconstruction",
            )
        stage_root = Path(root)
        stage_root.mkdir(parents=True, exist_ok=True)
        target = stage_root / stage_id
        alias = "STAGE_WORKSPACE_" + stage_id.upper().replace("-", "_")
        if target.exists():
            if not target.is_dir():
                raise StagePreparationError("PREPARATION_TARGET_NOT_DIRECTORY", "existing stage workspace is not a directory")
            copied_files = sum(1 for item in target.rglob("*") if item.is_file())
            fingerprint = self._copier.fingerprint(target)
            if expected_fingerprint is not None and fingerprint != expected_fingerprint:
                quarantine = stage_root / f".{stage_id}.quarantined-{uuid4().hex[:12]}"
                target.replace(quarantine)
                try:
                    report = self._copier.copy_atomically(source_path, target, registered_root=stage_root)
                except Exception:
                    if not target.exists() and quarantine.exists():
                        quarantine.replace(target)
                    raise
                shutil.rmtree(quarantine, ignore_errors=True)
                return StagePreparationResult(alias, report.target, report.fingerprint, report.copied_files, True)
            return StagePreparationResult(
                alias,
                str(target.resolve(strict=True)),
                fingerprint,
                copied_files,
                False,
            )
        report = self._copier.copy_atomically(source_path, target, registered_root=stage_root)
        return StagePreparationResult(alias, report.target, report.fingerprint, report.copied_files, True)

    def cleanup(self, result: StagePreparationResult) -> None:
        """Remove only a sandbox created by the current failed preparation attempt."""
        if result.created:
            shutil.rmtree(result.workspace_path, ignore_errors=True)
