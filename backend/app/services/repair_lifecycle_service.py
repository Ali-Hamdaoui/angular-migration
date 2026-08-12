"""Durable reconciliation for terminal repair-attempt lifecycle state."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.repositories.models import (
    MigrationStageModel,
    RepairAttemptModel,
    StageGatePackageModel,
)


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
        if stage is None or not cls._has_approved_gate(
            session, run_id=run_id, stage_id=stage_id, gate_id="G11"
        ):
            return ()

        replacements = session.scalars(
            select(RepairAttemptModel)
            .where(
                RepairAttemptModel.run_id == run_id,
                RepairAttemptModel.stage_id == stage_id,
                RepairAttemptModel.status == "validation_passed",
            )
            .order_by(RepairAttemptModel.attempt_number.desc())
        ).all()
        replacement = next(
            (
                attempt
                for attempt in replacements
                if cls._has_complete_replacement_evidence(session, attempt)
            ),
            None,
        )
        if replacement is None:
            return ()

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

        reconciled_at = now or datetime.now(UTC)
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
    def _has_complete_replacement_evidence(cls, session, attempt) -> bool:
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
                attempt.completed_at,
            )
        ):
            return False
        gate = session.get(StageGatePackageModel, attempt.g10_gate_package_id)
        return bool(
            gate is not None
            and gate.run_id == attempt.run_id
            and gate.stage_id == attempt.stage_id
            and gate.gate_id == "G10"
            and gate.status == "approved"
            and gate.stale_at is None
        )
