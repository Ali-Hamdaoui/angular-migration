"""Durable planning-job lifecycle and restart recovery."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib

from sqlalchemy import func, or_, select, update

from app.repositories.models import MigrationRunModel, PlanningJobModel
from app.repositories.session import session_scope


PLANNING_JOB_STATES = frozenset({
    "queued_after_g04",
    "resolving_feasibility",
    "waiting_g05",
    "generating_plan",
    "running_planning_review",
    "waiting_g06",
    "waiting_retry",
    "completed",
    "completed_blocked",
    "technical_failed",
})
PLANNING_JOB_TERMINAL_STATES = frozenset({"completed", "completed_blocked", "technical_failed"})
PLANNING_JOB_HUMAN_WAIT_STATES = frozenset({"waiting_g05", "waiting_g06"})
PLANNING_JOB_CLAIMABLE_STATES = frozenset({
    "queued_after_g04", "resolving_feasibility", "generating_plan", "running_planning_review", "waiting_retry"
})
PLANNING_JOB_ACTIVE_STATES = PLANNING_JOB_CLAIMABLE_STATES
PLANNING_JOB_NONTERMINAL_STATES = PLANNING_JOB_CLAIMABLE_STATES | PLANNING_JOB_HUMAN_WAIT_STATES


def is_terminal_state(status: str) -> bool:
    return status in PLANNING_JOB_TERMINAL_STATES


def is_human_wait_state(status: str) -> bool:
    return status in PLANNING_JOB_HUMAN_WAIT_STATES


def is_claimable_state(status: str) -> bool:
    return status in PLANNING_JOB_CLAIMABLE_STATES


def claim_planning_job(run_id: str, worker_id: str, *, now: datetime | None = None, lease_seconds: int = 120, scope=session_scope):
    now = now or datetime.now(UTC)
    with scope() as session:
        candidate = session.scalar(
            select(PlanningJobModel)
            .where(
                PlanningJobModel.run_id == run_id,
                PlanningJobModel.status.in_(PLANNING_JOB_CLAIMABLE_STATES),
                (PlanningJobModel.status != "waiting_retry") | (PlanningJobModel.next_attempt_at.is_(None)) | (PlanningJobModel.next_attempt_at <= now),
                PlanningJobModel.attempt < PlanningJobModel.max_attempts,
                or_(PlanningJobModel.lease_expires_at.is_(None), PlanningJobModel.lease_expires_at <= now),
            )
            .order_by(PlanningJobModel.created_at.desc())
        )
        if candidate is None:
            return None
        claimed = session.execute(
            update(PlanningJobModel)
            .where(
                PlanningJobModel.id == candidate.id,
                PlanningJobModel.status.in_(PLANNING_JOB_CLAIMABLE_STATES),
                PlanningJobModel.attempt < PlanningJobModel.max_attempts,
                or_(PlanningJobModel.lease_expires_at.is_(None), PlanningJobModel.lease_expires_at <= now),
            )
            .values(
                worker_id=worker_id,
                attempt=PlanningJobModel.attempt + 1,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                started_at=func.coalesce(PlanningJobModel.started_at, now),
                updated_at=now,
            )
        )
        if claimed.rowcount != 1:
            return None
        session.flush()
        return candidate.id


def recover_planning_jobs(*, now: datetime | None = None, scope=session_scope) -> int:
    """Reclaim expired work without advancing human approval waits."""
    now = now or datetime.now(UTC)
    recovered = 0
    with scope() as session:
        jobs = session.scalars(select(PlanningJobModel).where(PlanningJobModel.status.in_(PLANNING_JOB_ACTIVE_STATES))).all()
        for job in jobs:
            if job.status in {"waiting_g05", "waiting_g06", "queued_after_g04"}:
                continue
            if job.lease_expires_at is not None and job.lease_expires_at > now:
                continue
            job.status = "waiting_retry"
            job.current_step = job.current_step or "recovery"
            job.worker_id = None
            job.lease_expires_at = None
            job.last_error_code = job.last_error_code or "PLANNING_WORKER_INTERRUPTED"
            job.last_error_message = job.last_error_message or "The planning worker lease expired before completion."
            job.last_error_stage = job.last_error_stage or job.current_step
            job.retryable = True
            job.first_failed_at = job.first_failed_at or now
            job.next_attempt_at = now
            job.updated_at = now
            recovered += 1
        session.flush()
    return recovered


def ensure_planning_job(session, run: MigrationRunModel, actor: str, package_checksum: str, now: datetime, *, idempotency_key: str | None = None) -> PlanningJobModel:
    generation_key = idempotency_key or f"planning-after-g04:{run.id}:{package_checksum}"
    replay = session.scalar(select(PlanningJobModel).where(PlanningJobModel.run_id == run.id, PlanningJobModel.idempotency_key == generation_key))
    if replay is not None:
        return replay
    existing = session.scalar(
        select(PlanningJobModel).where(PlanningJobModel.run_id == run.id, PlanningJobModel.status.in_(PLANNING_JOB_NONTERMINAL_STATES)).order_by(PlanningJobModel.created_at.desc())
    )
    if existing is not None:
        return existing
    generation_id = hashlib.sha256(generation_key.encode()).hexdigest()[:12]
    job = PlanningJobModel(
        id=f"planning-{run.id}-{generation_id}", run_id=run.id, thread_id=f"planning:{run.id}", status="queued_after_g04", current_step="resolving_feasibility",
        actor=actor, worker_id=None, attempt=0, lease_expires_at=None, idempotency_key=generation_key,
        correlation_id=f"planning:{run.id}", max_attempts=3, next_attempt_at=None, last_error_code=None, last_error_message=None, last_error_stage=None, retryable=None, first_failed_at=None, terminal_failed_at=None, state_version=run.state_version,
        created_at=now, started_at=None, updated_at=now, completed_at=None,
    )
    session.add(job)
    session.flush()
    return job


def enqueue_planning_job(run_id: str, *, actor: str, expected_state_version: int, idempotency_key: str, scope=session_scope):
    """Idempotently expose the backend-owned feasibility command boundary."""
    with scope() as session:
        run = session.get(MigrationRunModel, run_id)
        if run is None:
            raise ValueError("RUN_NOT_FOUND")
        if run.actor and run.actor != actor:
            raise ValueError("RUN_NOT_AUTHORIZED")
        if run.state_version != expected_state_version:
            raise ValueError("STALE_STATE_VERSION")
        from app.repositories.models import G04ApprovalModel
        gate = session.scalar(select(G04ApprovalModel).where(G04ApprovalModel.run_id == run_id, G04ApprovalModel.status == "approved").order_by(G04ApprovalModel.created_at.desc()))
        if gate is None:
            raise ValueError("PLANNING_G04_BINDING_STALE")
        job = ensure_planning_job(session, run, actor, gate.package_checksum, datetime.now(UTC), idempotency_key=f"planning-command:{idempotency_key}")
        return {"job_id": job.id, "status": job.status, "current_step": job.current_step, "correlation_id": job.correlation_id}
