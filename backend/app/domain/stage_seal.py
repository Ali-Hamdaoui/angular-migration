"""Deterministic rules for S3-F14 stage seal (G12 gate) and cleanup.

This module defines:
- StageSealService for orchestrating stage sealing
- G12 gate model for sealing gate decisions
- Cleanup and fingerprinting logic
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StageSealError(ValueError):
    """Raised when stage seal inputs or preconditions are invalid."""


class SealStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SEALED = "sealed"
    FAILED = "failed"


class G12Decision(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFICATION_REQUESTED = "modification_requested"


@dataclass(frozen=True)
class OutputFingerprint:
    """Immutable fingerprint of a stage output directory."""
    fingerprint_id: str
    run_id: str
    stage_id: str
    relative_path: str
    size_bytes: int = 0
    checksum: str | None = None
    file_count: int = 0
    created_at: str | None = None


@dataclass(frozen=True)
class CleanupResult:
    """Result of stage workspace cleanup operations."""
    paths_cleaned: tuple[str, ...] = ()
    total_bytes_freed: int = 0
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class G12Gate:
    """G12 sealing gate record bound to state + artifact checksums."""
    gate_id: str
    run_id: str
    stage_id: str
    status: str = "pending"
    decision: G12Decision = G12Decision.PENDING
    fingerprint_checksum: str | None = None
    assurance_checksum: str | None = None
    workspace_fingerprint: str | None = None
    comment: str | None = None
    state_version: int = 1
    event_sequence: int = 1


class StageSealService:
    """Orchestrates stage sealing operations including fingerprinting and cleanup."""

    def compute_fingerprint(
        self,
        fingerprint_id: str,
        run_id: str,
        stage_id: str,
        output_path: str,
        files: list[dict[str, Any]],
    ) -> OutputFingerprint:
        """Compute an output fingerprint from a list of file metadata."""
        total_bytes = sum(f.get("size_bytes", 0) for f in files)
        file_count = len(files)
        # Simple checksum over concatenated file checksums
        checksum_parts = ":".join(
            f.get("checksum", "") for f in sorted(files, key=lambda x: x.get("path", ""))
        )
        import hashlib
        checksum = hashlib.sha256(checksum_parts.encode()).hexdigest() if checksum_parts else None

        return OutputFingerprint(
            fingerprint_id=fingerprint_id,
            run_id=run_id,
            stage_id=stage_id,
            relative_path=output_path,
            size_bytes=total_bytes,
            checksum=checksum,
            file_count=file_count,
        )

    def plan_cleanup(
        self,
        fingerprint: OutputFingerprint,
        workspace_paths: list[str],
        preserve_paths: tuple[str, ...] = (".git", "node_modules", "dist"),
    ) -> CleanupResult:
        """Plan workspace cleanup based on fingerprint and preserve rules."""
        import os
        paths_cleaned: list[str] = []
        errors: list[str] = []
        total_freed = 0

        preserve_set = set(preserve_paths)

        for path in workspace_paths:
            base = os.path.basename(path)
            if base in preserve_set:
                continue
            try:
                if os.path.isfile(path):
                    size = os.path.getsize(path)
                    paths_cleaned.append(path)
                    total_freed += size
                elif os.path.isdir(path):
                    dir_size = sum(
                        os.path.getsize(os.path.join(dp, f))
                        for dp, _, fn in os.walk(path)
                        for f in fn
                    )
                    paths_cleaned.append(path)
                    total_freed += dir_size
            except OSError as e:
                errors.append(f"{path}: {e}")

        return CleanupResult(
            paths_cleaned=tuple(paths_cleaned),
            total_bytes_freed=total_freed,
            errors=tuple(errors),
        )

    def evaluate_g12_readiness(
        self,
        assurance_passed: bool,
        all_checks_passed: bool,
        has_valid_fingerprint: bool,
    ) -> tuple[bool, str | None]:
        """Evaluate whether the stage is ready for G12 sealing."""
        if not assurance_passed:
            return False, "Assurance checks have not passed"
        if not all_checks_passed:
            return False, "Not all stage checks have passed"
        if not has_valid_fingerprint:
            return False, "Valid output fingerprint is required"
        return True, None
