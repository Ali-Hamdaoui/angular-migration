"""Tests for S4-F08 — Preflight, invalidation boundary, error delta, G11 gate, orchestration."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from app.domain.repair_validation import (
    ErrorDelta,
    G11Decision,
    G11GateRecord,
    G11GateStatus,
    G11Package,
    InvalidationBoundary,
    PatchPreflightReport,
    PreflightCheck,
    PreflightStatus,
    RepairValidationResult,
    RepairValidationStatus,
    ValidationRerunReference,
)
from app.services.repair_validation_service import (
    G11GateService,
    InvalidationBoundaryResolver,
    ErrorDeltaCalculator,
    PatchPreflightError,
    PatchPreflightValidator,
    RepairValidationOrchestrator,
)


# ── helpers ────────────────────────────────────────────────────────────────────

_IDS = {
    "preflight": "pf-001",
    "attempt": "attempt-abc",
    "run": "run-999",
    "version_run": "vrun-42",
}


def _fresh_gate_record(**overrides: Any) -> G11GateRecord:
    """Build a minimal PENDING gate record with deterministic defaults."""
    defaults: dict[str, Any] = {
        "gate_id": "G11-abc123def456",
        "run_id": _IDS["run"],
        "attempt_id": _IDS["attempt"],
        "status": G11GateStatus.PENDING,
        "state_version": 0,
        "artifact_set_checksum": "sha256:" + "a" * 64,
        "plan_version": "1.0",
        "workspace_fingerprint": "sha256:" + "b" * 64,
        "decision": G11Decision.PENDING,
        "decision_at": None,
        "actor": "",
        "rationale": "",
        "bound_checksum": "",
        "stale_replay": False,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return G11GateRecord(**defaults)


# ════════════════════════════════════════════════════════════════════════════════
# PatchPreflightValidator
# ════════════════════════════════════════════════════════════════════════════════


class TestPatchPreflightValidator:
    """Patch preflight: fast feedback checks before full validation."""

    def test_profile_match_success(self) -> None:
        validator = PatchPreflightValidator()
        report = validator.run_preflight(
            preflight_id=_IDS["preflight"],
            attempt_id=_IDS["attempt"],
            run_id=_IDS["run"],
            diff_content="--- a/app.ts\n+++ b/app.ts\n@@ -1 +1 @@\n-const x = 1;\n+const x = 2;\n",
            expected_profile_id="angular-18",
            actual_profile_id="angular-18",
            expected_plan_version="v2",
            actual_plan_version="v2",
        )

        assert report.status == PreflightStatus.PASSED
        assert report.profile_match is True
        assert report.plan_version_match is True
        assert len(report.errors) == 0
        assert report.preflight_id == _IDS["preflight"]
        assert report.attempt_id == _IDS["attempt"]
        assert report.run_id == _IDS["run"]
        # All three checks should pass
        passed_checks = [c for c in report.checks if c.passed]
        assert len(passed_checks) == 3

    def test_profile_mismatch_failure(self) -> None:
        validator = PatchPreflightValidator()
        report = validator.run_preflight(
            preflight_id=_IDS["preflight"],
            attempt_id=_IDS["attempt"],
            run_id=_IDS["run"],
            diff_content="--- a/app.ts\n+++ b/app.ts\n@@ -1 +1 @@\n-const x = 1;\n+const x = 2;\n",
            expected_profile_id="angular-18",
            actual_profile_id="react-18",
            expected_plan_version="v2",
            actual_plan_version="v2",
        )

        assert report.status == PreflightStatus.FAILED
        assert report.profile_match is False
        assert report.plan_version_match is True
        assert len(report.errors) == 1
        assert "Profile mismatch" in report.errors[0]
        # Profile check failed
        profile_check = next(c for c in report.checks if c.check_name == "profile_match")
        assert profile_check.passed is False

    def test_plan_version_mismatch(self) -> None:
        validator = PatchPreflightValidator()
        report = validator.run_preflight(
            preflight_id=_IDS["preflight"],
            attempt_id=_IDS["attempt"],
            run_id=_IDS["run"],
            diff_content="--- a/app.ts\n+++ b/app.ts\n@@ -1 +1 @@\n-const x = 1;\n+const x = 2;\n",
            expected_profile_id="angular-18",
            actual_profile_id="angular-18",
            expected_plan_version="v2",
            actual_plan_version="v3",
        )

        assert report.status == PreflightStatus.FAILED
        assert report.profile_match is True
        assert report.plan_version_match is False
        assert len(report.errors) == 1
        assert "Plan version mismatch" in report.errors[0]

    def test_profile_and_plan_both_mismatch(self) -> None:
        """Both profile and plan version mismatch yields two errors."""
        validator = PatchPreflightValidator()
        report = validator.run_preflight(
            preflight_id=_IDS["preflight"],
            attempt_id=_IDS["attempt"],
            run_id=_IDS["run"],
            diff_content="--- a/app.ts\n+++ b/app.ts\n@@ -1 +1 @@\n-const x = 1;\n+const x = 2;\n",
            expected_profile_id="angular-18",
            actual_profile_id="react-18",
            expected_plan_version="v2",
            actual_plan_version="v3",
        )

        assert report.status == PreflightStatus.FAILED
        assert report.profile_match is False
        assert report.plan_version_match is False
        assert len(report.errors) == 2
        assert any("Profile mismatch" in e for e in report.errors)
        assert any("Plan version mismatch" in e for e in report.errors)

    def test_empty_diff_causes_check_failure(self) -> None:
        validator = PatchPreflightValidator()
        report = validator.run_preflight(
            preflight_id=_IDS["preflight"],
            attempt_id=_IDS["attempt"],
            run_id=_IDS["run"],
            diff_content="",
            expected_profile_id="angular-18",
            actual_profile_id="angular-18",
            expected_plan_version="v2",
            actual_plan_version="v2",
        )

        assert report.status == PreflightStatus.FAILED
        diff_check = next(c for c in report.checks if c.check_name == "diff_content_valid")
        assert diff_check.passed is False
        assert "Diff content is empty" in diff_check.detail
        assert any("Diff content is empty" in e for e in report.errors)

    def test_whitespace_only_diff_is_treated_as_empty(self) -> None:
        """Diff content that is only whitespace is treated as invalid."""
        validator = PatchPreflightValidator()
        report = validator.run_preflight(
            preflight_id=_IDS["preflight"],
            attempt_id=_IDS["attempt"],
            run_id=_IDS["run"],
            diff_content="   \n  \t  \n",
            expected_profile_id="angular-18",
            actual_profile_id="angular-18",
            expected_plan_version="v2",
            actual_plan_version="v2",
        )

        assert report.status == PreflightStatus.FAILED
        diff_check = next(c for c in report.checks if c.check_name == "diff_content_valid")
        assert diff_check.passed is False

    def test_report_includes_details_dict(self) -> None:
        """The report's details dict contains the preflight input metadata."""
        validator = PatchPreflightValidator()
        report = validator.run_preflight(
            preflight_id=_IDS["preflight"],
            attempt_id=_IDS["attempt"],
            run_id=_IDS["run"],
            diff_content="--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n",
            expected_profile_id="angular-18",
            actual_profile_id="angular-18",
            expected_plan_version="v2",
            actual_plan_version="v2",
        )

        assert report.details["expected_profile_id"] == "angular-18"
        assert report.details["actual_profile_id"] == "angular-18"
        assert report.details["diff_length"] == len("--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n")
        assert report.generated_at is not None

    def test_report_generated_at_is_set(self) -> None:
        """generated_at should be a datetime (not None)."""
        validator = PatchPreflightValidator()
        report = validator.run_preflight(
            preflight_id=_IDS["preflight"],
            attempt_id=_IDS["attempt"],
            run_id=_IDS["run"],
            diff_content="--- a/app.ts\n+++ b/app.ts\n@@ -1 +1 @@\n-const x = 1;\n+const x = 2;\n",
            expected_profile_id="angular-18",
            actual_profile_id="angular-18",
            expected_plan_version="v2",
            actual_plan_version="v2",
        )

        assert isinstance(report.generated_at, datetime)


