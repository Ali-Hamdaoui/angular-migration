"""Partial migration delivery service (V2 F26)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.domain.partial_delivery import PartialDeliveryDecision
from app.repositories.models import MigrationRunModel, PartialDeliveryModel, StageValidationSealModel
from app.repositories.session import session_scope
from app.services.stage_rollback_service import StageRollbackService


class PartialDeliveryError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class PartialDeliveryService:
    """Deliver a partial migration at the furthest sealed stage (F26)."""

    def __init__(
        self,
        *,
        rollback_service: StageRollbackService | None = None,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._rollback = rollback_service or StageRollbackService()
        self._session_scope = session_scope_factory or session_scope
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def deliver_partial(self, run_id: str, workspace: Path) -> PartialDeliveryDecision:
        """Deliver the partial migration at the furthest sealed stage (F26-01).

        The workspace is validated before delivery (F26-02), the remaining
        stages are recorded (F26-03), and the delivery is resumable (F26-04).
        """
        self._require_run(run_id)
        rollback_point = self._rollback.find_rollback_point(run_id)
        if rollback_point is None:
            raise PartialDeliveryError("NO_SEALED_STAGE", f"run {run_id} has no sealed stage to deliver")
        validated, fingerprint, blockers = self._validate_partial_workspace(workspace)
        remaining = self._remaining_stages(run_id, rollback_point)
        decision = PartialDeliveryDecision(
            run_id=run_id,
            delivered_at_stage=rollback_point,
            delivered_fingerprint=fingerprint,
            validated=validated,
            remaining_stages=tuple(remaining),
            resumable=True,
        ).bind_checksum()
        with self._session_scope() as session:
            existing = session.scalar(
                select(PartialDeliveryModel).where(
                    PartialDeliveryModel.run_id == run_id,
                    PartialDeliveryModel.checksum == decision.checksum,
                )
            )
            if existing is None:
                session.add(
                    PartialDeliveryModel(
                        id="pd-" + hashlib.sha256(f"{run_id}:{decision.checksum}".encode()).hexdigest()[:24],
                        run_id=run_id,
                        delivered_at_stage=rollback_point,
                        delivered_fingerprint=fingerprint,
                        validated=validated,
                        remaining_stages=list(remaining),
                        resumable=True,
                        blockers=blockers,
                        checksum=decision.checksum,
                        created_at=self._now_provider(),
                    )
                )
                session.commit()
        return decision

    def resume_partial(self, run_id: str) -> dict:
        """Resume a partial migration from the last delivery (F26-04)."""
        self._require_run(run_id)
        with self._session_scope() as session:
            last = session.scalar(
                select(PartialDeliveryModel)
                .where(PartialDeliveryModel.run_id == run_id)
                .order_by(PartialDeliveryModel.created_at.desc())
                .limit(1)
            )
            if last is None:
                raise PartialDeliveryError("NO_PARTIAL_DELIVERY", f"run {run_id} has no partial delivery to resume")
        return {
            "run_id": run_id,
            "delivered_at_stage": last.delivered_at_stage,
            "remaining_stages": list(last.remaining_stages or []),
            "resume_action": "resume_chain_from_delivered_stage",
        }

    def _validate_partial_workspace(self, workspace: Path) -> tuple[bool, str, list[str]]:
        """Validate the partial workspace before delivery (F26-02)."""
        blockers: list[str] = []
        if not workspace.is_dir():
            blockers.append("PARTIAL_WORKSPACE_MISSING")
        elif not (workspace / "package.json").is_file():
            blockers.append("PARTIAL_PACKAGE_JSON_MISSING")
        from app.services.workspace_fingerprint import STAGE_FINGERPRINT_PROFILE

        fingerprint = STAGE_FINGERPRINT_PROFILE.fingerprint(workspace) if workspace.is_dir() else ""
        return (not blockers, fingerprint, blockers)

    def _remaining_stages(self, run_id: str, delivered_at_stage: int) -> list[str]:
        """Record the remaining work for the partial delivery (F26-03)."""
        from app.repositories.models import MigrationStageModel, StageChainRunModel

        with self._session_scope() as session:
            chain = session.scalar(
                select(StageChainRunModel)
                .where(StageChainRunModel.run_id == run_id)
                .order_by(StageChainRunModel.updated_at.desc())
                .limit(1)
            )
            if chain is not None:
                chain_orders = sorted(s.get("stage_order") for s in (chain.stages or []))
            else:
                chain_orders = sorted(
                    session.scalars(
                        select(MigrationStageModel.stage_order).where(MigrationStageModel.run_id == run_id)
                    ).all()
                )
        return [f"angular-{order+10}.x -> angular-{order+11}.x" for order in chain_orders if order > delivered_at_stage]

    def list_partial_deliveries(self, run_id: str) -> list[PartialDeliveryModel]:
        with self._session_scope() as session:
            return list(
                session.scalars(
                    select(PartialDeliveryModel)
                    .where(PartialDeliveryModel.run_id == run_id)
                    .order_by(PartialDeliveryModel.created_at.asc())
                ).all()
            )

    def _require_run(self, run_id: str) -> None:
        with self._session_scope() as session:
            if session.get(MigrationRunModel, run_id) is None:
                raise PartialDeliveryError("RUN_NOT_FOUND", f"Migration run {run_id} not found")
