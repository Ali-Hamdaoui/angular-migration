"""Deterministic rules for S3-F11 stage build matrix execution.

This module defines:
- BuildTarget, BuildTargetKind, BuildTargetStatus enums
- BuildResult dataclass for per-target build outcomes
- StageBuildService for orchestrating build matrix execution
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class StageBuildError(ValueError):
    """Raised when stage build inputs or preconditions are invalid."""


class BuildTargetKind(str, Enum):
    APPLICATION = "application"
    LIBRARY = "library"
    TEST_BED = "test_bed"
    E2E = "e2e"


class BuildTargetStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class BuildTarget:
    """A single build target within the stage build matrix."""
    target_id: str
    kind: BuildTargetKind
    project: str | None = None
    configuration: str | None = None
    command_id: str = "stage_build"
    executable: str = "npx"
    arguments: tuple[str, ...] = ("ng", "build")
    working_directory_alias: str = "STAGE_SANDBOX"
    supported: bool = True
    blocker: str | None = None


@dataclass(frozen=True)
class BuildResult:
    """Outcome of a single build target execution."""
    target_id: str
    kind: BuildTargetKind
    status: BuildTargetStatus
    exit_code: int | None = None
    duration_ms: int | None = None
    warnings: tuple[str, ...] = ()
    output_location: str | None = None
    artifact_ids: tuple[str, ...] = ()
    blocker: str | None = None
    output_size_bytes: int | None = None
    output_checksum: str | None = None


class StageBuildService:
    """Orchestrates per-target build execution within a stage.

    This service defines build targets, matrix aggregation, and result
    normalization. Actual command execution is delegated to the application
    service layer via ExecutionWorker.
    """

    def __init__(self):
        self._targets: list[BuildTarget] = []

    def resolve_targets(
        self,
        sandbox: Path,
        target_kinds: tuple[BuildTargetKind, ...] = (
            BuildTargetKind.APPLICATION,
            BuildTargetKind.LIBRARY,
            BuildTargetKind.TEST_BED,
        ),
    ) -> list[BuildTarget]:
        """Resolve build targets from the sandbox workspace.

        In production this would parse angular.json or workspace config.
        For now, return generic targets based on requested kinds.
        """
        targets: list[BuildTarget] = []
        angular_json = sandbox / "angular.json"
        if not angular_json.is_file():
            # Fall back to generic targets
            for idx, kind in enumerate(target_kinds):
                targets.append(BuildTarget(
                    target_id=f"target-{kind.value}-{idx}",
                    kind=kind,
                    project=kind.value,
                    command_id=f"stage_build_{kind.value}",
                    arguments=("ng", "build", kind.value) if kind != BuildTargetKind.TEST_BED else ("ng", "test", "--no-watch"),
                ))
            return targets

        # In a real implementation, parse angular.json projects
        # For now return a single default target
        targets.append(BuildTarget(
            target_id="target-default",
            kind=BuildTargetKind.APPLICATION,
            project="default",
            arguments=("ng", "build", "--prod"),
        ))
        return targets

    def aggregate_matrix_summary(self, results: list[BuildResult]) -> dict[str, Any]:
        """Aggregate build results into a summary dict."""
        return {
            "target_count": len(results),
            "passed": sum(1 for r in results if r.status is BuildTargetStatus.PASSED),
            "failed": sum(1 for r in results if r.status is BuildTargetStatus.FAILED),
            "skipped": sum(1 for r in results if r.status is BuildTargetStatus.SKIPPED),
            "blocked": sum(1 for r in results if r.status is BuildTargetStatus.BLOCKED),
            "cancelled": sum(1 for r in results if r.status is BuildTargetStatus.CANCELLED),
            "total_duration_ms": sum(r.duration_ms or 0 for r in results),
        }
