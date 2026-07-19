"""Domain models for G07 — no-progress repair loop detection and recovery."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class RepairChainStatus(str, Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    DIAGNOSTIC_HOLD = "diagnostic_hold"


class NoProgressReason(str, Enum):
    DUPLICATE_PATCH = "duplicate_patch"
    IDENTICAL_FINGERPRINT = "identical_fingerprint"
    NO_ERROR_DELTA = "no_error_delta"
    ATTEMPT_LIMIT_REACHED = "attempt_limit_reached"
    COST_THRESHOLD_EXCEEDED = "cost_threshold_exceeded"
    USER_CANCELLED = "user_cancelled"


class RecoveryAction(str, Enum):
    ROLL_BACK = "roll_back"
    RECONSTRUCT_FROM_INPUT = "reconstruct_from_input"
    DIAGNOSTIC_HOLD = "diagnostic_hold"


class AttemptOutcome(str, Enum):
    APPLIED = "applied"
    REJECTED = "rejected"
    FAILED = "failed"
    DUPLICATE = "duplicate"
    ROLLED_BACK = "rolled_back"
    RECONSTRUCTED = "reconstructed"


@dataclass(frozen=True)
class NormalizedPatchFingerprint:
    """Semantically normalized fingerprint for duplicate patch detection."""
    normalized_content: str
    checksum: str
    normalization_version: str = "v1"


@dataclass(frozen=True)
class FailureSetComparison:
    previous_failure_set: tuple[str, ...] = ()
    current_failure_set: tuple[str, ...] = ()
    identical: bool = False
    subset: bool = False
    superset: bool = False
    new_failures: tuple[str, ...] = ()
    resolved_failures: tuple[str, ...] = ()
    persistent_failures: tuple[str, ...] = ()
    comparison_checksum: str = ""


@dataclass(frozen=True)
class RepairAttemptRecord:
    attempt_number: int
    attempt_id: str
    patch_fingerprint: str
    failure_fingerprint: str
    outcome: AttemptOutcome
    outcome_at: datetime | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RollbackRecord:
    rollback_id: str
    chain_id: str
    run_id: str
    stage_id: str
    rolled_back_at: datetime
    restored_from_fingerprint: str
    restored_to_fingerprint: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StageReconstructionRecord:
    reconstruction_id: str
    chain_id: str
    run_id: str
    stage_id: str
    reconstructed_at: datetime
    source_input_fingerprint: str
    new_fingerprint: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DiagnosticHoldSummary:
    chain_id: str
    reason: NoProgressReason
    attempt_count: int
    duplicate_count: int
    held_at: datetime | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RepairChainProgress:
    chain_id: str
    run_id: str
    status: RepairChainStatus
    attempts: tuple[RepairAttemptRecord, ...] = ()
    total_attempts: int = 0
    applied_attempts: int = 0
    duplicate_count: int = 0
    max_applied_attempts: int = 3
    patch_fingerprints: tuple[str, ...] = ()
    failure_fingerprints: tuple[str, ...] = ()
    rollback_record: RollbackRecord | None = None
    reconstruction_record: StageReconstructionRecord | None = None
    diagnostic_hold: DiagnosticHoldSummary | None = None
    no_progress_reason: NoProgressReason | None = None
    recovery_action: RecoveryAction | None = None
    artifact_refs: dict[str, str] = field(default_factory=dict)
    state_version: int = 0
    updated_at: datetime | None = None


@dataclass(frozen=True)
class RepairRecoveryResult:
    chain_id: str
    run_id: str
    action: RecoveryAction
    status: RepairChainStatus
    state_version: int
    rollback_record: RollbackRecord | None = None
    reconstruction_record: StageReconstructionRecord | None = None
    diagnostic_hold: DiagnosticHoldSummary | None = None
    artifact_refs: dict[str, str] = field(default_factory=dict)
    idempotent_replay: bool = False


def normalize_patch_fingerprint(patch_content: str) -> NormalizedPatchFingerprint:
    """Normalize a patch by removing whitespace-only differences for comparison."""
    import hashlib
    lines = patch_content.splitlines(keepends=True)
    normalized_lines: list[str] = []
    for line in lines:
        # Strip trailing whitespace for comparison
        stripped = line.rstrip() + "\n"
        normalized_lines.append(stripped)
    normalized = "".join(normalized_lines)
    checksum = "sha256:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return NormalizedPatchFingerprint(
        normalized_content=normalized,
        checksum=checksum,
    )


def compare_failure_sets(
    previous: tuple[str, ...],
    current: tuple[str, ...],
) -> FailureSetComparison:
    """Compare two sets of failure signatures."""
    prev_set = set(previous)
    curr_set = set(current)
    return FailureSetComparison(
        previous_failure_set=previous,
        current_failure_set=current,
        identical=prev_set == curr_set,
        subset=curr_set.issubset(prev_set) if curr_set != prev_set else False,
        superset=prev_set.issubset(curr_set) if curr_set != prev_set else False,
        new_failures=tuple(sorted(curr_set - prev_set)),
        resolved_failures=tuple(sorted(prev_set - curr_set)),
        persistent_failures=tuple(sorted(prev_set & curr_set)),
        comparison_checksum=f"set-v1-{len(prev_set)}-{len(curr_set)}-{hash(tuple(sorted(curr_set)))}",
    )
