"""Tests for S4-F09 — RepairProgressService (no-progress repair loop detection and recovery)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from app.domain.repair_progress import (
    AttemptOutcome,
    FailureSetComparison,
    NoProgressReason,
    RecoveryAction,
    RepairAttemptRecord,
    RepairChainProgress,
    RepairChainStatus,
    compare_failure_sets,
    normalize_patch_fingerprint,
)
from app.services.repair_progress_service import MAX_APPLIED_ATTEMPTS, RepairProgressService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SERVICE = RepairProgressService()
NOW = datetime.now(UTC)

PATCH_A = "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new"
PATCH_B = "--- a/bar.py\n+++ b/bar.py\n@@ -1 +1 @@\n-old\n+new"


def _chain(**overrides) -> RepairChainProgress:
    """Build a minimal RepairChainProgress with sensible defaults."""
    defaults: dict = {
        "chain_id": "chain-1",
        "run_id": "run-1",
        "status": RepairChainStatus.ACTIVE,
        "attempts": (),
        "total_attempts": 0,
        "applied_attempts": 0,
        "duplicate_count": 0,
        "max_applied_attempts": MAX_APPLIED_ATTEMPTS,
        "patch_fingerprints": (),
        "failure_fingerprints": (),
        "rollback_record": None,
        "reconstruction_record": None,
        "diagnostic_hold": None,
        "no_progress_reason": None,
        "recovery_action": None,
        "artifact_refs": {},
        "state_version": 0,
        "updated_at": NOW,
    }
    defaults.update(overrides)
    return RepairChainProgress(**defaults)  # type: ignore[arg-type]


def _failure_set(*sigs: str) -> tuple[str, ...]:
    return tuple(sigs)


# ===================================================================
# 1. Create repair chain
# ===================================================================

def test_create_chain_returns_active_chain():
    chain = SERVICE.create_chain(chain_id="chain-1", run_id="run-1")

    assert chain.chain_id == "chain-1"
    assert chain.run_id == "run-1"
    assert chain.status is RepairChainStatus.ACTIVE
    assert chain.attempts == ()
    assert chain.total_attempts == 0
    assert chain.applied_attempts == 0
    assert chain.duplicate_count == 0
    assert chain.patch_fingerprints == ()
    assert chain.failure_fingerprints == ()
    assert chain.no_progress_reason is None
    assert chain.recovery_action is None
    assert chain.state_version == 0
    assert chain.updated_at is not None

# ===================================================================
# 2. Record attempt with APPLIED outcome
# ===================================================================

def test_record_attempt_with_applied_outcome_increments_count():
    chain = _chain()

    result = SERVICE.record_attempt(
        chain=chain,
        attempt_number=1,
        attempt_id="attempt-1",
        patch_content=PATCH_A,
        failure_signatures=_failure_set("err-1"),
        outcome=AttemptOutcome.APPLIED,
    )

    assert len(result.attempts) == 1
    assert result.attempts[0].attempt_number == 1
    assert result.attempts[0].attempt_id == "attempt-1"
    assert result.attempts[0].outcome is AttemptOutcome.APPLIED
    assert result.applied_attempts == 1
    assert result.total_attempts == 1
    assert result.state_version == 1
    assert len(result.patch_fingerprints) == 1
    assert len(result.failure_fingerprints) == 1
    assert result.status is RepairChainStatus.ACTIVE  # unchanged

def test_record_attempt_with_rejected_does_not_count_as_applied():
    chain = _chain()

    result = SERVICE.record_attempt(
        chain=chain,
        attempt_number=1,
        attempt_id="attempt-1",
        patch_content=PATCH_A,
        failure_signatures=_failure_set("err-1"),
        outcome=AttemptOutcome.REJECTED,
    )

    assert result.applied_attempts == 0
    assert result.total_attempts == 1

def test_record_attempt_multiple_applied_correctly_counts():
    chain = _chain()
    for i in range(3):
        outcome = AttemptOutcome.APPLIED if i < 2 else AttemptOutcome.REJECTED
        chain = SERVICE.record_attempt(
            chain=chain,
            attempt_number=i + 1,
            attempt_id=f"attempt-{i+1}",
            patch_content=f"patch-{i}",
            failure_signatures=_failure_set(f"err-{i}"),
            outcome=outcome,
        )

    assert chain.total_attempts == 3
    assert chain.applied_attempts == 2

# ===================================================================
# 3. Detect duplicate patch via normalized fingerprint
# ===================================================================

def test_detect_duplicate_patch_via_normalized_fingerprint():
    """Same patch content (modulo whitespace) must be flagged as duplicate."""
    chain = _chain(
        patch_fingerprints=(
            normalize_patch_fingerprint(PATCH_A).checksum,
        ),
    )

    is_np, reason, detail = SERVICE.detect_no_progress(
        chain=chain,
        new_patch_content=PATCH_A,
        new_failure_set=_failure_set("err-new"),
        previous_failure_set=_failure_set("err-old"),
    )

    assert is_np is True
    assert reason is NoProgressReason.DUPLICATE_PATCH
    assert "matches previous attempt" in detail

def test_detect_duplicate_patch_whitespace_insensitive():
    """Patches differing only in trailing whitespace must be detected as duplicates."""
    content_a = "line1\nline2\n"
    content_b = "line1  \nline2\n"

    fp_a = normalize_patch_fingerprint(content_a)
    fp_b = normalize_patch_fingerprint(content_b)
    assert fp_a.checksum == fp_b.checksum, "whitespace-normalized fingerprints must match"

    chain = _chain(patch_fingerprints=(fp_a.checksum,))

    is_np, reason, detail = SERVICE.detect_no_progress(
        chain=chain,
        new_patch_content=content_b,
        new_failure_set=_failure_set("err-1"),
        previous_failure_set=_failure_set("err-1"),
    )

    assert is_np is True
    assert reason is NoProgressReason.DUPLICATE_PATCH

# ===================================================================
# 4. Detect identical failure fingerprint
# ===================================================================

def test_detect_identical_failure_fingerprint():
    """Same set of failure signatures must be flagged as identical fingerprint."""
    chain = _chain(
        failure_fingerprints=(
            SERVICE._compute_failure_fingerprint(_failure_set("err-a", "err-b")),
        ),
    )

    is_np, reason, detail = SERVICE.detect_no_progress(
        chain=chain,
        new_patch_content=PATCH_B,
        new_failure_set=_failure_set("err-b", "err-a"),  # same set, different order
        previous_failure_set=_failure_set("err-old"),
    )

    assert is_np is True
    assert reason is NoProgressReason.IDENTICAL_FINGERPRINT
    assert "matches previous attempt" in detail

# ===================================================================
# 5. Detect no error delta (identical error sets)
# ===================================================================

def test_detect_no_error_delta_identical_error_sets():
    """Identical non-empty failure sets (by set comparison) must be flagged."""
    chain = _chain()

    is_np, reason, detail = SERVICE.detect_no_progress(
        chain=chain,
        new_patch_content=PATCH_B,
        new_failure_set=_failure_set("err-1", "err-2"),
        previous_failure_set=_failure_set("err-1", "err-2"),
    )

    assert is_np is True
    assert reason is NoProgressReason.NO_ERROR_DELTA
    assert "identical" in detail

def test_no_error_delta_not_triggered_on_empty_sets():
    """Empty error sets must NOT trigger no-error-delta — nothing to compare."""
    chain = _chain()

    is_np, reason, detail = SERVICE.detect_no_progress(
        chain=chain,
        new_patch_content=PATCH_B,
        new_failure_set=(),
        previous_failure_set=(),
    )

    # Empty sets are identical, but the code requires len(new_failure_set) > 0
    assert is_np is False
    assert reason is None

# ===================================================================
# 6. Attempt limit reached (max 3 applied attempts)
# ===================================================================

def test_attempt_limit_reached():
    """Chain with applied_attempts >= MAX_APPLIED_ATTEMPTS must be flagged."""
    chain = _chain(applied_attempts=MAX_APPLIED_ATTEMPTS)

    is_np, reason, detail = SERVICE.detect_no_progress(
        chain=chain,
        new_patch_content=PATCH_B,
        new_failure_set=_failure_set("err-new"),
        previous_failure_set=_failure_set("err-old"),
    )

    assert is_np is True
    assert reason is NoProgressReason.ATTEMPT_LIMIT_REACHED
    assert "Maximum applied attempts" in detail

def test_attempt_limit_not_reached_below_max():
    """Chain below the limit must NOT be flagged for attempt limit."""
    chain = _chain(applied_attempts=MAX_APPLIED_ATTEMPTS - 1)

    is_np, _, _ = SERVICE.detect_no_progress(
        chain=chain,
        new_patch_content=PATCH_B,
        new_failure_set=_failure_set("err-new"),
        previous_failure_set=_failure_set("err-old"),
    )

    assert is_np is False

# ===================================================================
# 7. No progress detection returns False for new unique patches
# ===================================================================

def test_detect_no_progress_false_for_unique_patch():
    """A genuinely new patch with a new failure set must NOT be flagged."""
    chain = _chain()

    is_np, reason, detail = SERVICE.detect_no_progress(
        chain=chain,
        new_patch_content=PATCH_A,
        new_failure_set=_failure_set("err-new"),
        previous_failure_set=_failure_set("err-old"),
    )

    assert is_np is False
    assert reason is None
    assert detail == ""

def test_detect_no_progress_passes_after_reaching_limit_with_different_patches():
    """Different patches with same failures should hit DUPLICATE_PATCH first,
    then IDENTICAL_FINGERPRINT, before ATTEMPT_LIMIT_REACHED would apply."""
    # Build a chain where a patch fingerprint already exists
    fp = normalize_patch_fingerprint(PATCH_A).checksum
    chain = _chain(
        patch_fingerprints=(fp,),
        applied_attempts=0,
    )

    # Even though applied_attempts < 3, duplicate patch is detected first
    is_np, reason, _ = SERVICE.detect_no_progress(
        chain=chain,
        new_patch_content=PATCH_A,
        new_failure_set=_failure_set("err-1"),
        previous_failure_set=_failure_set("err-old"),
    )

    assert is_np is True
    assert reason is NoProgressReason.DUPLICATE_PATCH

# ===================================================================
# 8. Mark no progress -> diagnostic hold state
# ===================================================================

def test_mark_no_progress_transitions_to_diagnostic_hold():
    """mark_no_progress must set status to DIAGNOSTIC_HOLD and create a summary."""
    chain = _chain(total_attempts=3, applied_attempts=1, duplicate_count=1)

    result = SERVICE.mark_no_progress(
        chain=chain,
        reason=NoProgressReason.DUPLICATE_PATCH,
    )

    assert result.status is RepairChainStatus.DIAGNOSTIC_HOLD
    assert result.no_progress_reason is NoProgressReason.DUPLICATE_PATCH
    assert result.recovery_action is not None
    assert result.state_version == 1
    assert result.diagnostic_hold is not None
    assert result.diagnostic_hold.chain_id == "chain-1"
    assert result.diagnostic_hold.reason is NoProgressReason.DUPLICATE_PATCH
    assert result.diagnostic_hold.attempt_count == 3
    assert result.diagnostic_hold.duplicate_count == 1
    assert result.diagnostic_hold.held_at is not None
    assert "total_attempts" in result.diagnostic_hold.details
    assert "applied_attempts" in result.diagnostic_hold.details

def test_mark_no_progress_preserves_existing_state():
    """mark_no_progress must preserve attempts and other tracking fields."""
    chain = _chain(
        total_attempts=5,
        applied_attempts=2,
        duplicate_count=3,
        state_version=10,
    )

    result = SERVICE.mark_no_progress(
        chain=chain,
        reason=NoProgressReason.ATTEMPT_LIMIT_REACHED,
    )

    assert result.total_attempts == 5
    assert result.applied_attempts == 2
    assert result.duplicate_count == 3
    assert result.recovery_action is RecoveryAction.RECONSTRUCT_FROM_INPUT

# ===================================================================
# 9–10. Rollback / Reconstruct recovery actions
# ===================================================================

def test_recover_rollback_action():
    """Recover with ROLL_BACK action must produce a rollback record."""
    chain = _chain(
        recovery_action=RecoveryAction.ROLL_BACK,
        state_version=5,
    )

    result = SERVICE.recover(
        chain=chain,
        run_id="run-1",
        stage_id="stage-1",
        workspace_fingerprint_before="sha256:before",
    )

    assert result.action is RecoveryAction.ROLL_BACK
    assert result.status is RepairChainStatus.DIAGNOSTIC_HOLD
    assert result.state_version == 6
    assert result.rollback_record is not None
    assert result.rollback_record.rollback_id.startswith("rollback-")
    assert result.rollback_record.chain_id == "chain-1"
    assert result.rollback_record.run_id == "run-1"
    assert result.rollback_record.stage_id == "stage-1"
    assert result.rollback_record.restored_from_fingerprint == "sha256:before"
    assert result.rollback_record.restored_to_fingerprint.startswith("pre-repair-")
    assert result.reconstruction_record is None
    assert result.diagnostic_hold is None  # chain didn't have one

def test_recover_reconstruct_action():
    """Recover with RECONSTRUCT_FROM_INPUT must produce a reconstruction record."""
    chain = _chain(
        recovery_action=RecoveryAction.RECONSTRUCT_FROM_INPUT,
        state_version=3,
    )

    result = SERVICE.recover(
        chain=chain,
        run_id="run-1",
        stage_id="stage-2",
        source_input_fingerprint="sha256:input-v1",
    )

    assert result.action is RecoveryAction.RECONSTRUCT_FROM_INPUT
    assert result.status is RepairChainStatus.DIAGNOSTIC_HOLD
    assert result.state_version == 4
    assert result.reconstruction_record is not None
    assert result.reconstruction_record.reconstruction_id.startswith("recon-")
    assert result.reconstruction_record.chain_id == "chain-1"
    assert result.reconstruction_record.run_id == "run-1"
    assert result.reconstruction_record.stage_id == "stage-2"
    assert result.reconstruction_record.source_input_fingerprint == "sha256:input-v1"
    assert result.reconstruction_record.new_fingerprint.startswith("reconstructed-")
    assert result.rollback_record is None

def test_recover_without_action_raises_error():
    """Recover without a recovery_action must raise RepairProgressError."""
    chain = _chain(recovery_action=None)

    from app.services.repair_progress_service import RepairProgressError

    with pytest.raises(RepairProgressError) as exc:
        SERVICE.recover(
            chain=chain,
            run_id="run-1",
            stage_id="stage-1",
        )

    assert exc.value.code == "NO_RECOVERY_ACTION"

# ===================================================================
# 11. Normalize patch fingerprint (whitespace stripping)
# ===================================================================

def test_normalize_patch_fingerprint_strips_trailing_whitespace():
    content = "line1   \nline2  \nline3"
    result = normalize_patch_fingerprint(content)

    assert result.normalized_content == "line1\nline2\nline3\n"
    assert result.checksum.startswith("sha256:")
    assert result.normalization_version == "v1"

def test_normalize_patch_fingerprint_preserves_significant_whitespace():
    """Leading whitespace / indentation must be preserved."""
    content = "    def foo():\n        pass\n"
    result = normalize_patch_fingerprint(content)

    assert result.normalized_content == "    def foo():\n        pass\n"

def test_normalize_patch_fingerprint_deterministic():
    c1 = normalize_patch_fingerprint("a\nb\nc")
    c2 = normalize_patch_fingerprint("a\nb\nc")
    assert c1.checksum == c2.checksum

def test_normalize_empty_patch():
    result = normalize_patch_fingerprint("")
    assert result.normalized_content == ""
    assert result.checksum.startswith("sha256:")

# ===================================================================
# 12. Compare failure sets (identical, subset, superset)
# ===================================================================

def test_compare_failure_sets_identical():
    comp = compare_failure_sets(
        _failure_set("a", "b"),
        _failure_set("b", "a"),
    )
    assert comp.identical is True
    assert comp.subset is False
    assert comp.superset is False
    assert comp.new_failures == ()
    assert comp.resolved_failures == ()
    assert comp.persistent_failures == ("a", "b")

def test_compare_failure_sets_subset():
    comp = compare_failure_sets(
        _failure_set("a", "b", "c"),
        _failure_set("a", "b"),
    )
    assert comp.identical is False
    assert comp.subset is True
    assert comp.superset is False
    assert comp.new_failures == ()
    assert comp.resolved_failures == ("c",)

def test_compare_failure_sets_superset():
    comp = compare_failure_sets(
        _failure_set("a"),
        _failure_set("a", "b", "c"),
    )
    assert comp.identical is False
    assert comp.subset is False
    assert comp.superset is True
    assert comp.new_failures == ("b", "c")

def test_compare_failure_sets_overlapping_but_neither_sub_nor_super():
    comp = compare_failure_sets(
        _failure_set("a", "b"),
        _failure_set("b", "c"),
    )
    assert comp.identical is False
    assert comp.subset is False
    assert comp.superset is False
    assert comp.new_failures == ("c",)
    assert comp.resolved_failures == ("a",)
    assert comp.persistent_failures == ("b",)

def test_compare_failure_sets_both_empty():
    comp = compare_failure_sets((), ())
    assert comp.identical is True
    assert comp.subset is False
    assert comp.superset is False
    assert comp.new_failures == ()
    assert comp.resolved_failures == ()

def test_compare_failure_sets_checksum():
    comp = compare_failure_sets(
        _failure_set("x", "y"),
        _failure_set("y", "z"),
    )
    assert comp.comparison_checksum.startswith("set-v1-")

# ===================================================================
# 13. Recovery action determination for different reasons
# ===================================================================

class TestRecoveryActionDetermination:
    """Verify _determine_recovery_action maps reasons to correct actions."""

    @staticmethod
    def _action(reason: NoProgressReason) -> RecoveryAction:
        return SERVICE._determine_recovery_action(reason)

    def test_duplicate_patch_rolls_back(self):
        assert self._action(NoProgressReason.DUPLICATE_PATCH) is RecoveryAction.ROLL_BACK

    def test_identical_fingerprint_rolls_back(self):
        assert self._action(NoProgressReason.IDENTICAL_FINGERPRINT) is RecoveryAction.ROLL_BACK

    def test_no_error_delta_reconstructs(self):
        assert self._action(NoProgressReason.NO_ERROR_DELTA) is RecoveryAction.RECONSTRUCT_FROM_INPUT

    def test_attempt_limit_reached_reconstructs(self):
        assert self._action(NoProgressReason.ATTEMPT_LIMIT_REACHED) is RecoveryAction.RECONSTRUCT_FROM_INPUT

    def test_cost_threshold_exceeded_reconstructs(self):
        assert self._action(NoProgressReason.COST_THRESHOLD_EXCEEDED) is RecoveryAction.RECONSTRUCT_FROM_INPUT

    def test_user_cancelled_goes_to_diagnostic_hold(self):
        assert self._action(NoProgressReason.USER_CANCELLED) is RecoveryAction.DIAGNOSTIC_HOLD

# ===================================================================
# Recovery artifact refs
# ===================================================================

def test_recover_rollback_includes_artifact_refs():
    """Rollback recovery must provide artifact references for persistence."""
    chain = _chain(recovery_action=RecoveryAction.ROLL_BACK, state_version=1)

    result = SERVICE.recover(chain=chain, run_id="run-1", stage_id="stage-1")

    assert result.artifact_refs["rollback_record"].startswith("artifact:")
    assert result.artifact_refs["diagnostic_hold"].startswith("artifact:")
    assert result.artifact_refs["reconstruction_record"] == ""

def test_recover_reconstruct_includes_artifact_refs():
    """Reconstruct recovery must provide artifact references for persistence."""
    chain = _chain(recovery_action=RecoveryAction.RECONSTRUCT_FROM_INPUT, state_version=1)

    result = SERVICE.recover(chain=chain, run_id="run-1", stage_id="stage-1")

    assert result.artifact_refs["reconstruction_record"].startswith("artifact:")
    assert result.artifact_refs["diagnostic_hold"].startswith("artifact:")
    assert result.artifact_refs["rollback_record"] == ""

# ===================================================================
# Edge cases: ordering of checks in detect_no_progress
# ===================================================================

def test_detect_duplicate_check_before_attempt_limit():
    """Duplicate patch detection must take priority over attempt limit."""
    fp = normalize_patch_fingerprint(PATCH_A).checksum
    chain = _chain(
        patch_fingerprints=(fp,),
        applied_attempts=MAX_APPLIED_ATTEMPTS,
    )

    is_np, reason, _ = SERVICE.detect_no_progress(
        chain=chain,
        new_patch_content=PATCH_A,
        new_failure_set=_failure_set("err-new"),
        previous_failure_set=_failure_set("err-old"),
    )

    assert reason is NoProgressReason.DUPLICATE_PATCH

def test_detect_identical_fingerprint_before_attempt_limit():
    """Identical failure fingerprint detection must take priority over attempt limit."""
    ffp = SERVICE._compute_failure_fingerprint(_failure_set("err-1"))
    chain = _chain(
        failure_fingerprints=(ffp,),
        applied_attempts=MAX_APPLIED_ATTEMPTS,
    )

    is_np, reason, _ = SERVICE.detect_no_progress(
        chain=chain,
        new_patch_content=PATCH_B,
        new_failure_set=_failure_set("err-1"),
        previous_failure_set=_failure_set("err-old"),
    )

    assert reason is NoProgressReason.IDENTICAL_FINGERPRINT

# ===================================================================
# _compute_failure_fingerprint determinism
# ===================================================================

def test_failure_fingerprint_order_independent():
    fp1 = SERVICE._compute_failure_fingerprint(_failure_set("a", "b"))
    fp2 = SERVICE._compute_failure_fingerprint(_failure_set("b", "a"))
    assert fp1 == fp2
    assert fp1.startswith("sha256:")

# ===================================================================
# get_chain_progress identity
# ===================================================================

def test_get_chain_progress_returns_same_reference():
    chain = _chain()
    assert SERVICE.get_chain_progress(chain=chain) is chain

# ===================================================================
# Adversarial / edge-case tests
# ===================================================================

def test_duplicate_patch_when_already_at_attempt_limit():
    """DUPLICATE_PATCH must be detected even when both limit and duplicate apply."""
    fp = normalize_patch_fingerprint(PATCH_A).checksum
    chain = _chain(
        patch_fingerprints=(fp,),
        applied_attempts=MAX_APPLIED_ATTEMPTS,  # already at limit
    )

    is_np, reason, _ = SERVICE.detect_no_progress(
        chain=chain,
        new_patch_content=PATCH_A,  # same patch → duplicate
        new_failure_set=_failure_set("err-1"),
        previous_failure_set=_failure_set("err-1"),
    )

    assert is_np is True
    # DUPLICATE_PATCH takes priority over ATTEMPT_LIMIT_REACHED
    assert reason is NoProgressReason.DUPLICATE_PATCH, (
        f"Expected DUPLICATE_PATCH, got {reason}"
    )

def test_identical_fingerprint_when_already_at_attempt_limit():
    """IDENTICAL_FINGERPRINT must be detected even when also at limit."""
    ffp = SERVICE._compute_failure_fingerprint(_failure_set("err-1"))
    chain = _chain(
        failure_fingerprints=(ffp,),
        applied_attempts=MAX_APPLIED_ATTEMPTS,  # already at limit
    )

    is_np, reason, _ = SERVICE.detect_no_progress(
        chain=chain,
        new_patch_content=PATCH_B,  # different patch → not duplicate
        new_failure_set=_failure_set("err-1"),  # same failures → identical fingerprint
        previous_failure_set=_failure_set("err-old"),
    )

    assert is_np is True
    assert reason is NoProgressReason.IDENTICAL_FINGERPRINT, (
        f"Expected IDENTICAL_FINGERPRINT, got {reason}"
    )

def test_no_error_delta_before_attempt_limit():
    """NO_ERROR_DELTA must be detected before ATTEMPT_LIMIT_REACHED when both apply."""
    chain = _chain(
        applied_attempts=MAX_APPLIED_ATTEMPTS,  # at limit
    )

    is_np, reason, _ = SERVICE.detect_no_progress(
        chain=chain,
        new_patch_content=PATCH_B,  # different patch → not duplicate
        new_failure_set=_failure_set("err-1"),  # same as previous
        previous_failure_set=_failure_set("err-1"),  # identical non-empty set
    )

    # NO_ERROR_DELTA fires before ATTEMPT_LIMIT_REACHED
    assert is_np is True
    assert reason is NoProgressReason.NO_ERROR_DELTA, (
        f"Expected NO_ERROR_DELTA, got {reason}"
    )

def test_attempt_limit_with_partially_different_errors():
    """ATTEMPT_LIMIT_REACHED fires when limit is hit even with partial error delta."""
    chain = _chain(
        applied_attempts=MAX_APPLIED_ATTEMPTS,  # at limit (3)
    )

    is_np, reason, _ = SERVICE.detect_no_progress(
        chain=chain,
        new_patch_content=PATCH_B,  # different patch
        new_failure_set=_failure_set("err-new-1", "err-new-2"),  # different from previous
        previous_failure_set=_failure_set("err-old-1"),
    )

    # ATTEMPT_LIMIT_REACHED fires because:
    # 1. Not duplicate patch (different content)
    # 2. Not identical fingerprint (new failures differ from history)
    # 3. Not no-error-delta (different sets)
    # 4. Applied_attempts (3) >= MAX_APPLIED_ATTEMPTS (3) → fires
    assert is_np is True
    assert reason is NoProgressReason.ATTEMPT_LIMIT_REACHED, (
        f"Expected ATTEMPT_LIMIT_REACHED, got {reason}"
    )

def test_attempt_limit_at_exact_boundary():
    """Exactly 3 applied attempts must fire ATTEMPT_LIMIT_REACHED."""
    chain = _chain(applied_attempts=3)

    is_np, reason, _ = SERVICE.detect_no_progress(
        chain=chain,
        new_patch_content=PATCH_B,
        new_failure_set=_failure_set("err-1"),
        previous_failure_set=_failure_set("err-old"),
    )

    assert is_np is True
    assert reason is NoProgressReason.ATTEMPT_LIMIT_REACHED

def test_attempt_limit_below_boundary_does_not_fire():
    """Exactly 2 applied attempts must NOT fire ATTEMPT_LIMIT_REACHED."""
    chain = _chain(applied_attempts=2)

    is_np, reason, _ = SERVICE.detect_no_progress(
        chain=chain,
        new_patch_content=PATCH_B,
        new_failure_set=_failure_set("err-1"),
        previous_failure_set=_failure_set("err-old"),
    )

    assert is_np is False
    assert reason is None

def test_normalize_patch_with_windows_line_endings():
    """Windows \\r\\n line endings must normalize to same fingerprint as \\n."""
    unix_content = "line1\nline2\nline3\n"
    windows_content = "line1\r\nline2\r\nline3\r\n"

    fp_unix = normalize_patch_fingerprint(unix_content)
    fp_win = normalize_patch_fingerprint(windows_content)

    assert fp_unix.checksum == fp_win.checksum, (
        "Windows \\r\\n and Unix \\n must produce identical fingerprints"
    )

def test_normalize_patch_with_null_bytes():
    """Null bytes in patch must be preserved (not treated as whitespace)."""
    content = "line1\x00\nline2\n"
    result = normalize_patch_fingerprint(content)

    assert "\x00" in result.normalized_content
    assert result.checksum.startswith("sha256:")

def test_normalize_patch_very_long_content():
    """Extremely long patches must produce a valid checksum without error."""
    long_content = "line\n" * 10_000
    result = normalize_patch_fingerprint(long_content)

    assert len(result.normalized_content) == 5 * 10_000  # "line\n" = 5 chars
    assert result.checksum.startswith("sha256:")
    assert len(result.checksum) == 64 + 7  # "sha256:" + 64 hex chars

def test_normalize_patch_only_newlines():
    """Content that is only newlines must normalize gracefully."""
    content = "\n\n\n"
    result = normalize_patch_fingerprint(content)

    # Each rstrip('') → '' + '\n' → '\n', so normalized is same
    assert result.normalized_content == "\n\n\n"
    assert result.checksum.startswith("sha256:")

def test_failure_set_comparison_empty_current():
    """Empty current set with non-empty previous set is resolved (not identical).
    Note: empty set IS a subset of any set per set theory, so subset=True is correct.
    """
    comp = compare_failure_sets(
        _failure_set("err-a", "err-b"),
        _failure_set(),
    )
    assert comp.identical is False
    assert comp.subset is True  # empty set is subset of any set
    assert comp.superset is False
    assert comp.resolved_failures == ("err-a", "err-b")

def test_failure_set_comparison_empty_previous():
    """Empty previous set with non-empty current set is all new."""
    comp = compare_failure_sets(
        _failure_set(),
        _failure_set("err-a", "err-b"),
    )
    assert comp.identical is False
    assert comp.new_failures == ("err-a", "err-b")

def test_failure_set_comparison_single_item():
    """Single-item sets must compare correctly."""
    comp = compare_failure_sets(
        _failure_set("err-1"),
        _failure_set("err-2"),
    )
    assert comp.identical is False
    assert comp.new_failures == ("err-2",)
    assert comp.resolved_failures == ("err-1",)
    assert comp.persistent_failures == ()

def test_failure_set_comparison_large_set():
    """Large failure sets must compare correctly."""
    large_prev = tuple(f"ERR-{i}" for i in range(100))
    large_curr = tuple(f"ERR-{i}" for i in range(1, 101))  # shifted by 1

    comp = compare_failure_sets(large_prev, large_curr)
    assert comp.identical is False
    assert comp.new_failures == ("ERR-100",)
    assert comp.resolved_failures == ("ERR-0",)
    assert len(comp.persistent_failures) == 99

def test_detect_no_progress_empty_patch_not_duplicate():
    """Empty patch content should not be falsely flagged as duplicate
    (the NO_ERROR_DELTA check should not fire because sets differ).
    """
    fp_empty = normalize_patch_fingerprint("").checksum
    chain = _chain(
        patch_fingerprints=(fp_empty,),
    )

    # A non-empty patch should not match empty fingerprint;
    # failure sets differ so NO_ERROR_DELTA doesn't fire.
    is_np, reason, _ = SERVICE.detect_no_progress(
        chain=chain,
        new_patch_content=PATCH_A,
        new_failure_set=_failure_set("err-new"),
        previous_failure_set=_failure_set("err-old"),
    )

    assert is_np is False
    assert reason is None

def test_detect_no_progress_empty_failure_set_does_not_fire_no_error_delta():
    """Empty new_failure_set with any previous must not trigger NO_ERROR_DELTA."""
    chain = _chain()

    is_np, reason, _ = SERVICE.detect_no_progress(
        chain=chain,
        new_patch_content=PATCH_B,
        new_failure_set=(),
        previous_failure_set=_failure_set("err-1"),
    )

    assert is_np is False
    assert reason is None

def test_recovery_comprehensive_mapping():
    """All NoProgressReason values must map to expected RecoveryAction."""
    from app.services.repair_progress_service import RepairProgressService
    svc = RepairProgressService()

    # ROLL_BACK reasons
    for reason in (NoProgressReason.DUPLICATE_PATCH, NoProgressReason.IDENTICAL_FINGERPRINT):
        action = svc._determine_recovery_action(reason)
        assert action is RecoveryAction.ROLL_BACK, f"{reason} → {action}"

    # RECONSTRUCT_FROM_INPUT reasons
    for reason in (NoProgressReason.NO_ERROR_DELTA, NoProgressReason.ATTEMPT_LIMIT_REACHED,
                   NoProgressReason.COST_THRESHOLD_EXCEEDED):
        action = svc._determine_recovery_action(reason)
        assert action is RecoveryAction.RECONSTRUCT_FROM_INPUT, f"{reason} → {action}"

    # DIAGNOSTIC_HOLD reasons
    action = svc._determine_recovery_action(NoProgressReason.USER_CANCELLED)
    assert action is RecoveryAction.DIAGNOSTIC_HOLD, f"USER_CANCELLED → {action}"

def test_record_attempt_preserves_fingerprint_history():
    """Recording attempts must preserve all fingerprints (no dedup loss)."""
    chain = _chain()

    # Record first attempt with patch A
    chain = SERVICE.record_attempt(
        chain=chain,
        attempt_number=1,
        attempt_id="attempt-1",
        patch_content=PATCH_A,
        failure_signatures=_failure_set("err-1"),
        outcome=AttemptOutcome.APPLIED,
    )
    # Record second attempt with same patch A (duplicate)
    chain = SERVICE.record_attempt(
        chain=chain,
        attempt_number=2,
        attempt_id="attempt-2",
        patch_content=PATCH_A,  # same content
        failure_signatures=_failure_set("err-2"),
        outcome=AttemptOutcome.DUPLICATE,
    )
    # Record third attempt with patch B
    chain = SERVICE.record_attempt(
        chain=chain,
        attempt_number=3,
        attempt_id="attempt-3",
        patch_content=PATCH_B,
        failure_signatures=_failure_set("err-3"),
        outcome=AttemptOutcome.APPLIED,
    )

    assert len(chain.patch_fingerprints) == 2  # 2 unique fingerprints
    assert chain.total_attempts == 3
    assert chain.applied_attempts == 2  # only APPLIED outcomes counted
    assert chain.duplicate_count == 1

# ===================================================================
# Import guard
# ===================================================================
import pytest
