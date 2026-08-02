"""Durable Transformer continuation lifecycle."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.domain.contracts import WorkflowEventType
from app.domain.transformation import TransformationNode, TransformationStatus
from app.repositories.models import (
    G06ApprovalModel,
    MigrationPlanModel,
    MigrationStageModel,
    StageExecutionPlanModel,
    TransformationContinuationModel,
)
from app.state import StateTransitionService


class TransformationContinuationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def append_continuation_event(
    session: Session,
    continuation: TransformationContinuationModel,
    *,
    event_type: WorkflowEventType,
    key: str,
    reason: str,
    payload: dict[str, str | int | None] | None = None,
    occurred_at: datetime | None = None,
    actor: str = "transformer",
) -> None:
    """Append a durable continuation lifecycle event atomically in the caller's transaction.

    The event shares the continuation's transaction, so the status change and
    the event commit together; replaying the same deterministic key appends
    nothing a second time.
    """
    StateTransitionService(session).append_audit_event(
        run_id=continuation.run_id,
        idempotency_key=f"{continuation.id}:{key}",
        event_type=event_type,
        actor=actor,
        reason=reason,
        occurred_at=occurred_at or continuation.updated_at,
        payload=payload or {},
    )


class TransformationContinuationService:
    def __init__(self, *, lease_seconds: int = 120) -> None:
        self.lease_seconds = lease_seconds

    def ensure_created_in_session(
        self,
        session: Session,
        *,
        run_id: str,
        stage_id: str,
        g06_approval_id: str,
        plan_id: str,
        plan_checksum: str,
        stage_plan_id: str,
        stage_plan_checksum: str,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> TransformationContinuationModel:
        created_at = now or datetime.now(UTC)
        request_checksum = self._checksum(
            {
                "run_id": run_id,
                "stage_id": stage_id,
                "g06_approval_id": g06_approval_id,
                "plan_id": plan_id,
                "plan_checksum": plan_checksum,
                "stage_plan_id": stage_plan_id,
                "stage_plan_checksum": stage_plan_checksum,
                "idempotency_key": idempotency_key,
            }
        )
        existing = session.scalar(
            select(TransformationContinuationModel).where(
                TransformationContinuationModel.run_id == run_id
            )
        )
        if existing is not None:
            if existing.request_checksum != request_checksum:
                raise TransformationContinuationError(
                    "IDEMPOTENCY_PAYLOAD_MISMATCH",
                    "Transformation continuation already exists with a different payload",
                )
            return existing
        g06 = session.get(G06ApprovalModel, g06_approval_id)
        plan = session.get(MigrationPlanModel, plan_id)
        stage_plan = session.get(StageExecutionPlanModel, stage_plan_id)
        stage = session.get(MigrationStageModel, stage_id)
        if (
            g06 is None
            or g06.run_id != run_id
            or g06.status not in {"approved", "approved_with_comment"}
            or g06.plan_checksum != plan_checksum
            or g06.stage_plan_checksum != stage_plan_checksum
        ):
            raise TransformationContinuationError("G06_BINDING_STALE", "Approved G06 binding is missing or stale")
        if plan is None or plan.run_id != run_id or plan.checksum != plan_checksum:
            raise TransformationContinuationError("G06_BINDING_STALE", "Migration plan binding is stale")
        if (
            stage_plan is None
            or stage_plan.run_id != run_id
            or stage_plan.stage_id != stage_id
            or stage_plan.migration_plan_id != plan_id
            or stage_plan.checksum != stage_plan_checksum
        ):
            raise TransformationContinuationError("STAGE_PLAN_STALE", "Stage plan binding is stale")
        if stage is None:
            planned = stage_plan.stage_plan or {}
            stage = MigrationStageModel(
                id=stage_id,
                run_id=run_id,
                stage_order=session.query(MigrationStageModel).filter_by(run_id=run_id).count() + 1,
                source_version_family=planned.get("source_family"),
                target_version_family=planned.get("target_family"),
                source_version_detected=planned.get("source_exact"),
                target_version_resolved=planned.get("target_exact"),
                source_angular_version=planned.get("source_exact"),
                target_angular_version=planned.get("target_exact"),
                status="planned",
                created_at=created_at,
            )
            session.add(stage)
            session.flush()
        if stage.run_id != run_id:
            raise TransformationContinuationError("STAGE_PLAN_STALE", "Stage does not belong to the run")
        model = TransformationContinuationModel(
            id=f"transform-{uuid4().hex[:12]}",
            run_id=run_id,
            current_stage_id=stage_id,
            thread_id=f"transform:{run_id}",
            status=TransformationStatus.QUEUED.value,
            current_node=TransformationNode.VALIDATE_G06.value,
            g06_approval_id=g06_approval_id,
            plan_id=plan_id,
            plan_checksum=plan_checksum,
            stage_plan_id=stage_plan_id,
            stage_plan_checksum=stage_plan_checksum,
            attempt=0,
            max_attempts=3,
            claim_count=0,
            wake_sequence=0,
            idempotency_key=idempotency_key,
            request_checksum=request_checksum,
            state_version=1,
            created_at=created_at,
            updated_at=created_at,
        )
        session.add(model)
        session.flush()
        StateTransitionService(session).append_audit_event(
            run_id=run_id,
            idempotency_key=f"{idempotency_key}:continuation",
            event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_CREATED,
            actor="transformer",
            reason="durable Transformer continuation created",
            occurred_at=created_at,
            payload={"continuation_id": model.id, "stage_id": stage_id},
        )
        return model

    def claim_next(
        self,
        session: Session,
        worker_id: str,
        now: datetime | None = None,
    ) -> TransformationContinuationModel | None:
        claimed_at = now or datetime.now(UTC)
        candidate = session.scalar(
            select(TransformationContinuationModel)
            .where(
                or_(
                    TransformationContinuationModel.status == TransformationStatus.QUEUED.value,
                    TransformationContinuationModel.status == TransformationStatus.CANCELLING.value,
                    TransformationContinuationModel.status == TransformationStatus.WAITING_RETRY.value,
                    (
                        (TransformationContinuationModel.status == TransformationStatus.RUNNING.value)
                        & (TransformationContinuationModel.lease_expires_at <= claimed_at)
                    ),
                )
            )
            .where(
                or_(
                    TransformationContinuationModel.next_attempt_at.is_(None),
                    TransformationContinuationModel.next_attempt_at <= claimed_at,
                )
            )
            .order_by(TransformationContinuationModel.created_at)
            .limit(1)
        )
        if candidate is None:
            return None
        prior_claim_count = candidate.claim_count or 0
        claimed = session.execute(
            update(TransformationContinuationModel)
            .where(TransformationContinuationModel.id == candidate.id)
            .where(TransformationContinuationModel.state_version == candidate.state_version)
            .values(
                status=TransformationStatus.RUNNING.value,
                worker_id=worker_id,
                claim_count=prior_claim_count + 1,
                lease_expires_at=claimed_at + timedelta(seconds=self.lease_seconds),
                state_version=candidate.state_version + 1,
                started_at=candidate.started_at or claimed_at,
                updated_at=claimed_at,
            )
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:
            session.expire_all()
            return None
        session.refresh(candidate)
        append_continuation_event(
            session,
            candidate,
            event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_CLAIMED,
            key=f"claim:{candidate.claim_count}",
            reason="durable Transformer continuation claimed by worker",
            payload={
                "worker_id": candidate.worker_id or "",
                "expected_state_version": candidate.state_version - 1,
            },
            occurred_at=claimed_at,
        )
        return candidate

    def wait(
        self,
        session: Session,
        continuation_id: str,
        worker_id: str,
        *,
        status: str,
        current_node: str,
        now: datetime | None = None,
    ) -> TransformationContinuationModel:
        if status not in {
            TransformationStatus.WAITING_COMMAND.value,
            TransformationStatus.WAITING_GATE.value,
            TransformationStatus.WAITING_PROMPT.value,
            TransformationStatus.WAITING_RETRY.value,
            TransformationStatus.BLOCKED.value,
        }:
            raise TransformationContinuationError("TRANSFORMATION_STATUS_INVALID", "Invalid continuation wait status")
        model = self._owned(session, continuation_id, worker_id)
        occurred_at = now or datetime.now(UTC)
        expected_state_version = model.state_version
        model.status = status
        model.current_node = TransformationNode(current_node).value
        model.worker_id = None
        model.lease_expires_at = None
        model.state_version += 1
        model.updated_at = occurred_at
        session.flush()
        append_continuation_event(
            session,
            model,
            event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_WAITING,
            key=f"wait:{status}:{expected_state_version}",
            reason=f"Transformer continuation waits on {status}",
            payload={"expected_state_version": expected_state_version},
            occurred_at=occurred_at,
        )
        return model

    def wake(
        self,
        session: Session,
        continuation_id: str,
        *,
        now: datetime | None = None,
    ) -> TransformationContinuationModel:
        model = self._get(session, continuation_id)
        if model.status in {
            TransformationStatus.CANCELLED.value,
            TransformationStatus.FAILED.value,
            TransformationStatus.COMPLETED.value,
        }:
            raise TransformationContinuationError(
                "TRANSFORMATION_ALREADY_TERMINAL",
                "Terminal continuation cannot be woken",
            )
        if model.status != TransformationStatus.QUEUED.value:
            model.status = TransformationStatus.QUEUED.value
            model.worker_id = None
            model.lease_expires_at = None
            model.wake_sequence += 1
            model.state_version += 1
            model.updated_at = now or datetime.now(UTC)
            session.flush()
        return model

    def request_cancel(
        self,
        session: Session,
        continuation_id: str,
        *,
        actor: str,
        idempotency_key: str,
        expected_state_version: int,
        now: datetime | None = None,
    ) -> TransformationContinuationModel:
        model = self._get(session, continuation_id)
        checksum = self._checksum(
            {"continuation_id": continuation_id, "actor": actor, "idempotency_key": idempotency_key}
        )
        if model.cancel_idempotency_key is not None:
            if (
                model.cancel_idempotency_key != idempotency_key
                or model.cancel_request_checksum != checksum
            ):
                raise TransformationContinuationError(
                    "IDEMPOTENCY_PAYLOAD_MISMATCH",
                    "Cancellation key was already used with a different payload",
                )
            return model
        if model.state_version != expected_state_version:
            raise TransformationContinuationError(
                "TRANSFORMATION_STATE_CONFLICT",
                "Transformation state changed; refresh authoritative state",
            )
        if model.status in {
            TransformationStatus.CANCELLED.value,
            TransformationStatus.FAILED.value,
            TransformationStatus.COMPLETED.value,
        }:
            raise TransformationContinuationError(
                "TRANSFORMATION_ALREADY_TERMINAL",
                "Terminal continuation cannot be cancelled",
            )
        requested_at = now or datetime.now(UTC)
        expected_state_version = model.state_version
        model.cancel_requested_at = requested_at
        model.cancel_requested_by = actor
        model.cancel_idempotency_key = idempotency_key
        model.cancel_request_checksum = checksum
        model.status = TransformationStatus.CANCELLING.value
        model.current_node = TransformationNode.CANCEL.value
        model.worker_id = None
        model.lease_expires_at = None
        model.state_version += 1
        model.updated_at = requested_at
        session.flush()
        append_continuation_event(
            session,
            model,
            event_type=WorkflowEventType.TRANSFORMATION_CANCEL_REQUESTED,
            key=f"cancel:{idempotency_key}",
            reason="Transformer cancellation requested",
            payload={
                "actor": actor,
                "expected_state_version": expected_state_version,
            },
            occurred_at=requested_at,
        )
        return model

    def complete(
        self,
        session: Session,
        continuation_id: str,
        worker_id: str,
        *,
        now: datetime | None = None,
    ) -> TransformationContinuationModel:
        model = self._owned(session, continuation_id, worker_id)
        completed_at = now or datetime.now(UTC)
        expected_state_version = model.state_version
        model.status = TransformationStatus.COMPLETED.value
        model.current_node = TransformationNode.TERMINAL.value
        model.worker_id = None
        model.lease_expires_at = None
        model.completed_at = completed_at
        model.updated_at = completed_at
        model.state_version += 1
        session.flush()
        append_continuation_event(
            session,
            model,
            event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_COMPLETED,
            key="complete",
            reason="durable Transformer continuation completed",
            payload={"expected_state_version": expected_state_version},
            occurred_at=completed_at,
        )
        return model

    @staticmethod
    def _checksum(value: dict[str, object]) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _get(session: Session, continuation_id: str) -> TransformationContinuationModel:
        model = session.get(TransformationContinuationModel, continuation_id)
        if model is None:
            raise TransformationContinuationError("TRANSFORMATION_NOT_FOUND", "Continuation does not exist")
        return model

    def _owned(
        self,
        session: Session,
        continuation_id: str,
        worker_id: str,
    ) -> TransformationContinuationModel:
        model = self._get(session, continuation_id)
        if model.status != TransformationStatus.RUNNING.value or model.worker_id != worker_id:
            raise TransformationContinuationError("TRANSFORMATION_CLAIM_STALE", "Worker no longer owns continuation")
        return model