# ════════════════════════════════════════════════════════════════════════════════
# InvalidationBoundaryResolver
# ════════════════════════════════════════════════════════════════════════════════


class TestInvalidationBoundaryResolver:
    """Resolve earliest invalidated step from a list of validation steps."""

    def test_finds_earliest_invalidated_step(self) -> None:
        resolver = InvalidationBoundaryResolver()
        steps = [
            {"step_id": "discovery", "status": "PASSED"},
            {"step_id": "baseline", "status": "INVALIDATED"},
            {"step_id": "analysis", "status": "NEEDS_RERUN"},
            {"step_id": "planning", "status": "FAILED"},
            {"step_id": "implementation", "status": "PASSED"},
        ]
        boundary = resolver.resolve(
            validation_run_id=_IDS["version_run"],
            steps=steps,
        )

        assert boundary.validation_run_id == _IDS["version_run"]
        assert boundary.earliest_invalidated_step == "baseline"
        assert "baseline" in boundary.invalidated_steps
        assert "analysis" in boundary.invalidated_steps
        assert "planning" in boundary.invalidated_steps
        assert len(boundary.invalidated_steps) == 3
        assert "Found 3 invalidated step(s)" in boundary.reason

    def test_only_failed_steps_are_included(self) -> None:
        resolver = InvalidationBoundaryResolver()
        steps = [
            {"step_id": "discovery", "status": "PASSED"},
            {"step_id": "baseline", "status": "PASSED"},
        ]
        boundary = resolver.resolve(
            validation_run_id=_IDS["version_run"],
            steps=steps,
        )

        assert len(boundary.invalidated_steps) == 0
        assert boundary.earliest_invalidated_step == ""
        assert "Found 0 invalidated step(s)" in boundary.reason

    def test_only_invalidated_failed_needs_rerun_qualify(self) -> None:
        """Only INVALIDATED, FAILED, or NEEDS_RERUN statuses are included."""
        resolver = InvalidationBoundaryResolver()
        steps = [
            {"step_id": "discovery", "status": "PASSED"},
            {"step_id": "baseline", "status": "SKIPPED"},
            {"step_id": "analysis", "status": "INVALIDATED"},
            {"step_id": "planning", "status": "BLOCKED"},
            {"step_id": "impl", "status": "FAILED"},
            {"step_id": "verify", "status": "NEEDS_RERUN"},
        ]
        boundary = resolver.resolve(
            validation_run_id=_IDS["version_run"],
            steps=steps,
        )

        # SKIPPED and BLOCKED do not count
        assert boundary.earliest_invalidated_step == "analysis"
        assert set(boundary.invalidated_steps) == {"analysis", "impl", "verify"}
        assert len(boundary.invalidated_steps) == 3

    def test_earliest_step_with_any_qualifying_status(self) -> None:
        """Earliest invalidated step is the first qualifying one in list order."""
        resolver = InvalidationBoundaryResolver()
        steps = [
            {"step_id": "verify", "status": "NEEDS_RERUN"},
            {"step_id": "deploy", "status": "INVALIDATED"},
            {"step_id": "validate", "status": "PASSED"},
        ]
        boundary = resolver.resolve(
            validation_run_id=_IDS["version_run"],
            steps=steps,
        )

        assert boundary.earliest_invalidated_step == "verify"

    def test_boundary_checksum_is_deterministic(self) -> None:
        """Same steps produce the same checksum."""
        resolver = InvalidationBoundaryResolver()
        steps = [
            {"step_id": "discovery", "status": "INVALIDATED"},
        ]
        b1 = resolver.resolve(validation_run_id=_IDS["version_run"], steps=steps)
        b2 = resolver.resolve(validation_run_id=_IDS["version_run"], steps=steps)

        assert b1.boundary_checksum == b2.boundary_checksum
        assert b1.boundary_checksum.startswith("sha256:")

    def test_differs_for_different_invalidated_steps(self) -> None:
        """Different invalidated lists give different checksums."""
        resolver = InvalidationBoundaryResolver()
        steps_a = [{"step_id": "discovery", "status": "INVALIDATED"}]
        steps_b = [{"step_id": "baseline", "status": "INVALIDATED"}]
        b1 = resolver.resolve(validation_run_id=_IDS["version_run"], steps=steps_a)
        b2 = resolver.resolve(validation_run_id=_IDS["version_run"], steps=steps_b)

        assert b1.boundary_checksum != b2.boundary_checksum


