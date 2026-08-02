"""JobSupervisor service for G01 S3-F04.

Manages active command ownership, WorkerLease heartbeat/expiry,
process-tree termination, timeout, cancel idempotency, and
Transition Service cancellation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.contracts import RunStatus, WorkflowEventType
from app.repositories.models.workflow import (
    CommandExecutionModel,
    WorkerLeaseModel,
    WorkflowEventModel,
    MigrationRunModel,
)
from app.repositories.models import TransformationContinuationModel
from app.state.transition_service import (
    StateTransitionService,
    TransitionRequest,
    LeaseRequiredError,
)


class JobSupervisorError(ValueError):
    """Raised when a job supervision operation fails."""
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


_CANCEL_EVENTS: dict[str, Any] = {}


@dataclass(frozen=True)
class LeaseResult:
    """Result of a lease operation."""
    lease_id: str
    run_id: str
    worker_id: str
    status: str
    expires_at: datetime


class JobSupervisorService:
    """Active command ownership and lifecycle management.

    One run has at most one active command at a time. The supervisor
    manages heartbeats, timeouts, and cancellation.
    """

    def __init__(self, lease_seconds: int = 120) -> None:
        self._lease_seconds = lease_seconds

    def register_cancel_event(self, execution_id: str, event: Any) -> None:
        _CANCEL_EVENTS[execution_id] = event

    def unregister_cancel_event(self, execution_id: str) -> None:
        _CANCEL_EVENTS.pop(execution_id, None)

    def signal_cancel(self, execution_id: str) -> bool:
        event = _CANCEL_EVENTS.get(execution_id)
        if event is None:
            return False
        event.set()
        return True

    def acquire_lease(
        self,
        session: Session,
        run_id: str,
        execution_id: str,
        worker_id: str,
        lease_owner: str,
    ) -> LeaseResult:
        """Acquire an exclusive worker lease for a run."""
        now = datetime.now(UTC)

        # Check for existing active lease (non-expired)
        existing = session.scalar(
            select(WorkerLeaseModel)
            .where(WorkerLeaseModel.run_id == run_id)
            .where(WorkerLeaseModel.expires_at > now)
            .order_by(WorkerLeaseModel.acquired_at.desc())
            .limit(1)
        )
        if existing is not None:
            raise JobSupervisorError(
                "LEASE_EXISTS",
                f"Run {run_id} already has an active lease owned by {existing.lease_owner}",
            )

        lease_id = f"lease-{uuid4().hex[:12]}"
        expires_at = now + timedelta(seconds=self._lease_seconds)
        lease = WorkerLeaseModel(
            id=lease_id,
            run_id=run_id,
            execution_id=execution_id,
            worker_id=worker_id,
            lease_owner=lease_owner,
            backend_instance_id="hermes-worktree-01",
            acquired_at=now,
            heartbeat_at=now,
            expires_at=expires_at,
        )
        session.add(lease)
        session.flush()

        return LeaseResult(
            lease_id=lease_id,
            run_id=run_id,
            worker_id=worker_id,
            status="active",
            expires_at=expires_at,
        )

    def renew_lease(
        self,
        session: Session,
        lease_id: str,
        worker_id: str,
    ) -> LeaseResult:
        """Renew a worker lease by extending its expiry."""
        now = datetime.now(UTC)
        lease = session.get(WorkerLeaseModel, lease_id)
        if lease is None:
            raise JobSupervisorError("LEASE_NOT_FOUND", f"Lease {lease_id} not found")
        if lease.worker_id != worker_id:
            raise JobSupervisorError("LEASE_OWNER_MISMATCH", "Worker does not own this lease")

        expires = lease.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires <= now:
            raise JobSupervisorError("LEASE_EXPIRED", "Lease has already expired")

        lease.expires_at = now + timedelta(seconds=self._lease_seconds)
        lease.heartbeat_at = now
        session.flush()

        return LeaseResult(
            lease_id=lease.id,
            run_id=lease.run_id,
            worker_id=lease.worker_id,
            status="active",
            expires_at=lease.expires_at,
        )

    def release_lease(
        self,
        session: Session,
        lease_id: str,
        worker_id: str,
    ) -> None:
        """Release a lease explicitly."""
        lease = session.get(WorkerLeaseModel, lease_id)
        if lease is None:
            raise JobSupervisorError("LEASE_NOT_FOUND", f"Lease {lease_id} not found")
        if lease.worker_id != worker_id:
            raise JobSupervisorError("LEASE_OWNER_MISMATCH", "Worker does not own this lease")
        session.delete(lease)
        session.flush()

    def cancel_command(
        self,
        session: Session,
        run_id: str,
        execution_id: str,
        actor: str,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Request cancellation of a running command."""
        now = datetime.now(UTC)

        # Check idempotency
        existing = session.scalar(
            select(WorkflowEventModel)
            .where(WorkflowEventModel.run_id == run_id)
            .where(WorkflowEventModel.idempotency_key == idempotency_key)
        )
        if existing is not None:
            if (existing.payload or {}).get("execution_id") != execution_id:
                raise JobSupervisorError("IDEMPOTENCY_KEY_CONFLICT", "Cancellation idempotency key belongs to another execution")
            return {"idempotent_replay": True, "event_id": existing.id}

        # Find the command execution
        exec_model = session.scalar(select(CommandExecutionModel).where(
            CommandExecutionModel.id == execution_id,
            CommandExecutionModel.run_id == run_id,
        ))
        if exec_model is None:
            raise JobSupervisorError("EXECUTION_NOT_FOUND", f"Command execution {execution_id} not found")
        if exec_model.status not in {"queued", "pending", "running"}:
            raise JobSupervisorError(
                "EXECUTION_NOT_ACTIVE",
                f"Command execution is {exec_model.status}, cannot cancel",
            )

        # Update the execution record
        # ``cancelled`` is a durable request marker until the worker records
        # its terminal status; status itself remains RUNNING during teardown.
        exec_model.cancelled = True
        exec_model.cancel_requested_at = now
        exec_model.cancel_requested_by = actor
        exec_model.cancel_idempotency_key = idempotency_key
        queued = exec_model.status == "queued"
        if queued:
            exec_model.status = "cancelled"
            exec_model.finished_at = now
            exec_model.worker_id = None
            exec_model.claim_expires_at = None
            self._wake_command_waiter(session, exec_model, now)
        session.flush()

        # The worker emits the terminal command event after process-tree
        # termination and artifact finalization.
        signalled = False if queued else self.signal_cancel(execution_id)
        if queued:
            self._append_event(
                session,
                run_id,
                idempotency_key,
                WorkflowEventType.COMMAND_CANCELLED,
                "queued command cancelled before spawn",
                {"execution_id": execution_id, "actor": actor},
            )
            return {
                "execution_id": execution_id,
                "run_id": run_id,
                "cancelled": True,
                "signal_delivered": False,
                "cancel_requested_at": now.isoformat(),
                "idempotent_replay": False,
            }

        # Update run status to CANCELLING via Transition Service
        run = session.get(MigrationRunModel, run_id)
        if run is not None and run.status in {"CREATED", "RUNNING", "WAITING"}:
            StateTransitionService(session).apply_transition(
                TransitionRequest(
                    run_id=run_id,
                    idempotency_key=idempotency_key + ":transition",
                    expected_state_version=run.state_version,
                    event_type=WorkflowEventType.RUN_CANCEL_REQUESTED,
                    next_run_status=RunStatus.CANCELLING,
                    actor=actor,
                    reason=f"cancellation requested by {actor}",
                    occurred_at=now,
                    payload={"execution_id": execution_id, "signal_delivered": int(signalled)},
                )
            )
        else:
            run = session.get(MigrationRunModel, run_id)
            if run is not None:
                StateTransitionService(session).append_audit_event(
                    run_id=run_id, idempotency_key=idempotency_key,
                    event_type=WorkflowEventType.RUN_CANCEL_REQUESTED,
                    actor=actor, reason=f"cancellation requested by {actor}",
                    occurred_at=now, payload={"execution_id": execution_id, "signal_delivered": int(signalled)},
                )
            else:
                self._append_event(session, run_id, idempotency_key,
                                   WorkflowEventType.RUN_CANCEL_REQUESTED,
                                   f"cancellation requested by {actor}",
                                   {"execution_id": execution_id, "actor": actor})

        return {
            "execution_id": execution_id,
            "run_id": run_id,
            "cancelled": True,
            "signal_delivered": signalled,
            "cancel_requested_at": now.isoformat(),
            "idempotent_replay": False,
        }

    def get_active_command(
        self,
        session: Session,
        run_id: str,
    ) -> CommandExecutionModel | None:
        """Get the currently active (PENDING or RUNNING) command for a run."""
        return session.scalar(
            select(CommandExecutionModel)
            .where(CommandExecutionModel.run_id == run_id)
            .where(CommandExecutionModel.status.in_(["pending", "running"]))
            .order_by(CommandExecutionModel.requested_at.desc())
            .limit(1)
        )

    def get_active_lease(
        self,
        session: Session,
        run_id: str,
    ) -> WorkerLeaseModel | None:
        """Get the active worker lease for a run."""
        now = datetime.now(UTC)
        return session.scalar(
            select(WorkerLeaseModel)
            .where(WorkerLeaseModel.run_id == run_id)
            .where(WorkerLeaseModel.expires_at > now)
            .order_by(WorkerLeaseModel.acquired_at.desc())
            .limit(1)
        )

    @staticmethod
    def _wake_command_waiter(
        session: Session,
        execution: CommandExecutionModel,
        now: datetime,
    ) -> None:
        """Release a continuation parked on the cancelled command.

        A QUEUED command transitions straight to ``cancelled`` with no worker
        execution and therefore no worker wake; without this the parked
        ``waiting_command`` continuation would never resume. The wake only
        fires when the continuation is still parked, so repeated triggers
        (cancel + worker sweep) remain a single wake.
        """
        continuation = session.scalar(
            select(TransformationContinuationModel).where(
                TransformationContinuationModel.run_id == execution.run_id,
                TransformationContinuationModel.current_stage_id == execution.stage_id,
                TransformationContinuationModel.status == "waiting_command",
            )
        )
        if continuation is not None:
            continuation.status = "queued"
            continuation.wake_sequence += 1
            continuation.state_version += 1
            continuation.updated_at = now

    @staticmethod
    def _append_event(
        session: Session,
        run_id: str,
        idempotency_key: str,
        event_type: WorkflowEventType,
        reason: str,
        payload: dict[str, Any],
    ) -> WorkflowEventModel:
        latest = session.scalar(
            select(WorkflowEventModel)
            .where(WorkflowEventModel.run_id == run_id)
            .order_by(WorkflowEventModel.sequence.desc())
            .limit(1)
        )
        event = WorkflowEventModel(
            id=f"event-{uuid4().hex[:12]}",
            run_id=run_id,
            stage_id=None,
            event_type=event_type.value,
            idempotency_key=idempotency_key,
            actor="job-supervisor",
            reason=reason,
            sequence=(latest.sequence + 1) if latest else 1,
            payload=payload,
            occurred_at=datetime.now(UTC),
        )
        session.add(event)
        return event
