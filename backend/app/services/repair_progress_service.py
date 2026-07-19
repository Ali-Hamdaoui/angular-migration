"""Application service for no-progress repair loop detection and recovery.

Bounded repair protects cost, source parity, and delivery predictability;
repeated equivalent patches must never loop.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.domain.repair_progress import (
    AttemptOutcome,
    DiagnosticHoldSummary,
    FailureSetComparison,
    NoProgressReason,
    NormalizedPatchFingerprint,
    RecoveryAction,
    RepairAttemptRecord,
    RepairChainProgress,
    RepairChainStatus,
    RepairRecoveryResult,
    RollbackRecord,
    StageReconstructionRecord,
    compare_failure_sets,
    normalize_patch_fingerprint,
)


class RepairProgressError(ValueError):
    """Raised when repair progress operations fail."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


MAX_APPLIED_ATTEMPTS = 3


class RepairProgressService:
    """Track, detect, and act on no-progress repair loops.

    Provides semantic patch normalization/fingerprints, failure-set comparison,
    max-three applied attempts limit, revision/transport counters separation,
    rollback checkpoint or WorkspaceManager reconstruction, and diagnostic-hold
    transitions.
    """

    def detect_no_progress(
        self,
        *,
        chain: RepairChainProgress,
        new_patch_content: str,
        new_failure_set: tuple[str, ...],
        previous_failure_set: tuple[str, ...],
    ) -> tuple[bool, NoProgressReason | None, str]:
        """Detect if a new patch represents no progress.

        Returns (is_no_progress, reason, detail).
        """
        # 1. Duplicate patch detection via normalized fingerprint
        new_fingerprint = normalize_patch_fingerprint(new_patch_content)
        for existing_fp in chain.patch_fingerprints:
            if existing_fp == new_fingerprint.checksum:
                return True, NoProgressReason.DUPLICATE_PATCH, (
                    f"Patch fingerprint '{new_fingerprint.checksum[:16]}...' "
                    f"matches previous attempt"
                )

        # 2. Identical failure fingerprint
        new_failure_fp = self._compute_failure_fingerprint(new_failure_set)
        for existing_ffp in chain.failure_fingerprints:
            if existing_ffp == new_failure_fp:
                return True, NoProgressReason.IDENTICAL_FINGERPRINT, (
                    f"Failure fingerprint '{new_failure_fp[:16]}...' "
                    f"matches previous attempt"
                )

        # 3. No error delta
        comparison = compare_failure_sets(previous_failure_set, new_failure_set)
        if comparison.identical and len(new_failure_set) > 0:
            return True, NoProgressReason.NO_ERROR_DELTA, (
                "Error set is identical to previous attempt; no progress"
            )

        # 4. Attempt limit
        if chain.applied_attempts >= MAX_APPLIED_ATTEMPTS:
            return True, NoProgressReason.ATTEMPT_LIMIT_REACHED, (
                f"Maximum applied attempts ({MAX_APPLIED_ATTEMPTS}) reached"
            )

        return False, None, ""

    def create_chain(
        self,
        *,
        chain_id: str,
        run_id: str,
    ) -> RepairChainProgress:
        """Create a new repair chain."""
        return RepairChainProgress(
            chain_id=chain_id,
            run_id=run_id,
            status=RepairChainStatus.ACTIVE,
            attempts=(),
            updated_at=datetime.now(UTC),
        )

    def record_attempt(
        self,
        *,
        chain: RepairChainProgress,
        attempt_number: int,
        attempt_id: str,
        patch_content: str,
        failure_signatures: tuple[str, ...],
        outcome: AttemptOutcome,
        outcome_at: datetime | None = None,
    ) -> RepairChainProgress:
        """Record a new attempt in the chain."""
        patch_fingerprint = normalize_patch_fingerprint(patch_content)
        failure_fingerprint = self._compute_failure_fingerprint(failure_signatures)

        new_attempt = RepairAttemptRecord(
            attempt_number=attempt_number,
            attempt_id=attempt_id,
            patch_fingerprint=patch_fingerprint.checksum,
            failure_fingerprint=failure_fingerprint,
            outcome=outcome,
            outcome_at=outcome_at or datetime.now(UTC),
        )

        attempts = list(chain.attempts) + [new_attempt]
        applied = sum(1 for a in attempts if a.outcome == AttemptOutcome.APPLIED)
        duplicates = sum(1 for a in attempts if a.outcome == AttemptOutcome.DUPLICATE)
        fingerprints = tuple(
            dict.fromkeys(list(chain.patch_fingerprints) + [patch_fingerprint.checksum])
        )
        failure_fps = tuple(
            dict.fromkeys(list(chain.failure_fingerprints) + [failure_fingerprint])
        )

        return RepairChainProgress(
            chain_id=chain.chain_id,
            run_id=chain.run_id,
            status=chain.status,
            attempts=tuple(attempts),
            total_attempts=len(attempts),
            applied_attempts=applied,
            duplicate_count=duplicates,
            max_applied_attempts=MAX_APPLIED_ATTEMPTS,
            patch_fingerprints=fingerprints,
            failure_fingerprints=failure_fps,
            rollback_record=chain.rollback_record,
            reconstruction_record=chain.reconstruction_record,
            diagnostic_hold=chain.diagnostic_hold,
            no_progress_reason=chain.no_progress_reason,
            recovery_action=chain.recovery_action,
            artifact_refs=chain.artifact_refs,
            state_version=chain.state_version + 1,
            updated_at=datetime.now(UTC),
        )

    def mark_no_progress(
        self,
        *,
        chain: RepairChainProgress,
        reason: NoProgressReason,
    ) -> RepairChainProgress:
        """Mark the chain as no-progress and set the appropriate action."""
        action = self._determine_recovery_action(reason)

        diagnostic_hold = DiagnosticHoldSummary(
            chain_id=chain.chain_id,
            reason=reason,
            attempt_count=chain.total_attempts,
            duplicate_count=chain.duplicate_count,
            held_at=datetime.now(UTC),
            details={
                "reason": reason.value,
                "total_attempts": chain.total_attempts,
                "applied_attempts": chain.applied_attempts,
            },
        )

        return RepairChainProgress(
            chain_id=chain.chain_id,
            run_id=chain.run_id,
            status=RepairChainStatus.DIAGNOSTIC_HOLD,
            attempts=chain.attempts,
            total_attempts=chain.total_attempts,
            applied_attempts=chain.applied_attempts,
            duplicate_count=chain.duplicate_count,
            max_applied_attempts=MAX_APPLIED_ATTEMPTS,
            patch_fingerprints=chain.patch_fingerprints,
            failure_fingerprints=chain.failure_fingerprints,
            rollback_record=chain.rollback_record,
            reconstruction_record=chain.reconstruction_record,
            diagnostic_hold=diagnostic_hold,
            no_progress_reason=reason,
            recovery_action=action,
            artifact_refs=chain.artifact_refs,
            state_version=chain.state_version + 1,
            updated_at=datetime.now(UTC),
        )

    def recover(
        self,
        *,
        chain: RepairChainProgress,
        run_id: str,
        stage_id: str,
        workspace_fingerprint_before: str = "",
        source_input_fingerprint: str = "",
    ) -> RepairRecoveryResult:
        """Execute recovery action (rollback or reconstruction)."""
        if chain.recovery_action is None:
            raise RepairProgressError(
                "NO_RECOVERY_ACTION",
                "No recovery action has been determined for this chain",
            )

        now = datetime.now(UTC)
        rollback_record: RollbackRecord | None = None
        reconstruction_record: StageReconstructionRecord | None = None
        new_state_version = chain.state_version + 1

        if chain.recovery_action == RecoveryAction.ROLL_BACK:
            rollback_record = RollbackRecord(
                rollback_id=f"rollback-{uuid4().hex[:12]}",
                chain_id=chain.chain_id,
                run_id=run_id,
                stage_id=stage_id,
                rolled_back_at=now,
                restored_from_fingerprint=workspace_fingerprint_before,
                restored_to_fingerprint=f"pre-repair-{uuid4().hex[:12]}",
            )
        elif chain.recovery_action == RecoveryAction.RECONSTRUCT_FROM_INPUT:
            reconstruction_record = StageReconstructionRecord(
                reconstruction_id=f"recon-{uuid4().hex[:12]}",
                chain_id=chain.chain_id,
                run_id=run_id,
                stage_id=stage_id,
                reconstructed_at=now,
                source_input_fingerprint=source_input_fingerprint,
                new_fingerprint=f"reconstructed-{uuid4().hex[:12]}",
            )

        diagnostic_hold = chain.diagnostic_hold

        return RepairRecoveryResult(
            chain_id=chain.chain_id,
            run_id=run_id,
            action=chain.recovery_action,
            status=RepairChainStatus.DIAGNOSTIC_HOLD,
            state_version=new_state_version,
            rollback_record=rollback_record,
            reconstruction_record=reconstruction_record,
            diagnostic_hold=diagnostic_hold,
            artifact_refs={
                "rollback_record": f"artifact:{chain.chain_id}/rollback" if rollback_record else "",
                "reconstruction_record": f"artifact:{chain.chain_id}/reconstruction" if reconstruction_record else "",
                "diagnostic_hold": f"artifact:{chain.chain_id}/diagnostic-hold",
            },
        )

    def get_chain_progress(
        self,
        *,
        chain: RepairChainProgress,
    ) -> RepairChainProgress:
        """Return the current chain progress."""
        return chain

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_failure_fingerprint(failure_signatures: tuple[str, ...]) -> str:
        """Compute a fingerprint for a set of failure signatures."""
        import hashlib
        sorted_sigs = tuple(sorted(failure_signatures))
        raw = "|".join(sorted_sigs)
        return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _determine_recovery_action(reason: NoProgressReason) -> RecoveryAction:
        """Determine the appropriate recovery action based on the no-progress reason."""
        if reason in (
            NoProgressReason.DUPLICATE_PATCH,
            NoProgressReason.IDENTICAL_FINGERPRINT,
        ):
            return RecoveryAction.ROLL_BACK
        elif reason in (
            NoProgressReason.NO_ERROR_DELTA,
            NoProgressReason.ATTEMPT_LIMIT_REACHED,
            NoProgressReason.COST_THRESHOLD_EXCEEDED,
        ):
            return RecoveryAction.RECONSTRUCT_FROM_INPUT
        else:
            return RecoveryAction.DIAGNOSTIC_HOLD
