"""Durable reconciliation for terminal repair-attempt lifecycle state."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.repositories.models import (
    MigrationStageModel,
    RepairAttemptModel,
    StageGatePackageModel,
)
from app.services.repair_lifecycle_reliability_service import RepairLifecycleError
from app.state.event_sequencer import append_workflow_event


ACTIVE_REPAIR_STATUSES = frozenset(
    {
        "evidence_frozen",
        "proposed",
        "review_accepted",
        "waiting_g10",
        "applying",
        "applied",
        "revalidating",
        "revalidating_affected",
    }
)


class RepairLifecycleService:
    """Own fail-closed lifecycle reconciliation for historical repairs."""

    @staticmethod
    def transition_in_session(
        session,
        attempt: RepairAttemptModel,
        to_status: str,
        *,
        expected_state_version: int | None = None,
        reason: str = "repair lifecycle transition",
        actor: str = "factory",
        now: datetime | None = None,
    ) -> RepairAttemptModel:
        """Apply one audited repair transition inside the caller's transaction.

        The caller keeps ownership of the transaction so status, evidence, and
        continuation changes cannot commit independently.  This is the common
        authority for new writes; the legacy reconciliation paths remain
        readable while they are migrated.
        """
        from app.domain.repair_lifecycle import evaluate_transition

        current_version = int(attempt.state_version or 1)
        if expected_state_version is not None and current_version != expected_state_version:
            raise RepairLifecycleError(
                "REPAIR_STATE_VERSION_CONFLICT",
                "repair lifecycle state changed concurrently",
                {
                    "attempt_id": attempt.id,
                    "expected": expected_state_version,
                    "actual": current_version,
                },
            )
        if attempt.status == to_status:
            return attempt
        decision = evaluate_transition(attempt.id, attempt.status, to_status)
        if not decision.allowed:
            raise RepairLifecycleError(
                "REPAIR_TRANSITION_ILLEGAL",
                decision.reason or "illegal repair lifecycle transition",
                {
                    "attempt_id": attempt.id,
                    "from_status": attempt.status,
                    "to_status": to_status,
                },
            )
        occurred_at = now or datetime.now(UTC)
        next_version = current_version + 1
        attempt.status = to_status
        attempt.state_version = next_version
        attempt.updated_at = occurred_at
        append_workflow_event(
            session,
            run_id=attempt.run_id,
            stage_id=attempt.stage_id,
            event_type="REPAIR_LIFECYCLE_TRANSITION",
            idempotency_key=f"repair-transition:{attempt.id}:{next_version}",
            actor=actor,
            reason=reason,
            occurred_at=occurred_at,
            payload={
                "attempt_id": attempt.id,
                "from_status": decision.from_status,
                "to_status": to_status,
                "state_version": next_version,
            },
        )
        return attempt

    @classmethod
    def reconcile_superseded_attempts(
        cls,
        session,
        *,
        run_id: str,
        stage_id: str,
        now: datetime | None = None,
    ) -> tuple[str, ...]:
        stage = session.scalar(
            select(MigrationStageModel).where(
                MigrationStageModel.id == stage_id,
                MigrationStageModel.run_id == run_id,
                MigrationStageModel.status == "sealed",
            )
        )
        final_gate = session.scalar(
            select(StageGatePackageModel)
            .where(
                StageGatePackageModel.run_id == run_id,
                StageGatePackageModel.stage_id == stage_id,
                StageGatePackageModel.gate_id.in_("G11", "G12"),
                StageGatePackageModel.status == "approved",
                StageGatePackageModel.stale_at.is_(None),
            )
            .order_by(
                (StageGatePackageModel.gate_id == "G12").desc(),
                StageGatePackageModel.gate_version.desc(),
            )
        )
        if stage is None or final_gate is None:
            return ()

        replacements = session.scalars(
            select(RepairAttemptModel)
            .where(
                RepairAttemptModel.run_id == run_id,
                RepairAttemptModel.stage_id == stage_id,
                RepairAttemptModel.status.in_(
                    ("validation_passed", "waiting_g11", "revalidating", "revalidating_affected")
                ),
            )
            .order_by(RepairAttemptModel.attempt_number.desc())
        ).all()
        replacement = next(
            (
                attempt
                for attempt in replacements
                if cls._has_complete_replacement_evidence(
                    session,
                    attempt,
                    final_gate=final_gate,
                    allow_uncompleted=final_gate.gate_id == "G12",
                )
            ),
            None,
        )
        if replacement is None:
            return ()

        reconciled_at = now or datetime.now(UTC)
        if replacement.status != "validation_passed":
            if replacement.status != "waiting_g11":
                cls.transition_in_session(
                    session,
                    replacement,
                    "waiting_g11",
                    reason="sealed final gate completed legacy repair revalidation",
                    actor="transformer",
                    now=reconciled_at,
                )
            cls.transition_in_session(
                session,
                replacement,
                "validation_passed",
                reason="sealed final gate completed repair validation",
                actor="transformer",
                now=reconciled_at,
            )
            replacement.completed_at = reconciled_at

        older_attempts = session.scalars(
            select(RepairAttemptModel)
            .where(
                RepairAttemptModel.run_id == run_id,
                RepairAttemptModel.stage_id == stage_id,
                RepairAttemptModel.attempt_number < replacement.attempt_number,
                RepairAttemptModel.status.in_(ACTIVE_REPAIR_STATUSES),
            )
            .order_by(RepairAttemptModel.attempt_number)
        ).all()
        if not older_attempts:
            return ()

        for attempt in older_attempts:
            attempt.status = "superseded"
            attempt.completed_at = reconciled_at
            attempt.updated_at = reconciled_at
        return tuple(attempt.id for attempt in older_attempts)

    @staticmethod
    def _has_approved_gate(session, *, run_id: str, stage_id: str, gate_id: str) -> bool:
        return (
            session.scalar(
                select(StageGatePackageModel.id).where(
                    StageGatePackageModel.run_id == run_id,
                    StageGatePackageModel.stage_id == stage_id,
                    StageGatePackageModel.gate_id == gate_id,
                    StageGatePackageModel.status == "approved",
                    StageGatePackageModel.stale_at.is_(None),
                )
            )
            is not None
        )

    @classmethod
    def _has_complete_replacement_evidence(
        cls,
        session,
        attempt,
        *,
        final_gate: StageGatePackageModel,
        allow_uncompleted: bool = False,
    ) -> bool:
        if not all(
            (
                attempt.proposal_artifact_id,
                attempt.proposal_checksum,
                attempt.review_artifact_id,
                attempt.review_checksum,
                attempt.apply_ledger_artifact_id,
                attempt.apply_ledger_checksum,
                attempt.validation_summary_artifact_id,
                attempt.validation_summary_checksum,
                attempt.post_fingerprint,
            )
        ):
            return False
        if not allow_uncompleted and attempt.completed_at is None:
            return False
        gate = session.get(StageGatePackageModel, attempt.g10_gate_package_id)
        return bool(
            gate is not None
            and gate.run_id == attempt.run_id
            and gate.stage_id == attempt.stage_id
            and gate.gate_id == "G10"
            and gate.status == "approved"
            and gate.stale_at is None
            and gate.stage_plan_id == final_gate.stage_plan_id
            and final_gate.workspace_fingerprint == attempt.post_fingerprint
        )
