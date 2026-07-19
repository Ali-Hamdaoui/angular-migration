"""Application service for patch preflight, validation rerun, and G11 gate.

Patch preflight is fast feedback only; the repair must use the same
ExecutionProfile and normal stage pipeline.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

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

# Time-to-live for G11 gate approvals (24 hours by default)
G11_GATE_TTL_SECONDS: int = 86400


class PatchPreflightError(ValueError):
    """Raised when preflight validation fails."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class G11GateError(ValueError):
    """Raised when G11 gate operations fail."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class PatchPreflightValidator:
    """Run quick preflight checks before resuming the full validation pipeline."""

    def run_preflight(
        self,
        *,
        preflight_id: str,
        attempt_id: str,
        run_id: str,
        diff_content: str,
        expected_profile_id: str,
        actual_profile_id: str,
        expected_plan_version: str,
        actual_plan_version: str,
    ) -> PatchPreflightReport:
        """Run preflight checks and return a report."""
        checks: list[PreflightCheck] = []

        # Profile match
        profile_match = expected_profile_id == actual_profile_id
        checks.append(PreflightCheck(
            check_name="profile_match",
            passed=profile_match,
            detail=f"expected: {expected_profile_id}, actual: {actual_profile_id}",
        ))

        # Plan version match
        plan_version_match = expected_plan_version == actual_plan_version
        checks.append(PreflightCheck(
            check_name="plan_version_match",
            passed=plan_version_match,
            detail=f"expected: {expected_plan_version}, actual: {actual_plan_version}",
        ))

        # Diff validity (quick check)
        diff_valid = bool(diff_content and diff_content.strip())
        checks.append(PreflightCheck(
            check_name="diff_content_valid",
            passed=diff_valid,
            detail="Diff content is empty" if not diff_valid else "Diff content OK",
        ))

        errors: list[str] = []
        warnings: list[str] = []

        if not profile_match:
            errors.append("Profile mismatch between expected and actual execution profile")
        if not plan_version_match:
            errors.append("Plan version mismatch")
        if not diff_valid:
            errors.append("Diff content is empty")

        if not errors and not warnings:
            status = PreflightStatus.PASSED
        elif errors:
            status = PreflightStatus.FAILED
        else:
            status = PreflightStatus.PASSED  # Warnings only

        return PatchPreflightReport(
            preflight_id=preflight_id,
            attempt_id=attempt_id,
            run_id=run_id,
            status=status,
            profile_match=profile_match,
            plan_version_match=plan_version_match,
            checks=tuple(checks),
            warnings=tuple(warnings),
            errors=tuple(errors),
            details={
                "expected_profile_id": expected_profile_id,
                "actual_profile_id": actual_profile_id,
                "expected_plan_version": expected_plan_version,
                "actual_plan_version": actual_plan_version,
                "diff_length": len(diff_content),
            },
            generated_at=datetime.now(UTC),
        )


class InvalidationBoundaryResolver:
    """Resolve the earliest invalidated validation boundary after a repair."""

    def resolve(
        self,
        *,
        validation_run_id: str,
        steps: list[dict[str, Any]],
    ) -> InvalidationBoundary:
        """Find the earliest step that needs revalidation."""
        invalidated: list[str] = []
        for step in steps:
            step_id = step.get("step_id", "")
            status = step.get("status", "")
            if status in ("INVALIDATED", "FAILED", "NEEDS_RERUN"):
                invalidated.append(step_id)

        return InvalidationBoundary(
            validation_run_id=validation_run_id,
            invalidated_steps=tuple(invalidated),
            earliest_invalidated_step=invalidated[0] if invalidated else "",
            reason=f"Found {len(invalidated)} invalidated step(s) after repair",
            boundary_checksum="sha256:" + hashlib.sha256(
                str(invalidated).encode("utf-8")
            ).hexdigest(),
        )


class ErrorDeltaCalculator:
    """Calculate the delta between previous and current validation errors."""

    def calculate(
        self,
        *,
        previous_errors: list[str],
        current_errors: list[str],
    ) -> ErrorDelta:
        """Compute the error delta between two validation runs."""
        prev_set = set(previous_errors)
        curr_set = set(current_errors)

        return ErrorDelta(
            previous_errors=tuple(previous_errors),
            current_errors=tuple(current_errors),
            new_errors=tuple(sorted(curr_set - prev_set)),
            resolved_errors=tuple(sorted(prev_set - curr_set)),
            persistent_errors=tuple(sorted(prev_set & curr_set)),
            delta_checksum="sha256:" + hashlib.sha256(
                f"{sorted(prev_set)}-{sorted(curr_set)}".encode("utf-8")
            ).hexdigest(),
        )


class G11GateService:
    """Manage G11 gate — create, bind, decide, verify."""

    def create_gate(
        self,
        *,
        run_id: str,
        attempt_id: str,
        state_version: int,
        artifact_set_checksum: str,
        plan_version: str = "",
        workspace_fingerprint: str = "",
        preflight_report_ref: str = "",
    ) -> G11Package:
        """Create a new G11 gate package bound to current state."""
        gate_id = f"G11-{uuid4().hex[:12]}"
        bound_data = (
            f"{run_id}:{attempt_id}:{state_version}:{artifact_set_checksum}"
            f":{plan_version}:{workspace_fingerprint}"
        )
        bound_checksum = "sha256:" + hashlib.sha256(bound_data.encode("utf-8")).hexdigest()

        return G11Package(
            gate_id=gate_id,
            run_id=run_id,
            attempt_id=attempt_id,
            state_version=state_version,
            artifact_set_checksum=artifact_set_checksum,
            plan_version=plan_version,
            workspace_fingerprint=workspace_fingerprint,
            preflight_report_ref=preflight_report_ref,
            bound_checksum=bound_checksum,
            created_at=datetime.now(UTC),
        )

    def create_gate_record(
        self,
        *,
        gate_id: str,
        run_id: str,
        attempt_id: str,
        state_version: int,
        artifact_set_checksum: str,
        plan_version: str = "",
        workspace_fingerprint: str = "",
    ) -> G11GateRecord:
        """Create a G11 gate record with PENDING status."""
        return G11GateRecord(
            gate_id=gate_id,
            run_id=run_id,
            attempt_id=attempt_id,
            status=G11GateStatus.PENDING,
            state_version=state_version,
            artifact_set_checksum=artifact_set_checksum,
            plan_version=plan_version,
            workspace_fingerprint=workspace_fingerprint,
            decision=G11Decision.PENDING,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    def decide(
        self,
        *,
        gate_record: G11GateRecord,
        decision: G11Decision,
        actor: str,
        rationale: str = "",
        current_state_version: int = 0,
        current_artifact_checksum: str = "",
        current_workspace_fingerprint: str = "",
        current_plan_version: str = "",
    ) -> G11GateRecord:
        """Record a G11 decision with binding checks."""
        # Binding verification across all four bound parameters
        bound_changed = (
            current_state_version != gate_record.state_version
            or current_artifact_checksum != gate_record.artifact_set_checksum
            or (current_workspace_fingerprint and gate_record.workspace_fingerprint
                and current_workspace_fingerprint != gate_record.workspace_fingerprint)
            or (current_plan_version and gate_record.plan_version
                and current_plan_version != gate_record.plan_version)
        )

        if bound_changed:
            return G11GateRecord(
                gate_id=gate_record.gate_id,
                run_id=gate_record.run_id,
                attempt_id=gate_record.attempt_id,
                status=G11GateStatus.STALE,
                state_version=gate_record.state_version,
                artifact_set_checksum=gate_record.artifact_set_checksum,
                plan_version=gate_record.plan_version,
                workspace_fingerprint=gate_record.workspace_fingerprint,
                decision=G11Decision.STALE,
                decision_at=datetime.now(UTC),
                actor=actor,
                rationale="Bound state changed; decision automatically marked stale",
                bound_checksum=gate_record.bound_checksum,
                stale_replay=True,
                created_at=gate_record.created_at,
                updated_at=datetime.now(UTC),
            )

        now = datetime.now(UTC)
        new_status = G11GateStatus.APPROVED if decision == G11Decision.APPROVED else (
            G11GateStatus.REJECTED if decision == G11Decision.REJECTED else
            G11GateStatus.MODIFICATION_REQUESTED
        )

        return G11GateRecord(
            gate_id=gate_record.gate_id,
            run_id=gate_record.run_id,
            attempt_id=gate_record.attempt_id,
            status=new_status,
            state_version=gate_record.state_version,
            artifact_set_checksum=gate_record.artifact_set_checksum,
            plan_version=gate_record.plan_version,
            workspace_fingerprint=gate_record.workspace_fingerprint,
            decision=decision,
            decision_at=now,
            actor=actor,
            rationale=rationale,
            bound_checksum=gate_record.bound_checksum,
            stale_replay=False,
            created_at=gate_record.created_at,
            updated_at=now,
        )

    def verify_gate_for_transition(
        self,
        gate_record: G11GateRecord,
        ttl_seconds: int | None = None,
    ) -> tuple[bool, str]:
        """Verify that a G11 gate is satisfied for the next protected transition.

        Optionally checks time-based expiry if ttl_seconds is provided (defaults to
        G11_GATE_TTL_SECONDS). Pass ttl_seconds=0 to disable TTL checking.
        """
        if gate_record.status == G11GateStatus.STALE:
            return False, "G11 gate decision is stale (bound state changed)"
        if gate_record.status == G11GateStatus.EXPIRED:
            return False, "G11 gate decision has expired"
        if gate_record.status == G11GateStatus.PENDING:
            return False, "G11 gate decision is still pending"
        if gate_record.status == G11GateStatus.REJECTED:
            return False, "G11 gate was rejected"
        if gate_record.status == G11GateStatus.MODIFICATION_REQUESTED:
            return False, "G11 gate requires modification"
        if gate_record.status == G11GateStatus.APPROVED:
            # Time-based expiry check — if the gate was approved too long ago,
            # treat it as expired even if status hasn't been explicitly set
            if ttl_seconds is None:
                ttl_seconds = G11_GATE_TTL_SECONDS
            if ttl_seconds > 0 and gate_record.decision_at is not None:
                elapsed = (datetime.now(UTC) - gate_record.decision_at).total_seconds()
                if elapsed > ttl_seconds:
                    return False, (
                        f"G11 gate has expired ({elapsed:.0f}s elapsed, "
                        f"TTL {ttl_seconds}s)"
                    )
            return True, "G11 gate is approved"
        return False, f"G11 gate status: {gate_record.status}"


class RepairValidationOrchestrator:
    """Orchestrate the repair validation flow: preflight → rerun → G11."""

    def __init__(
        self,
        preflight_validator: PatchPreflightValidator | None = None,
        boundary_resolver: InvalidationBoundaryResolver | None = None,
        delta_calculator: ErrorDeltaCalculator | None = None,
        gate_service: G11GateService | None = None,
    ) -> None:
        self._preflight = preflight_validator or PatchPreflightValidator()
        self._boundary_resolver = boundary_resolver or InvalidationBoundaryResolver()
        self._delta_calculator = delta_calculator or ErrorDeltaCalculator()
        self._gate_service = gate_service or G11GateService()

    def validate_repair(
        self,
        *,
        attempt_id: str,
        run_id: str,
        preflight_id: str,
        diff_content: str,
        expected_profile_id: str,
        actual_profile_id: str,
        expected_plan_version: str,
        actual_plan_version: str,
        validation_run_id: str,
        steps: list[dict[str, Any]],
        previous_errors: list[str],
        current_errors: list[str],
        artifact_set_checksum: str,
        plan_version: str = "",
        workspace_fingerprint: str = "",
    ) -> RepairValidationResult:
        """Run the complete repair validation flow."""
        # Phase 1 — Preflight
        preflight_report = self._preflight.run_preflight(
            preflight_id=preflight_id,
            attempt_id=attempt_id,
            run_id=run_id,
            diff_content=diff_content,
            expected_profile_id=expected_profile_id,
            actual_profile_id=actual_profile_id,
            expected_plan_version=expected_plan_version,
            actual_plan_version=actual_plan_version,
        )

        if preflight_report.status == PreflightStatus.FAILED:
            return RepairValidationResult(
                attempt_id=attempt_id,
                run_id=run_id,
                status=RepairValidationStatus.PREFLIGHT_FAILED,
                state_version=0,
                preflight_report=preflight_report,
                artifact_refs={
                    "preflight_report": f"artifact:{preflight_id}/preflight-report",
                },
                failure_evidence={
                    "reason": "Preflight validation failed",
                    "errors": list(preflight_report.errors),
                },
            )

        # Phase 2 — Invalidation boundary
        invalidation_boundary = self._boundary_resolver.resolve(
            validation_run_id=validation_run_id,
            steps=steps,
        )

        # Phase 3 — Error delta
        error_delta = self._delta_calculator.calculate(
            previous_errors=previous_errors,
            current_errors=current_errors,
        )

        # Phase 4 — Rerun reference
        rerun_ref = ValidationRerunReference(
            rerun_id=f"rerun-{uuid4().hex[:12]}",
            run_id=run_id,
            stage_id="",
            attempt_id=attempt_id,
            profile_id=actual_profile_id,
            passed=len(current_errors) == 0,
            logs_ref=f"artifact:{run_id}/rerun-logs",
            results_ref=f"artifact:{run_id}/rerun-results",
        )

        # Phase 5 — G11 package
        g11_package = self._gate_service.create_gate(
            run_id=run_id,
            attempt_id=attempt_id,
            state_version=0,
            artifact_set_checksum=artifact_set_checksum,
            plan_version=plan_version,
            workspace_fingerprint=workspace_fingerprint,
            preflight_report_ref=f"artifact:{preflight_id}/preflight-report",
        )

        g11_record = self._gate_service.create_gate_record(
            gate_id=g11_package.gate_id,
            run_id=run_id,
            attempt_id=attempt_id,
            state_version=0,
            artifact_set_checksum=artifact_set_checksum,
            plan_version=plan_version,
            workspace_fingerprint=workspace_fingerprint,
        )

        status = RepairValidationStatus.WAITING_G11

        return RepairValidationResult(
            attempt_id=attempt_id,
            run_id=run_id,
            status=status,
            state_version=0,
            preflight_report=preflight_report,
            invalidation_boundary=invalidation_boundary,
            error_delta=error_delta,
            rerun_reference=rerun_ref,
            g11_package=g11_package,
            g11_record=g11_record,
            artifact_refs={
                "preflight_report": f"artifact:{preflight_id}/preflight-report",
                "invalidation_boundary": f"artifact:{validation_run_id}/invalidation-boundary",
                "error_delta": f"artifact:{run_id}/error-delta",
                "rerun_reference": f"artifact:{rerun_ref.rerun_id}/rerun-ref",
                "g11_package": f"artifact:{g11_package.gate_id}/g11-package",
            },
        )
