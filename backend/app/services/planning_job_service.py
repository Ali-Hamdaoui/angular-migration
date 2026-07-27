"""Durable planning-job lifecycle and restart recovery."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.repositories.models import MigrationRunModel, PlanningJobModel
from app.repositories.session import session_scope


PLANNING_JOB_ACTIVE_STATES = frozenset({
    "queued_after_g04", "resolving_feasibility", "waiting_g05", "generating_plan", "running_planning_review", "waiting_g06", "waiting_retry"
})


def claim_planning_job(run_id: str, worker_id: str, *, now: datetime | None = None, lease_seconds: int = 120):
    now = now or datetime.now(UTC)
    with session_scope() as session:
        job = session.scalar(
            select(PlanningJobModel)
            .where(PlanningJobModel.run_id == run_id, PlanningJobModel.status.in_(PLANNING_JOB_ACTIVE_STATES))
            .order_by(PlanningJobModel.created_at.desc())
        )
        if job is None:
            return None
        if job.lease_expires_at is not None and job.lease_expires_at > now and job.worker_id != worker_id:
            return None
        job.worker_id = worker_id
        job.attempt += 1
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        job.started_at = job.started_at or now
        job.updated_at = now
        session.flush()
        return job.id


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
            job.last_error_stage = job.last_error_stage or job.current_step
            job.retryable = True
            job.updated_at = now
            recovered += 1
        session.flush()
    return recovered


def ensure_planning_job(session, run: MigrationRunModel, actor: str, package_checksum: str, now: datetime) -> PlanningJobModel:
    existing = session.scalar(
        select(PlanningJobModel).where(PlanningJobModel.run_id == run.id, PlanningJobModel.status.in_(PLANNING_JOB_ACTIVE_STATES)).order_by(PlanningJobModel.created_at.desc())
    )
    if existing is not None:
        return existing
    job = PlanningJobModel(
        id=f"planning-{run.id}", run_id=run.id, thread_id=f"planning:{run.id}", status="queued_after_g04", current_step="resolving_feasibility",
        actor=actor, worker_id=None, attempt=0, lease_expires_at=None, idempotency_key=f"planning-after-g04:{run.id}:{package_checksum}",
        correlation_id=None, last_error_code=None, last_error_stage=None, retryable=None, state_version=run.state_version,
        created_at=now, started_at=None, updated_at=now, completed_at=None,
    )
    session.add(job)
    session.flush()
    return job
