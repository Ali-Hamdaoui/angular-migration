from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from contextlib import contextmanager
from sqlalchemy.orm import sessionmaker

from app.repositories.models import Base, MigrationRunModel, PlanningJobModel
from app.services.planning_job_service import claim_planning_job, ensure_planning_job


NOW = datetime(2026, 7, 27, tzinfo=UTC)


def test_due_retry_job_is_not_claimable_before_next_attempt(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.add(MigrationRunModel(id="run-1", status="PLANNING_RUNNING", run_phase="FEASIBILITY_PLANNING", phase_status="running", approval_status="approved", repair_status="not_required", state_version=1, actor="operator", created_at=NOW, updated_at=NOW))
        session.add(PlanningJobModel(id="planning-run-1", run_id="run-1", thread_id="planning:run-1", status="waiting_retry", current_step="resolving_feasibility", actor="operator", attempt=1, max_attempts=3, next_attempt_at=NOW + timedelta(minutes=5), idempotency_key="planning-after-g04:run-1:v1", state_version=1, created_at=NOW, updated_at=NOW))

    @contextmanager
    def scope():
        session = sessions()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    monkeypatch.setattr("app.services.planning_job_service.session_scope", scope)

    assert claim_planning_job("run-1", "worker-1", now=NOW, scope=scope) is None
    assert claim_planning_job("run-1", "worker-1", now=NOW + timedelta(minutes=5), scope=scope) == "planning-run-1"


def test_feasibility_command_replay_is_idempotent_and_can_start_a_new_terminal_generation():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        run = MigrationRunModel(
            id="run-2", status="PLANNING_RUNNING", run_phase="FEASIBILITY_PLANNING", phase_status="running",
            approval_status="approved", repair_status="not_required", state_version=1, actor="operator",
            created_at=NOW, updated_at=NOW,
        )
        session.add(run)
        session.flush()
        first = ensure_planning_job(
            session, run, "operator", "package-v1", NOW,
            idempotency_key="planning-command:repeat-click",
        )
        replay = ensure_planning_job(
            session, run, "operator", "package-v1", NOW,
            idempotency_key="planning-command:repeat-click",
        )
        assert replay.id == first.id

        first.status = "completed_blocked"
        second = ensure_planning_job(
            session, run, "operator", "package-v1", NOW,
            idempotency_key="planning-command:retry-after-evidence-fix",
        )

    assert second.id != first.id
    assert second.status == "queued_after_g04"
