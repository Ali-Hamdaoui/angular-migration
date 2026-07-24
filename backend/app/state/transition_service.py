"""Transactional state transition service for Sprint 0."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.contracts import RunStatus, StageStatus, StepStatus, WorkflowEventType
from app.repositories.models import MigrationRunModel, StageStepModel, WorkflowEventModel, WorkerLeaseModel


class TransitionError(RuntimeError):
    """Base error for rejected state transitions."""


class StaleStateVersionError(TransitionError):
    """Raised when optimistic concurrency rejects a transition."""


class LeaseRequiredError(TransitionError):
    """Raised when a worker attempts to complete work without a current lease."""


class ResumeRejectedError(TransitionError):
    """Raised when a run cannot resume from the last safe checkpoint."""


@dataclass(frozen=True)
class TransitionRequest:
    run_id: str
    idempotency_key: str
    expected_state_version: int
    event_type: WorkflowEventType
    next_run_status: RunStatus | None = None
    next_run_phase: str | None = None
    next_phase_status: str | None = None
    next_approval_status: str | None = None
    next_stage_status: StageStatus | None = None
    next_step_status: StepStatus | None = None
    stage_id: str | None = None
    step_id: str | None = None
    actor: str = "system"
    reason: str = "state transition"
    worker_id: str | None = None
    occurred_at: datetime | None = None
    payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class TransitionResult:
    run_id: str
    event_id: str
    event_sequence: int
    idempotency_key: str
    previous_state_version: int
    next_state_version: int
    status: str
    idempotent_replay: bool = False


class StateTransitionService:
    """Apply accepted transitions and ordered events in one database transaction."""

    def __init__(self, session: Session, *, lease_seconds: int = 120) -> None:
        self._session = session
        self._lease_seconds = lease_seconds

    def apply_transition(self, request: TransitionRequest) -> TransitionResult:
        existing = self._find_idempotent_event(request.run_id, request.idempotency_key)
        if existing is not None:
            return self._result_from_event(existing, idempotent_replay=True)

        run = self._session.get(MigrationRunModel, request.run_id)
        if run is None:
            raise TransitionError(f"run does not exist: {request.run_id}")
        if run.state_version != request.expected_state_version:
            raise StaleStateVersionError(
                f"run {request.run_id} is at state version {run.state_version}, expected {request.expected_state_version}"
            )

        previous_version = run.state_version
        occurred_at = request.occurred_at or datetime.now(UTC)
        payload: dict[str, str | int | None] = {
            "previous_state_version": previous_version,
            "next_state_version": previous_version + 1,
            "actor": request.actor,
            "reason": request.reason,
        }
        if request.payload:
            payload.update(request.payload)
        if request.next_run_status is not None:
            payload["previous_run_status"] = run.status
            payload["next_run_status"] = request.next_run_status.value
            run.status = request.next_run_status.value
        if request.next_run_phase is not None:
            payload["previous_run_phase"] = run.run_phase
            payload["next_run_phase"] = request.next_run_phase
            run.run_phase = request.next_run_phase
        if request.next_phase_status is not None:
            payload["previous_phase_status"] = run.phase_status
            payload["next_phase_status"] = request.next_phase_status
            run.phase_status = request.next_phase_status
        if request.next_approval_status is not None:
            payload["previous_approval_status"] = run.approval_status
            payload["next_approval_status"] = request.next_approval_status
            run.approval_status = request.next_approval_status
        if request.next_stage_status is not None:
            payload["next_stage_status"] = request.next_stage_status.value
        if request.next_step_status is not None:
            self._apply_step_status(request, occurred_at)
            payload["next_step_status"] = request.next_step_status.value
            payload["step_id"] = request.step_id
        run.state_version = previous_version + 1
        run.updated_at = occurred_at

        event = self._append_event(request, occurred_at, payload)
        self._session.flush()
        return TransitionResult(
            run_id=request.run_id,
            event_id=event.id,
            event_sequence=event.sequence,
            idempotency_key=request.idempotency_key,
            previous_state_version=previous_version,
            next_state_version=run.state_version,
            status=run.status,
        )

    def append_audit_event(self, *, run_id: str, idempotency_key: str, event_type: WorkflowEventType, actor: str, reason: str, occurred_at: datetime, payload: dict[str, str | int | None] | None = None) -> TransitionResult:
        """Append an evidence/audit event without changing workflow state.

        Some durable evidence lifecycle events (for example G05_CREATED) are
        projections of an already-committed transition and must not introduce
        a second optimistic-concurrency step.
        """
        existing = self._find_idempotent_event(run_id, idempotency_key)
        if existing is not None:
            return self._result_from_event(existing, idempotent_replay=True)
        run = self._session.get(MigrationRunModel, run_id)
        if run is None:
            raise TransitionError(f"run does not exist: {run_id}")
        current = run.state_version
        body = {"previous_state_version": current, "next_state_version": current, "actor": actor, "reason": reason}
        body.update(payload or {})
        event = self._append_event(TransitionRequest(run_id=run_id, idempotency_key=idempotency_key, expected_state_version=current, event_type=event_type, actor=actor, reason=reason, occurred_at=occurred_at), occurred_at, body)
        self._session.flush()
        return TransitionResult(run_id=run_id, event_id=event.id, event_sequence=event.sequence, idempotency_key=idempotency_key, previous_state_version=current, next_state_version=current, status=run.status)

    def acquire_lease(self, *, run_id: str, worker_id: str, lease_owner: str, now: datetime) -> WorkerLeaseModel:
        lease_id = f"lease-{uuid4().hex[:12]}"
        lease = WorkerLeaseModel(
            id=lease_id,
            run_id=run_id,
            worker_id=worker_id,
            lease_owner=lease_owner,
            acquired_at=now,
            expires_at=now + timedelta(seconds=self._lease_seconds),
        )
        self._session.add(lease)
        self._session.flush()
        return lease

    def renew_lease(self, *, lease_id: str, worker_id: str, now: datetime) -> WorkerLeaseModel:
        lease = self._session.get(WorkerLeaseModel, lease_id)
        if lease is None or lease.worker_id != worker_id or lease.expires_at <= now:
            raise LeaseRequiredError("worker lease is missing, owned by another worker, or expired")
        lease.expires_at = now + timedelta(seconds=self._lease_seconds)
        self._session.flush()
        return lease

    def release_lease(self, *, lease_id: str, worker_id: str) -> None:
        lease = self._session.get(WorkerLeaseModel, lease_id)
        if lease is None or lease.worker_id != worker_id:
            raise LeaseRequiredError("worker lease is missing or owned by another worker")
        self._session.delete(lease)
        self._session.flush()

    def request_cancel(self, *, run_id: str, expected_state_version: int, idempotency_key: str, actor: str, now: datetime) -> TransitionResult:
        return self.apply_transition(
            TransitionRequest(
                run_id=run_id,
                idempotency_key=idempotency_key,
                expected_state_version=expected_state_version,
                event_type=WorkflowEventType.RUN_STATE_CHANGED,
                next_run_status=RunStatus.CANCELLING,
                actor=actor,
                reason="cancellation requested",
                occurred_at=now,
            )
        )

    def acknowledge_cancel(self, *, run_id: str, expected_state_version: int, idempotency_key: str, actor: str, now: datetime) -> TransitionResult:
        return self.apply_transition(
            TransitionRequest(
                run_id=run_id,
                idempotency_key=idempotency_key,
                expected_state_version=expected_state_version,
                event_type=WorkflowEventType.RUN_STATE_CHANGED,
                next_run_status=RunStatus.CANCELLED,
                actor=actor,
                reason="cancellation acknowledged; evidence retained",
                occurred_at=now,
            )
        )

    def resume_from_checkpoint(self, *, run_id: str, expected_state_version: int, idempotency_key: str, actor: str, checkpoint_valid: bool, workspace_valid: bool, policy_compatible: bool, now: datetime) -> TransitionResult:
        if not (checkpoint_valid and workspace_valid and policy_compatible):
            raise ResumeRejectedError("resume requires valid checkpoint, workspace, and compatible policy")
        return self.apply_transition(
            TransitionRequest(
                run_id=run_id,
                idempotency_key=idempotency_key,
                expected_state_version=expected_state_version,
                event_type=WorkflowEventType.RUN_STATE_CHANGED,
                next_run_status=RunStatus.RUNNING,
                actor=actor,
                reason="resume from last safe mock checkpoint",
                occurred_at=now,
            )
        )

    def _apply_step_status(self, request: TransitionRequest, now: datetime) -> None:
        if request.step_id is None or request.next_step_status is None:
            return
        step = self._session.get(StageStepModel, request.step_id)
        if step is None:
            raise TransitionError(f"step does not exist: {request.step_id}")
        if request.next_step_status in {StepStatus.PASSED, StepStatus.FAILED, StepStatus.CANCELLED}:
            if request.worker_id is None or not self._has_current_lease(request.run_id, request.worker_id, now):
                raise LeaseRequiredError("worker cannot complete a step without a current lease")
            step.completed_at = now
        step.status = request.next_step_status.value

    def _append_event(self, request: TransitionRequest, occurred_at: datetime, payload: dict[str, str | int | None]) -> WorkflowEventModel:
        latest_sequence = self._session.scalar(
            select(func.max(WorkflowEventModel.sequence)).where(WorkflowEventModel.run_id == request.run_id)
        )
        event = WorkflowEventModel(
            id=f"event-{uuid4().hex[:12]}",
            run_id=request.run_id,
            stage_id=request.stage_id,
            event_type=request.event_type.value,
            idempotency_key=request.idempotency_key,
            actor=request.actor,
            reason=request.reason,
            sequence=(latest_sequence or 0) + 1,
            payload=payload,
            occurred_at=occurred_at,
        )
        self._session.add(event)
        return event

    def _find_idempotent_event(self, run_id: str, idempotency_key: str) -> WorkflowEventModel | None:
        return self._session.scalar(
            select(WorkflowEventModel)
            .where(WorkflowEventModel.run_id == run_id)
            .where(WorkflowEventModel.idempotency_key == idempotency_key)
        )

    def _result_from_event(self, event: WorkflowEventModel, *, idempotent_replay: bool) -> TransitionResult:
        payload = event.payload
        return TransitionResult(
            run_id=event.run_id,
            event_id=event.id,
            event_sequence=event.sequence,
            idempotency_key=event.idempotency_key or "",
            previous_state_version=int(payload.get("previous_state_version", 0)),
            next_state_version=int(payload.get("next_state_version", 0)),
            status=str(payload.get("next_run_status") or "unchanged"),
            idempotent_replay=idempotent_replay,
        )

    def _has_current_lease(self, run_id: str, worker_id: str, now: datetime) -> bool:
        lease = self._session.scalar(
            select(WorkerLeaseModel)
            .where(WorkerLeaseModel.run_id == run_id)
            .where(WorkerLeaseModel.worker_id == worker_id)
            .where(WorkerLeaseModel.expires_at > now)
        )
        return lease is not None
