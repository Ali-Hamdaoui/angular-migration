"""Transactional state transition service for Sprint 0."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.domain.contracts import RunStatus, StageStatus, StepStatus, WorkflowEventType
from app.repositories.models import (
    MigrationRunModel,
    MigrationStageModel,
    StageStepModel,
    WorkflowEventModel,
    WorkerLeaseModel,
)
from app.state.event_sequencer import append_workflow_event


class TransitionError(RuntimeError):
    """Base error for rejected state transitions."""


class StaleStateVersionError(TransitionError):
    """Raised when optimistic concurrency rejects a transition."""


class IdempotencyPayloadMismatchError(TransitionError):
    """Raised when an idempotency key is reused for a different request."""


class LeaseRequiredError(TransitionError):
    """Raised when a worker attempts to complete work without a current lease."""


class ResumeRejectedError(TransitionError):
    """Raised when a run cannot resume from the last safe checkpoint."""


class IllegalRunTransitionError(TransitionError):
    """Raised when an event would move a run to a status its event type forbids."""


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

    # Closed run-level transition map: for each workflow event type that may
    # move a run, the exact set of next run statuses that event type may
    # produce. Event types absent from the map never change run status.
    # Enumerated from every apply_transition call site across the services
    # and orchestrators (migration_run_service, source_intake, planning,
    # source_snapshot, g02, baseline_g03, discovery, analysis, compatibility,
    # planning_review, transformer_stage, transformer_sealing_flow, command
    # executor and supervisor services).
    _LEGAL_RUN_TRANSITIONS: dict[WorkflowEventType, frozenset[RunStatus]] = {
        WorkflowEventType.RUN_STATE_CHANGED: frozenset({
            RunStatus.SOURCE_VALIDATION_RUNNING,
            RunStatus.RUNNING,
            RunStatus.CANCELLING,
            RunStatus.CANCELLED,
        }),
        WorkflowEventType.RUN_START_ACCEPTED: frozenset({RunStatus.SOURCE_VALIDATION_RUNNING}),
        WorkflowEventType.RUN_CANCEL_REQUESTED: frozenset({RunStatus.CANCELLING}),
        WorkflowEventType.RUN_CANCELLED: frozenset({RunStatus.CANCELLED}),
        WorkflowEventType.SOURCE_INTAKE_FAILED: frozenset({RunStatus.FAILED}),
        WorkflowEventType.SNAPSHOT_STARTED: frozenset({RunStatus.SOURCE_VALIDATION_RUNNING}),
        WorkflowEventType.SNAPSHOT_CREATED: frozenset({RunStatus.SOURCE_VALIDATED}),
        WorkflowEventType.BASELINE_QUALIFIED: frozenset({RunStatus.BASELINE_QUALIFIED}),
        WorkflowEventType.BASELINE_BLOCKED: frozenset({RunStatus.DIAGNOSTIC_HOLD}),
        WorkflowEventType.G03_APPROVED: frozenset({RunStatus.BASELINE_QUALIFIED}),
        WorkflowEventType.DISCOVERY_BLOCKED: frozenset({RunStatus.DIAGNOSTIC_HOLD}),
        WorkflowEventType.G02_STALE: frozenset({RunStatus.DIAGNOSTIC_HOLD}),
        WorkflowEventType.EXECUTION_PROFILE_BLOCKED: frozenset({RunStatus.DIAGNOSTIC_HOLD}),
        WorkflowEventType.COMPATIBILITY_RESOLUTION_COMPLETED: frozenset({RunStatus.WAITING_PLAN_APPROVAL}),
        WorkflowEventType.G04_APPROVED: frozenset({RunStatus.PLANNING_RUNNING}),
        WorkflowEventType.G05_APPROVED: frozenset({RunStatus.PLANNING_RUNNING, RunStatus.WAITING_PLAN_APPROVAL}),
        WorkflowEventType.G06_APPROVED: frozenset({RunStatus.WAITING_STAGE_PREPARATION}),
        WorkflowEventType.G06_REJECTED: frozenset({RunStatus.WAITING_PLAN_APPROVAL}),
        WorkflowEventType.PLANNING_AGENT_COMPLETED: frozenset({RunStatus.WAITING_PLAN_APPROVAL}),
        WorkflowEventType.PLANNING_REVIEW_REVISION_REQUIRED: frozenset({RunStatus.WAITING_PLAN_APPROVAL}),
        WorkflowEventType.PLANNING_REVIEW_REJECTED: frozenset({RunStatus.WAITING_PLAN_APPROVAL}),
        WorkflowEventType.PLANNING_REVIEW_INSUFFICIENT_CONTEXT: frozenset({RunStatus.WAITING_PLAN_APPROVAL}),
        WorkflowEventType.PLANNING_FAILED: frozenset({RunStatus.FAILED}),
        WorkflowEventType.STAGED_MIGRATION_COMPLETED: frozenset({RunStatus.COMPLETED}),
        WorkflowEventType.STAGE_CREATED: frozenset({RunStatus.STAGE_CREATED}),
    }

    def __init__(self, session: Session, *, lease_seconds: int = 120) -> None:
        self._session = session
        self._lease_seconds = lease_seconds

    def apply_transition(self, request: TransitionRequest) -> TransitionResult:
        request_checksum = self._request_checksum(request)
        existing = self._find_idempotent_event(request.run_id, request.idempotency_key)
        if existing is not None:
            if existing.payload.get("request_checksum") != request_checksum:
                raise IdempotencyPayloadMismatchError(
                    f"idempotency key {request.idempotency_key} was already used for a different transition"
                )
            return self._result_from_event(existing, idempotent_replay=True)

        run = self._session.get(MigrationRunModel, request.run_id)
        if run is None:
            raise TransitionError(f"run does not exist: {request.run_id}")
        if run.state_version != request.expected_state_version:
            raise StaleStateVersionError(
                f"run {request.run_id} is at state version {run.state_version}, expected {request.expected_state_version}"
            )
        if request.next_run_status is not None:
            allowed_statuses = self._LEGAL_RUN_TRANSITIONS.get(request.event_type)
            if allowed_statuses is None or request.next_run_status not in allowed_statuses:
                raise IllegalRunTransitionError(
                    f"run transition {request.event_type.value} -> {request.next_run_status.value} is not a legal workflow transition"
                )
        if request.next_stage_status is not None:
            self._validate_stage_status(request)
        if request.next_step_status is not None:
            self._validate_step_status(request, request.occurred_at or datetime.now(UTC))

        previous_version = run.state_version
        occurred_at = request.occurred_at or datetime.now(UTC)
        payload: dict[str, str | int | None] = {
            "previous_state_version": previous_version,
            "next_state_version": previous_version + 1,
            "actor": request.actor,
            "reason": request.reason,
            "request_checksum": request_checksum,
        }
        if request.payload:
            payload.update(request.payload)
        run_values: dict[str, Any] = {
            "state_version": previous_version + 1,
            "updated_at": occurred_at,
        }
        if request.next_run_status is not None:
            payload["previous_run_status"] = run.status
            payload["next_run_status"] = request.next_run_status.value
            run_values["status"] = request.next_run_status.value
        if request.next_run_phase is not None:
            payload["previous_run_phase"] = run.run_phase
            payload["next_run_phase"] = request.next_run_phase
            run_values["run_phase"] = request.next_run_phase
        if request.next_phase_status is not None:
            payload["previous_phase_status"] = run.phase_status
            payload["next_phase_status"] = request.next_phase_status
            run_values["phase_status"] = request.next_phase_status
        if request.next_approval_status is not None:
            payload["previous_approval_status"] = run.approval_status
            payload["next_approval_status"] = request.next_approval_status
            run_values["approval_status"] = request.next_approval_status
        consumed = self._session.execute(
            update(MigrationRunModel)
            .where(MigrationRunModel.id == request.run_id)
            .where(MigrationRunModel.state_version == request.expected_state_version)
            .values(**run_values)
            .execution_options(synchronize_session=False)
        )
        if consumed.rowcount != 1:
            raise StaleStateVersionError(
                f"run {request.run_id} state version was concurrently consumed"
            )
        for field, value in run_values.items():
            setattr(run, field, value)
        if request.next_stage_status is not None:
            stage = self._apply_stage_status(request, occurred_at)
            payload["previous_stage_status"] = stage[0]
            payload["next_stage_status"] = request.next_stage_status.value
            payload["stage_id"] = request.stage_id
        if request.next_step_status is not None:
            self._apply_step_status(request, occurred_at)
            payload["next_step_status"] = request.next_step_status.value
            payload["step_id"] = request.step_id

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

    def _apply_stage_status(self, request: TransitionRequest, now: datetime) -> tuple[str, str]:
        stage = self._validate_stage_status(request)
        previous = stage.status
        stage.status = request.next_stage_status.value
        if request.next_stage_status in {StageStatus.PREPARING, StageStatus.RUNNING} and stage.started_at is None:
            stage.started_at = now
        if request.next_stage_status in {
            StageStatus.PASSED,
            StageStatus.PASSED_WITH_KNOWN_BASELINE_FAILURES,
            StageStatus.PASSED_WITH_MANUAL_ITEMS,
            StageStatus.FAILED,
            StageStatus.ROLLED_BACK,
            StageStatus.CANCELLED,
        }:
            stage.completed_at = now
        return previous, stage.status

    def _validate_stage_status(self, request: TransitionRequest) -> MigrationStageModel:
        if request.stage_id is None or request.next_stage_status is None:
            raise TransitionError("stage status transition requires stage_id")
        stage = self._session.get(MigrationStageModel, request.stage_id)
        if stage is None or stage.run_id != request.run_id:
            raise TransitionError(f"stage does not belong to run: {request.stage_id}")
        return stage

    def append_audit_event(self, *, run_id: str, idempotency_key: str, event_type: WorkflowEventType, actor: str, reason: str, occurred_at: datetime, payload: dict[str, str | int | None] | None = None) -> TransitionResult:
        """Append an evidence/audit event without changing workflow state.

        Some durable evidence lifecycle events (for example G05_CREATED) are
        projections of an already-committed transition and must not introduce
        a second optimistic-concurrency step. Replays verify the canonical
        audit checksum, so a different payload reusing the same key conflicts.
        """
        existing = self._find_idempotent_event(run_id, idempotency_key)
        if existing is not None:
            stored_checksum = (existing.payload or {}).get("request_checksum")
            if stored_checksum is not None and stored_checksum != canonical_audit_checksum(
                run_id=run_id, idempotency_key=idempotency_key, event_type=event_type,
                actor=actor, reason=reason, payload=payload,
            ):
                raise IdempotencyPayloadMismatchError(
                    f"idempotency key {idempotency_key} was already used for a different audit event"
                )
            return self._result_from_event(existing, idempotent_replay=True)
        run = self._session.get(MigrationRunModel, run_id)
        if run is None:
            raise TransitionError(f"run does not exist: {run_id}")
        current = run.state_version
        body: dict[str, str | int | None] = {
            "previous_state_version": current,
            "next_state_version": current,
            "actor": actor,
            "reason": reason,
            "request_checksum": canonical_audit_checksum(
                run_id=run_id, idempotency_key=idempotency_key, event_type=event_type,
                actor=actor, reason=reason, payload=payload,
            ),
        }
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
        step = self._validate_step_status(request, now)
        if request.next_step_status in {StepStatus.PASSED, StepStatus.FAILED, StepStatus.CANCELLED}:
            step.completed_at = now
        step.status = request.next_step_status.value

    def _validate_step_status(self, request: TransitionRequest, now: datetime) -> StageStepModel:
        if request.step_id is None or request.next_step_status is None:
            raise TransitionError("step status transition requires step_id")
        step = self._session.get(StageStepModel, request.step_id)
        if step is None or step.run_id != request.run_id:
            raise TransitionError(f"step does not belong to run: {request.step_id}")
        if request.next_step_status in {StepStatus.PASSED, StepStatus.FAILED, StepStatus.CANCELLED}:
            if request.worker_id is None or not self._has_current_lease(request.run_id, request.worker_id, now):
                raise LeaseRequiredError("worker cannot complete a step without a current lease")
        return step

    def _append_event(self, request: TransitionRequest, occurred_at: datetime, payload: dict[str, str | int | None]) -> WorkflowEventModel:
        return append_workflow_event(
            self._session,
            run_id=request.run_id,
            stage_id=request.stage_id,
            event_type=request.event_type.value,
            idempotency_key=request.idempotency_key,
            actor=request.actor,
            reason=request.reason,
            payload=payload,
            occurred_at=occurred_at,
        )

    def _find_idempotent_event(self, run_id: str, idempotency_key: str) -> WorkflowEventModel | None:
        return self._session.scalar(
            select(WorkflowEventModel)
            .where(WorkflowEventModel.run_id == run_id)
            .where(WorkflowEventModel.idempotency_key == idempotency_key)
        )

    @staticmethod
    def _request_checksum(request: TransitionRequest) -> str:
        return canonical_request_checksum(request)

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


def canonical_request_checksum(request: TransitionRequest) -> str:
    """Canonical checksum of a transition request, used to verify replays."""
    body = {
        "run_id": request.run_id,
        "idempotency_key": request.idempotency_key,
        "expected_state_version": request.expected_state_version,
        "event_type": request.event_type.value,
        "next_run_status": request.next_run_status.value if request.next_run_status else None,
        "next_run_phase": request.next_run_phase,
        "next_phase_status": request.next_phase_status,
        "next_approval_status": request.next_approval_status,
        "next_stage_status": request.next_stage_status.value if request.next_stage_status else None,
        "next_step_status": request.next_step_status.value if request.next_step_status else None,
        "stage_id": request.stage_id,
        "step_id": request.step_id,
        "actor": request.actor,
        "reason": request.reason,
        "worker_id": request.worker_id,
        "payload": request.payload,
    }
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def canonical_audit_checksum(*, run_id: str, idempotency_key: str, event_type: WorkflowEventType, actor: str, reason: str, payload: dict[str, str | int | None] | None) -> str:
    """Canonical checksum of an audit/evidence event, used to verify replays."""
    body = {
        "run_id": run_id,
        "idempotency_key": idempotency_key,
        "event_type": event_type.value,
        "actor": actor,
        "reason": reason,
        "payload": payload,
    }
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
