from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from contextlib import contextmanager
from sqlalchemy.orm import sessionmaker

from app.repositories.models import (
    ArtifactMetadataModel,
    Base,
    MigrationRunModel,
    PlanningJobModel,
    WorkflowEventModel,
)
from app.orchestration.planning import _mark_retry
from app.services.planning_job_service import PlanningFailureDisposition
from app.services.planning_job_service import (
    claim_planning_job,
    ensure_planning_job,
    is_claimable_state,
    is_human_wait_state,
    is_terminal_state,
)


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


def test_planning_job_states_have_one_authoritative_classification():
    expected = {
        "queued_after_g04": (False, False, True, True),
        "resolving_feasibility": (False, False, True, True),
        "waiting_g05": (False, True, False, False),
        "generating_plan": (False, False, True, True),
        "running_planning_review": (False, False, True, True),
        "review_revision_required": (False, True, False, False),
        "review_rejected": (False, True, False, False),
        "review_insufficient_context": (False, True, False, False),
        "waiting_g06": (False, True, False, False),
        "waiting_retry": (False, False, True, True),
        "completed": (True, False, False, False),
        "completed_blocked": (True, False, False, False),
        "technical_failed": (True, False, False, False),
    }
    for state, (terminal, human_wait, claimable, active) in expected.items():
        assert is_terminal_state(state) is terminal
        assert is_human_wait_state(state) is human_wait
        assert is_claimable_state(state) is claimable
        assert (not terminal and not human_wait) is active


def test_terminal_review_failure_records_actual_stage_and_fails_run(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    artifact_root = tmp_path / "artifacts"
    with sessions.begin() as session:
        session.add(MigrationRunModel(
            id="run-review-failure",
            status="PLANNING_RUNNING",
            run_phase="FEASIBILITY_PLANNING",
            phase_status="running",
            approval_status="approved",
            repair_status="not_required",
            state_version=1,
            actor="operator",
            artifact_root=str(artifact_root),
            created_at=NOW,
            updated_at=NOW,
        ))
        session.add(PlanningJobModel(
            id="planning-review-failure",
            run_id="run-review-failure",
            thread_id="planning:run-review-failure",
            status="running_planning_review",
            current_step="running_planning_review",
            actor="operator",
            attempt=1,
            max_attempts=3,
            idempotency_key="planning-review-failure",
            state_version=1,
            created_at=NOW,
            updated_at=NOW,
        ))

    @contextmanager
    def scope():
        session = sessions()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    _mark_retry(
        "planning-review-failure",
        disposition=PlanningFailureDisposition(
            code="PLANNING_REVIEW_FAILED",
            retryable=False,
            terminal=True,
            public_message="review provider returned invalid output",
        ),
        stage="running_planning_review",
        scope=scope,
    )

    with sessions() as session:
        run = session.get(MigrationRunModel, "run-review-failure")
        job = session.get(PlanningJobModel, "planning-review-failure")
        events = session.query(WorkflowEventModel).order_by(WorkflowEventModel.sequence).all()
        artifact = session.query(ArtifactMetadataModel).one()
        assert run.status == "FAILED"
        assert run.phase_status == "failed"
        assert job.status == "technical_failed"
        assert [event.event_type for event in events] == ["PLANNING_FAILED"]
        assert events[0].reason == "planning review failed technically"
        assert events[0].payload["planning_stage"] == "running_planning_review"
        assert artifact.relative_path == "03_planning/planning-review-failure.json"