# ════════════════════════════════════════════════════════════════════════════════
# ErrorDeltaCalculator
# ════════════════════════════════════════════════════════════════════════════════


class TestErrorDeltaCalculator:
    """Compute new, resolved, and persistent error deltas."""

    def test_all_new_errors(self) -> None:
        calc = ErrorDeltaCalculator()
        delta = calc.calculate(
            previous_errors=[],
            current_errors=["ERR-001", "ERR-002"],
        )

        assert delta.new_errors == ("ERR-001", "ERR-002")
        assert delta.resolved_errors == ()
        assert delta.persistent_errors == ()
        assert delta.previous_errors == ()
        assert delta.current_errors == ("ERR-001", "ERR-002")

    def test_all_resolved_errors(self) -> None:
        calc = ErrorDeltaCalculator()
        delta = calc.calculate(
            previous_errors=["ERR-001", "ERR-002"],
            current_errors=[],
        )

        assert delta.new_errors == ()
        assert delta.resolved_errors == ("ERR-001", "ERR-002")
        assert delta.persistent_errors == ()

    def test_persistent_errors(self) -> None:
        calc = ErrorDeltaCalculator()
        delta = calc.calculate(
            previous_errors=["ERR-001", "ERR-002"],
            current_errors=["ERR-001", "ERR-002", "ERR-003"],
        )

        assert delta.persistent_errors == ("ERR-001", "ERR-002")
        assert delta.new_errors == ("ERR-003",)
        assert delta.resolved_errors == ()

    def test_mixed_delta(self) -> None:
        calc = ErrorDeltaCalculator()
        delta = calc.calculate(
            previous_errors=["ERR-A", "ERR-B", "ERR-C"],
            current_errors=["ERR-B", "ERR-C", "ERR-D"],
        )

        # ERR-A resolved; ERR-D new; ERR-B, ERR-C persistent
        assert set(delta.resolved_errors) == {"ERR-A"}
        assert set(delta.new_errors) == {"ERR-D"}
        assert set(delta.persistent_errors) == {"ERR-B", "ERR-C"}

    def test_no_changes(self) -> None:
        calc = ErrorDeltaCalculator()
        delta = calc.calculate(
            previous_errors=["ERR-001", "ERR-002"],
            current_errors=["ERR-001", "ERR-002"],
        )

        assert delta.new_errors == ()
        assert delta.resolved_errors == ()
        assert set(delta.persistent_errors) == {"ERR-001", "ERR-002"}

    def test_delta_checksum_is_deterministic(self) -> None:
        calc = ErrorDeltaCalculator()
        d1 = calc.calculate(previous_errors=["A", "B"], current_errors=["B", "C"])
        d2 = calc.calculate(previous_errors=["A", "B"], current_errors=["B", "C"])

        assert d1.delta_checksum == d2.delta_checksum
        assert d1.delta_checksum.startswith("sha256:")

    def test_delta_checksum_changes_with_different_errors(self) -> None:
        calc = ErrorDeltaCalculator()
        d1 = calc.calculate(previous_errors=["A"], current_errors=["B"])
        d2 = calc.calculate(previous_errors=["A"], current_errors=["C"])

        assert d1.delta_checksum != d2.delta_checksum

    def test_duplicates_are_deduplicated(self) -> None:
        """Duplicate error codes in either list are treated as unique via set."""
        calc = ErrorDeltaCalculator()
        delta = calc.calculate(
            previous_errors=["ERR-001", "ERR-001"],
            current_errors=["ERR-002", "ERR-002"],
        )

        assert delta.new_errors == ("ERR-002",)
        assert delta.resolved_errors == ("ERR-001",)
        assert delta.persistent_errors == ()

    def test_errors_are_sorted_alphabetically(self) -> None:
        """New/resolved/persistent errors come back sorted."""
        calc = ErrorDeltaCalculator()
        delta = calc.calculate(
            previous_errors=["Z-ERR", "A-ERR"],
            current_errors=["A-ERR", "M-ERR"],
        )

        assert delta.resolved_errors == ("Z-ERR",)
        assert delta.new_errors == ("M-ERR",)
        assert delta.persistent_errors == ("A-ERR",)


# ════════════════════════════════════════════════════════════════════════════════
# G11GateService
# ════════════════════════════════════════════════════════════════════════════════


class TestG11GateService:
    """Create, bind, decide, verify G11 gate lifecycle."""

    def test_create_gate_returns_package_with_binding(self) -> None:
        svc = G11GateService()
        pkg = svc.create_gate(
            run_id=_IDS["run"],
            attempt_id=_IDS["attempt"],
            state_version=0,
            artifact_set_checksum="sha256:" + "a" * 64,
            plan_version="1.0",
            workspace_fingerprint="sha256:" + "b" * 64,
            preflight_report_ref="artifact:pf-001/preflight-report",
        )

        assert pkg.gate_id.startswith("G11-")
        assert pkg.run_id == _IDS["run"]
        assert pkg.attempt_id == _IDS["attempt"]
        assert pkg.state_version == 0
        assert pkg.artifact_set_checksum == "sha256:" + "a" * 64
        assert pkg.plan_version == "1.0"
        assert pkg.workspace_fingerprint == "sha256:" + "b" * 64
        assert pkg.preflight_report_ref == "artifact:pf-001/preflight-report"
        assert pkg.decision == G11Decision.PENDING
        assert pkg.bound_checksum != ""
        assert pkg.bound_checksum.startswith("sha256:")
        assert pkg.created_at is not None

    def test_create_gate_binds_checksum_to_run_attempt_state(self) -> None:
        """Same parameters produce same bound_checksum (deterministic)."""
        svc = G11GateService()
        pkg1 = svc.create_gate(
            run_id=_IDS["run"],
            attempt_id=_IDS["attempt"],
            state_version=0,
            artifact_set_checksum="sha256:" + "a" * 64,
        )
        pkg2 = svc.create_gate(
            run_id=_IDS["run"],
            attempt_id=_IDS["attempt"],
            state_version=0,
            artifact_set_checksum="sha256:" + "a" * 64,
        )

        # Gate IDs differ (uuid each time) but bound_checksum is deterministic
        assert pkg1.gate_id != pkg2.gate_id
        assert pkg1.bound_checksum == pkg2.bound_checksum

    def test_create_gate_record_returns_pending_record(self) -> None:
        svc = G11GateService()
        record = svc.create_gate_record(
            gate_id="G11-abc123def456",
            run_id=_IDS["run"],
            attempt_id=_IDS["attempt"],
            state_version=0,
            artifact_set_checksum="sha256:" + "a" * 64,
            plan_version="1.0",
            workspace_fingerprint="sha256:" + "b" * 64,
        )

        assert record.gate_id == "G11-abc123def456"
        assert record.status == G11GateStatus.PENDING
        assert record.decision == G11Decision.PENDING
        assert record.run_id == _IDS["run"]
        assert record.attempt_id == _IDS["attempt"]
        assert record.state_version == 0
        assert record.artifact_set_checksum == "sha256:" + "a" * 64
        assert record.created_at is not None
        assert record.updated_at is not None

    def test_decide_approves_gate(self) -> None:
        svc = G11GateService()
        record = _fresh_gate_record()
        result = svc.decide(
            gate_record=record,
            decision=G11Decision.APPROVED,
            actor="operator",
            rationale="All checks pass",
            current_state_version=record.state_version,
            current_artifact_checksum=record.artifact_set_checksum,
            current_workspace_fingerprint=record.workspace_fingerprint,
        )

        assert result.status == G11GateStatus.APPROVED
        assert result.decision == G11Decision.APPROVED
        assert result.actor == "operator"
        assert result.rationale == "All checks pass"
        assert result.stale_replay is False
        assert result.decision_at is not None

    def test_decide_rejects_gate(self) -> None:
        svc = G11GateService()
        record = _fresh_gate_record()
        result = svc.decide(
            gate_record=record,
            decision=G11Decision.REJECTED,
            actor="reviewer",
            rationale="Security concern",
            current_state_version=record.state_version,
            current_artifact_checksum=record.artifact_set_checksum,
            current_workspace_fingerprint=record.workspace_fingerprint,
        )

        assert result.status == G11GateStatus.REJECTED
        assert result.decision == G11Decision.REJECTED
        assert result.actor == "reviewer"
        assert result.rationale == "Security concern"
        assert result.stale_replay is False

    def test_decide_modification_requested(self) -> None:
        svc = G11GateService()
        record = _fresh_gate_record()
        result = svc.decide(
            gate_record=record,
            decision=G11Decision.MODIFICATION_REQUESTED,
            actor="reviewer",
            rationale="Please refactor",
            current_state_version=record.state_version,
            current_artifact_checksum=record.artifact_set_checksum,
            current_workspace_fingerprint=record.workspace_fingerprint,
        )

        assert result.status == G11GateStatus.MODIFICATION_REQUESTED
        assert result.decision == G11Decision.MODIFICATION_REQUESTED
        assert result.stale_replay is False

    def test_stale_detection_when_state_version_changes(self) -> None:
        svc = G11GateService()
        record = _fresh_gate_record(state_version=0)
        result = svc.decide(
            gate_record=record,
            decision=G11Decision.APPROVED,
            actor="operator",
            current_state_version=1,  # changed
            current_artifact_checksum=record.artifact_set_checksum,
            current_workspace_fingerprint=record.workspace_fingerprint,
        )

        assert result.status == G11GateStatus.STALE
        assert result.decision == G11Decision.STALE
        assert result.stale_replay is True
        assert "Bound state changed" in result.rationale

    def test_stale_detection_when_artifact_checksum_changes(self) -> None:
        svc = G11GateService()
        record = _fresh_gate_record()
        result = svc.decide(
            gate_record=record,
            decision=G11Decision.APPROVED,
            actor="operator",
            current_state_version=record.state_version,
            current_artifact_checksum="sha256:" + "d" * 64,  # changed
            current_workspace_fingerprint=record.workspace_fingerprint,
        )

        assert result.status == G11GateStatus.STALE

    def test_stale_detection_when_workspace_fingerprint_changes(self) -> None:
        svc = G11GateService()
        record = _fresh_gate_record()
        result = svc.decide(
            gate_record=record,
            decision=G11Decision.APPROVED,
            actor="operator",
            current_state_version=record.state_version,
            current_artifact_checksum=record.artifact_set_checksum,
            current_workspace_fingerprint="sha256:" + "e" * 64,  # changed
        )

        assert result.status == G11GateStatus.STALE

    def test_decide_does_not_check_fingerprint_when_current_empty(self) -> None:
        """If current_workspace_fingerprint is empty/falsy, skip fp comparison."""
        svc = G11GateService()
        record = _fresh_gate_record(workspace_fingerprint="sha256:" + "b" * 64)
        result = svc.decide(
            gate_record=record,
            decision=G11Decision.APPROVED,
            actor="operator",
            current_state_version=record.state_version,
            current_artifact_checksum=record.artifact_set_checksum,
            current_workspace_fingerprint="",  # empty — skip comparison
        )

        assert result.status == G11GateStatus.APPROVED

    def test_verify_approved_passes(self) -> None:
        svc = G11GateService()
        record = _fresh_gate_record(status=G11GateStatus.APPROVED, decision=G11Decision.APPROVED)
        ok, msg = svc.verify_gate_for_transition(record)

        assert ok is True
        assert "approved" in msg

    def test_verify_pending_fails(self) -> None:
        svc = G11GateService()
        record = _fresh_gate_record(status=G11GateStatus.PENDING)
        ok, msg = svc.verify_gate_for_transition(record)

        assert ok is False
        assert "pending" in msg

    def test_verify_rejected_fails(self) -> None:
        svc = G11GateService()
        record = _fresh_gate_record(status=G11GateStatus.REJECTED, decision=G11Decision.REJECTED)
        ok, msg = svc.verify_gate_for_transition(record)

        assert ok is False
        assert "rejected" in msg

    def test_verify_stale_fails(self) -> None:
        svc = G11GateService()
        record = _fresh_gate_record(status=G11GateStatus.STALE, decision=G11Decision.STALE, stale_replay=True)
        ok, msg = svc.verify_gate_for_transition(record)

        assert ok is False
        assert "stale" in msg

    def test_verify_expired_fails(self) -> None:
        svc = G11GateService()
        record = _fresh_gate_record(status=G11GateStatus.EXPIRED, decision=G11Decision.EXPIRED)
        ok, msg = svc.verify_gate_for_transition(record)

        assert ok is False
        assert "expired" in msg

    def test_verify_modification_requested_fails(self) -> None:
        svc = G11GateService()
        record = _fresh_gate_record(
            status=G11GateStatus.MODIFICATION_REQUESTED,
            decision=G11Decision.MODIFICATION_REQUESTED,
        )
        ok, msg = svc.verify_gate_for_transition(record)

        assert ok is False
        assert "modification" in msg

    # ════════════════════════════════════════════════════════════════════
    # Adversarial / edge-case tests for G11 gate
    # ════════════════════════════════════════════════════════════════════

    def test_stale_approval_after_state_change_replay(self) -> None:
        """Replaying an approve decision after state change must mark STALE.

        This simulates an attacker or stale client trying to reuse an old
        approval after the system state has moved on.
        """
        svc = G11GateService()
        record = _fresh_gate_record(state_version=0)

        # First approval
        result = svc.decide(
            gate_record=record,
            decision=G11Decision.APPROVED,
            actor="operator",
            current_state_version=0,
            current_artifact_checksum=record.artifact_set_checksum,
            current_workspace_fingerprint=record.workspace_fingerprint,
            current_plan_version=record.plan_version,
        )
        assert result.status == G11GateStatus.APPROVED

        # Now state changes (e.g. new repair attempt)
        # Replaying the same approval decision with stale state
        replay_result = svc.decide(
            gate_record=record,  # original record, state_version=0
            decision=G11Decision.APPROVED,
            actor="attacker",
            current_state_version=1,  # state has advanced
            current_artifact_checksum=record.artifact_set_checksum,
            current_workspace_fingerprint=record.workspace_fingerprint,
            current_plan_version=record.plan_version,
        )
        assert replay_result.status == G11GateStatus.STALE
        assert replay_result.stale_replay is True
        assert replay_result.decision == G11Decision.STALE
        assert "Bound state changed" in replay_result.rationale

    def test_stale_detection_when_plan_version_changes(self) -> None:
        """Plan version change must also trigger stale detection."""
        svc = G11GateService()
        record = _fresh_gate_record(plan_version="1.0")
        result = svc.decide(
            gate_record=record,
            decision=G11Decision.APPROVED,
            actor="operator",
            current_state_version=record.state_version,
            current_artifact_checksum=record.artifact_set_checksum,
            current_workspace_fingerprint=record.workspace_fingerprint,
            current_plan_version="2.0",  # changed
        )

        assert result.status == G11GateStatus.STALE
        assert result.decision == G11Decision.STALE
        assert result.stale_replay is True

    def test_verify_expired_gate_with_ttl_check(self) -> None:
        """verify_gate_for_transition must detect expired gates via TTL."""
        svc = G11GateService()
        import datetime as dt
        old_time = datetime.now(UTC) - dt.timedelta(seconds=10)
        record = _fresh_gate_record(
            status=G11GateStatus.APPROVED,
            decision=G11Decision.APPROVED,
            decision_at=old_time,
        )

        # TTL of 1s — gate is 10s old, should be expired
        ok, msg = svc.verify_gate_for_transition(record, ttl_seconds=1)
        assert ok is False
        assert "expired" in msg
        assert "TTL" in msg

    def test_verify_ttl_disabled_with_zero(self) -> None:
        """Passing ttl_seconds=0 must disable TTL check even for old gates."""
        svc = G11GateService()
        import datetime as dt
        old_time = datetime.now(UTC) - dt.timedelta(hours=48)
        record = _fresh_gate_record(
            status=G11GateStatus.APPROVED,
            decision=G11Decision.APPROVED,
            decision_at=old_time,
        )

        ok, msg = svc.verify_gate_for_transition(record, ttl_seconds=0)
        assert ok is True
        assert "approved" in msg

    def test_verify_approved_gate_within_ttl(self) -> None:
        """A recently approved gate should pass TTL check."""
        svc = G11GateService()
        record = _fresh_gate_record(
            status=G11GateStatus.APPROVED,
            decision=G11Decision.APPROVED,
            decision_at=datetime.now(UTC),
        )

        ok, msg = svc.verify_gate_for_transition(record, ttl_seconds=3600)
        assert ok is True
        assert "approved" in msg

    def test_verify_approved_no_decision_at_skips_ttl(self) -> None:
        """If decision_at is None, TTL check must be skipped."""
        svc = G11GateService()
        record = _fresh_gate_record(
            status=G11GateStatus.APPROVED,
            decision=G11Decision.APPROVED,
            decision_at=None,
        )

        ok, msg = svc.verify_gate_for_transition(record, ttl_seconds=1)
        assert ok is True
        assert "approved" in msg

    def test_bound_checksum_includes_plan_and_workspace(self) -> None:
        """Bound checksum must be sensitive to plan_version and workspace_fingerprint."""
        svc = G11GateService()
        pkg1 = svc.create_gate(
            run_id=_IDS["run"],
            attempt_id=_IDS["attempt"],
            state_version=0,
            artifact_set_checksum="sha256:" + "a" * 64,
            plan_version="1.0",
            workspace_fingerprint="fp-a",
        )
        pkg2 = svc.create_gate(
            run_id=_IDS["run"],
            attempt_id=_IDS["attempt"],
            state_version=0,
            artifact_set_checksum="sha256:" + "a" * 64,
            plan_version="2.0",  # different plan version
            workspace_fingerprint="fp-a",
        )
        pkg3 = svc.create_gate(
            run_id=_IDS["run"],
            attempt_id=_IDS["attempt"],
            state_version=0,
            artifact_set_checksum="sha256:" + "a" * 64,
            plan_version="1.0",
            workspace_fingerprint="fp-b",  # different workspace fingerprint
        )

        assert pkg1.bound_checksum != pkg2.bound_checksum, (
            "Different plan_version must produce different bound_checksum"
        )
        assert pkg1.bound_checksum != pkg3.bound_checksum, (
            "Different workspace_fingerprint must produce different bound_checksum"
        )


# ════════════════════════════════════════════════════════════════════════════════
# RepairValidationOrchestrator
# ════════════════════════════════════════════════════════════════════════════════


class TestRepairValidationOrchestrator:
    """Full validation orchestration: preflight → rerun → G11."""

    def test_happy_path(self) -> None:
        """All phases succeed: preflight passes, boundary resolved, delta computed,
        rerun ref created, G11 gate built and recorded."""
        orchestrator = RepairValidationOrchestrator()
        result = orchestrator.validate_repair(
            attempt_id=_IDS["attempt"],
            run_id=_IDS["run"],
            preflight_id=_IDS["preflight"],
            diff_content="--- a/app.ts\n+++ b/app.ts\n@@ -1 +1 @@\n-const x = 1;\n+const x = 2;\n",
            expected_profile_id="angular-18",
            actual_profile_id="angular-18",
            expected_plan_version="v2",
            actual_plan_version="v2",
            validation_run_id=_IDS["version_run"],
            steps=[
                {"step_id": "discovery", "status": "PASSED"},
                {"step_id": "baseline", "status": "FAILED"},
                {"step_id": "analysis", "status": "PASSED"},
            ],
            previous_errors=["ERR-001"],
            current_errors=["ERR-002"],
            artifact_set_checksum="sha256:" + "a" * 64,
            plan_version="1.0",
            workspace_fingerprint="sha256:" + "b" * 64,
        )

        # Overall status should be WAITING_G11 after completion
        assert result.status == RepairValidationStatus.WAITING_G11
        assert result.run_id == _IDS["run"]
        assert result.attempt_id == _IDS["attempt"]
        assert result.state_version == 0
        assert result.idempotent_replay is False

        # Phase 1 — Preflight passed
        assert result.preflight_report is not None
        assert result.preflight_report.status == PreflightStatus.PASSED
        assert result.preflight_report.profile_match is True

        # Phase 2 — Invalidation boundary
        assert result.invalidation_boundary is not None
        assert result.invalidation_boundary.earliest_invalidated_step == "baseline"

        # Phase 3 — Error delta
        assert result.error_delta is not None
        assert "ERR-001" in result.error_delta.resolved_errors
        assert "ERR-002" in result.error_delta.new_errors

        # Phase 4 — Rerun reference
        assert result.rerun_reference is not None
        assert result.rerun_reference.run_id == _IDS["run"]
        assert result.rerun_reference.attempt_id == _IDS["attempt"]
        # passed=True because current_errors list not empty ... wait, current_errors is ["ERR-002"],
        # so len != 0, so passed should be False
        assert result.rerun_reference.passed is False

        # Phase 5 — G11 gate
        assert result.g11_package is not None
        assert result.g11_package.run_id == _IDS["run"]
        assert result.g11_package.gate_id.startswith("G11-")
        assert result.g11_record is not None
        assert result.g11_record.status == G11GateStatus.PENDING

        # Artifact refs for each phase
        assert "preflight_report" in result.artifact_refs
        assert "invalidation_boundary" in result.artifact_refs
        assert "error_delta" in result.artifact_refs
        assert "rerun_reference" in result.artifact_refs
        assert "g11_package" in result.artifact_refs

    def test_happy_path_with_no_errors_sets_rerun_passed_true(self) -> None:
        """When current_errors is empty, rerun_reference.passed is True."""
        orchestrator = RepairValidationOrchestrator()
        result = orchestrator.validate_repair(
            attempt_id=_IDS["attempt"],
            run_id=_IDS["run"],
            preflight_id=_IDS["preflight"],
            diff_content="--- a/app.ts\n+++ b/app.ts\n@@ -1 +1 @@\n-const x = 1;\n+const x = 2;\n",
            expected_profile_id="angular-18",
            actual_profile_id="angular-18",
            expected_plan_version="v2",
            actual_plan_version="v2",
            validation_run_id=_IDS["version_run"],
            steps=[],
            previous_errors=[],
            current_errors=[],
            artifact_set_checksum="sha256:" + "a" * 64,
        )

        assert result.status == RepairValidationStatus.WAITING_G11
        assert result.rerun_reference is not None
        assert result.rerun_reference.passed is True

    def test_preflight_failure_returns_early(self) -> None:
        """When preflight fails, result is PREFLIGHT_FAILED with failure_evidence."""
        orchestrator = RepairValidationOrchestrator()
        result = orchestrator.validate_repair(
            attempt_id=_IDS["attempt"],
            run_id=_IDS["run"],
            preflight_id=_IDS["preflight"],
            diff_content="",
            expected_profile_id="angular-18",
            actual_profile_id="react-18",  # mismatch
            expected_plan_version="v2",
            actual_plan_version="v2",
            validation_run_id=_IDS["version_run"],
            steps=[],
            previous_errors=[],
            current_errors=[],
            artifact_set_checksum="sha256:" + "a" * 64,
        )

        assert result.status == RepairValidationStatus.PREFLIGHT_FAILED
        assert result.preflight_report is not None
        assert result.preflight_report.status == PreflightStatus.FAILED
        assert result.preflight_report.profile_match is False

        # No later phases should be populated
        assert result.invalidation_boundary is None
        assert result.error_delta is None
        assert result.rerun_reference is None
        assert result.g11_package is None
        assert result.g11_record is None

        # Failure evidence present
        assert result.failure_evidence is not None
        assert result.failure_evidence["reason"] == "Preflight validation failed"
        assert len(result.failure_evidence["errors"]) > 0

        # State version is 0 (default)
        assert result.state_version == 0

    def test_empty_diff_and_mismatch_produce_multiple_preflight_errors(self) -> None:
        """Multiple preflight issues all appear in failure evidence."""
        orchestrator = RepairValidationOrchestrator()
        result = orchestrator.validate_repair(
            attempt_id=_IDS["attempt"],
            run_id=_IDS["run"],
            preflight_id=_IDS["preflight"],
            diff_content="",
            expected_profile_id="angular-18",
            actual_profile_id="react-18",
            expected_plan_version="v2",
            actual_plan_version="v3",
            validation_run_id=_IDS["version_run"],
            steps=[],
            previous_errors=[],
            current_errors=[],
            artifact_set_checksum="sha256:" + "a" * 64,
        )

        assert result.status == RepairValidationStatus.PREFLIGHT_FAILED
        assert result.failure_evidence is not None
        assert len(result.failure_evidence["errors"]) == 3  # profile, version, diff
        assert result.preflight_report is not None
        assert len(result.preflight_report.errors) == 3

    def test_orchestrator_uses_injected_dependencies(self) -> None:
        """Custom services can be injected into the orchestrator."""
        tracked: list[str] = []

        class TrackingValidator(PatchPreflightValidator):
            def run_preflight(self, **kwargs: Any) -> PatchPreflightReport:
                tracked.append("preflight")
                # Return passing report
                return PatchPreflightReport(
                    preflight_id=kwargs["preflight_id"],
                    attempt_id=kwargs["attempt_id"],
                    run_id=kwargs["run_id"],
                    status=PreflightStatus.PASSED,
                    profile_match=True,
                    plan_version_match=True,
                    checks=(
                        PreflightCheck(check_name="profile_match", passed=True),
                        PreflightCheck(check_name="plan_version_match", passed=True),
                        PreflightCheck(check_name="diff_content_valid", passed=True),
                    ),
                    details={},
                    generated_at=datetime.now(UTC),
                )

        class TrackingResolver(InvalidationBoundaryResolver):
            def resolve(self, **kwargs: Any) -> InvalidationBoundary:
                tracked.append("resolve")
                return InvalidationBoundary(validation_run_id=kwargs["validation_run_id"])

        class TrackingDelta(ErrorDeltaCalculator):
            def calculate(self, **kwargs: Any) -> ErrorDelta:
                tracked.append("delta")
                return ErrorDelta()

        class TrackingGate(G11GateService):
            def create_gate(self, **kwargs: Any) -> G11Package:
                tracked.append("create_gate")
                return G11Package(
                    gate_id="G11-injected",
                    run_id=kwargs["run_id"],
                    attempt_id=kwargs["attempt_id"],
                    state_version=kwargs["state_version"],
                    artifact_set_checksum=kwargs["artifact_set_checksum"],
                    created_at=datetime.now(UTC),
                )

            def create_gate_record(self, **kwargs: Any) -> G11GateRecord:
                tracked.append("create_record")
                return G11GateRecord(
                    gate_id=kwargs["gate_id"],
                    run_id=kwargs["run_id"],
                    attempt_id=kwargs["attempt_id"],
                    state_version=kwargs["state_version"],
                    artifact_set_checksum=kwargs["artifact_set_checksum"],
                    status=G11GateStatus.PENDING,
                    decision=G11Decision.PENDING,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )

        orchestrator = RepairValidationOrchestrator(
            preflight_validator=TrackingValidator(),
            boundary_resolver=TrackingResolver(),
            delta_calculator=TrackingDelta(),
            gate_service=TrackingGate(),
        )

        result = orchestrator.validate_repair(
            attempt_id=_IDS["attempt"],
            run_id=_IDS["run"],
            preflight_id=_IDS["preflight"],
            diff_content="--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n",
            expected_profile_id="angular-18",
            actual_profile_id="angular-18",
            expected_plan_version="v2",
            actual_plan_version="v2",
            validation_run_id=_IDS["version_run"],
            steps=[],
            previous_errors=[],
            current_errors=[],
            artifact_set_checksum="sha256:" + "a" * 64,
        )

        assert result.status == RepairValidationStatus.WAITING_G11
        assert tracked == ["preflight", "resolve", "delta", "create_gate", "create_record"]
        assert result.g11_package is not None
        assert result.g11_package.gate_id == "G11-injected"

    def test_idempotent_replay_defaults_to_false(self) -> None:
        """New validation results are not idempotent replays."""
        orchestrator = RepairValidationOrchestrator()
        result = orchestrator.validate_repair(
            attempt_id=_IDS["attempt"],
            run_id=_IDS["run"],
            preflight_id=_IDS["preflight"],
            diff_content="--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n",
            expected_profile_id="angular-18",
            actual_profile_id="angular-18",
            expected_plan_version="v2",
            actual_plan_version="v2",
            validation_run_id=_IDS["version_run"],
            steps=[],
            previous_errors=[],
            current_errors=[],
            artifact_set_checksum="sha256:" + "a" * 64,
        )

        assert result.idempotent_replay is False
