from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.preflight import PreflightSnapshot
from app.domain.contracts import RunStatus, WorkflowEventType
from app.repositories.models import ActiveRunClaimModel, ArtifactMetadataModel, Base, MigrationRunModel, PathValidationModel, SourceIntakeJobModel, TargetReservationModel, WorkflowEventModel
from app.repositories.preflight_models import ApprovalGateModel, PreflightModel
from app.services.migration_run_service import CreateRunRequest, MigrationRunError, MigrationRunService
from app.core.config import Settings
from app.orchestration.source_intake import SourceIntakeDispatcher
import app.orchestration.source_intake as source_intake_module
from app.state import IdempotencyPayloadMismatchError


class RecordingGraph:
    def __init__(self):
        self.calls = []

    def start(self, *, run_id: str, thread_id: str) -> None:
        self.calls.append((run_id, thread_id))


class FailingGraph:
    def start(self, *, run_id: str, thread_id: str) -> None:
        raise RuntimeError("test handoff failure")


def _service(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'runs.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def scope():
        with sessions() as session:
            yield session
            session.commit()

    now = datetime.now(UTC)
    snapshot = PreflightSnapshot(
        preflight_id="preflight-1", gate_id="G01", gate_version="g01-v1", state_version=1,
        status="passed", created_at=now, expires_at=now + timedelta(minutes=5),
        input_checksum="sha256:input", artifact_set_checksum="sha256:artifacts",
        target_angular_family="21.x", migration_mode="strict-functional-parity",
        source_path="C:/source", target_parent_path=str(tmp_path / "migration-results"), generated_output_name="customer-portal-angular-21", resolved_output_root=str(tmp_path / "migration-results" / "customer-portal-angular-21"), target_output_path=str(tmp_path / "migration-results" / "customer-portal-angular-21"),
    )
    with scope() as session:
        path_snapshot = {"validation_id": "path-1", "captured_at": now.isoformat(), "policy_version": "path-v1", "status": "passed", "source_path": "C:/source", "target_parent_path": str(tmp_path / "migration-results"), "generated_output_name": "customer-portal-angular-21", "resolved_output_root": str(tmp_path / "migration-results" / "customer-portal-angular-21"), "target_output_path": str(tmp_path / "migration-results" / "customer-portal-angular-21"), "reservation_id": "reservation-1", "reservation_expires_at": (now + timedelta(minutes=15)).isoformat(), "source_fingerprint": "sha256:source", "rules": [], "blockers": [], "warnings": [], "target_reservation_eligible": True, "checksum": "sha256:path"}
        session.add(PreflightModel(id="preflight-1", idempotency_key="pf-1", actor="reviewer", gate_id="G01", gate_version="g01-v1", state_version=1, status="passed", input_checksum="sha256:input", artifact_set_checksum="sha256:artifacts", expires_at=snapshot.expires_at, binding={"path_validation_id": "path-1"}, snapshot=snapshot.model_copy(update={"target_reservation_id": "reservation-1"}).model_dump(mode="json"), created_at=now))
        session.add(PathValidationModel(id="path-1", idempotency_key="path-1", actor="operator", status="passed", source_fingerprint="sha256:source", checksum="sha256:path", snapshot=path_snapshot, created_at=now))
        session.add(TargetReservationModel(id="reservation-1", validation_id="path-1", target_path=str(tmp_path / "migration-results" / "customer-portal-angular-21"), status="reserved", expires_at=now + timedelta(minutes=15), created_at=now))
        session.add(ApprovalGateModel(id="gate-1", preflight_id="preflight-1", gate_id="G01", gate_version="g01-v1", status="approved", state_version=2, input_checksum="sha256:input", artifact_set_checksum="sha256:artifacts", expires_at=snapshot.expires_at, created_at=now))
    graph = RecordingGraph()
    settings = Settings(_env_file=None, artifact_root=tmp_path / "artifacts", workspace_root=tmp_path / "workspaces", snapshot_root=tmp_path / "snapshots", delivery_root=tmp_path / "delivery", sandbox_root=tmp_path / "sandboxes")
    return MigrationRunService(settings, session_scope_factory=scope, graph=graph, now_provider=lambda: now), scope, graph


def _request(key="create-1"):
    return CreateRunRequest("preflight-1", "sha256:input", "sha256:artifacts", key, "reviewer", {"preserve_ui": True})


def test_create_and_start_use_authoritative_transitions(tmp_path: Path):
    service, scope, graph = _service(tmp_path)
    created = service.create(_request())
    assert created.status == "CREATED"
    with scope() as session:
        reservation = session.get(TargetReservationModel, "reservation-1")
        claim = session.scalar(select(ActiveRunClaimModel).where(ActiveRunClaimModel.run_id == created.run_id))
        assert reservation is not None and reservation.status == "claimed"
        assert claim is not None
        reservation.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    started = service.start(run_id=created.run_id, expected_state_version=created.state_version, idempotency_key="start-1", actor="operator")
    assert started.status == "SOURCE_VALIDATION_RUNNING"
    assert graph.calls == [(created.run_id, created.graph_thread_id)]
    replayed_start = service.start(run_id=created.run_id, expected_state_version=created.state_version, idempotency_key="start-1", actor="operator")
    assert replayed_start.idempotent_replay is True
    with scope() as session:
        jobs = list(session.scalars(select(SourceIntakeJobModel).where(SourceIntakeJobModel.run_id == created.run_id)))
        assert len(jobs) == 1 and jobs[0].status == "queued"
    replay = service.create(_request())
    assert replay.idempotent_replay is True


def test_second_active_run_is_rejected(tmp_path: Path):
    service, _, _ = _service(tmp_path)
    service.create(_request())
    with pytest.raises(MigrationRunError, match="Only one mutating"):
        service.create(_request("create-2"))


def test_cancelling_a_quiescent_run_records_evidence_and_releases_its_claim(tmp_path: Path):
    service, scope, _ = _service(tmp_path)
    created = service.create(_request())

    cancelled = service.cancel(
        run_id=created.run_id, expected_state_version=created.state_version,
        idempotency_key="cancel-1", actor="operator",
    )

    assert cancelled.status == RunStatus.CANCELLED.value
    assert service.cancel(run_id=created.run_id, expected_state_version=created.state_version, idempotency_key="cancel-1", actor="operator").idempotent_replay
    replacement = service.create(_request("create-2"))
    assert replacement.run_id != created.run_id
    with scope() as session:
        events = list(session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == created.run_id)))
        assert events[-1].event_type == "RUN_CANCELLED"
        assert session.scalar(select(ActiveRunClaimModel).where(ActiveRunClaimModel.run_id == created.run_id)) is None


def test_stale_target_claim_is_replaced_before_new_claim_is_created(tmp_path: Path):
    service, scope, _ = _service(tmp_path)
    stale = service.create(_request("stale-owner"))

    with scope() as session:
        run = session.get(MigrationRunModel, stale.run_id)
        assert run is not None
        run.status = RunStatus.FAILED.value

    created = service.create(_request("replacement-owner"))

    with scope() as session:
        claims = list(session.scalars(select(ActiveRunClaimModel)))
        assert len(claims) == 1
        assert claims[0].run_id == created.run_id


def test_rejected_stale_preflight_does_not_create_run_or_artifacts(tmp_path: Path):
    service, scope, _ = _service(tmp_path)

    with pytest.raises(MigrationRunError, match="stale"):
        service.create(CreateRunRequest("preflight-1", "sha256:old", "sha256:artifacts", "stale-1", "reviewer", {}))

    with scope() as session:
        assert session.scalar(select(MigrationRunModel)) is None
        assert session.scalar(select(WorkflowEventModel)) is None
    assert not (tmp_path / "artifacts").exists()


def test_graph_handoff_failure_rolls_back_accepted_transition(tmp_path: Path):
    service, scope, _ = _service(tmp_path)
    failing = MigrationRunService(
        Settings(_env_file=None, artifact_root=tmp_path / "artifacts", workspace_root=tmp_path / "workspaces", snapshot_root=tmp_path / "snapshots", delivery_root=tmp_path / "delivery", sandbox_root=tmp_path / "sandboxes"),
        session_scope_factory=scope, graph=FailingGraph(), now_provider=lambda: datetime.now(UTC),
    )
    created = service.create(_request("handoff-create"))

    with pytest.raises(MigrationRunError, match="handoff failed safely"):
        failing.start(run_id=created.run_id, expected_state_version=created.state_version, idempotency_key="handoff-start", actor="operator")

    with scope() as session:
        run = session.get(MigrationRunModel, created.run_id)
        events = list(session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == created.run_id).order_by(WorkflowEventModel.sequence)))
        assert run is not None and run.status == RunStatus.FAILED.value
        assert [event.event_type for event in events][-2:] == ["SOURCE_INTAKE_QUEUED", "SOURCE_INTAKE_FAILED"]


def test_start_rejects_when_run_owned_target_claim_is_missing(tmp_path: Path):
    service, scope, _ = _service(tmp_path)
    created = service.create(_request("missing-claim-create"))
    with scope() as session:
        claim = session.scalar(select(ActiveRunClaimModel).where(ActiveRunClaimModel.run_id == created.run_id))
        assert claim is not None
        session.delete(claim)

    with pytest.raises(MigrationRunError, match="target reservation"):
        service.start(run_id=created.run_id, expected_state_version=created.state_version, idempotency_key="missing-claim-start", actor="operator")


def test_start_rejects_when_g01_is_no_longer_approved(tmp_path: Path):
    service, scope, _ = _service(tmp_path)
    created = service.create(_request("revoked-g01-create"))
    with scope() as session:
        gate = session.scalar(select(ApprovalGateModel).where(ApprovalGateModel.preflight_id == "preflight-1", ApprovalGateModel.gate_id == "G01"))
        assert gate is not None
        gate.status = "stale"

    with pytest.raises(MigrationRunError, match="G01"):
        service.start(run_id=created.run_id, expected_state_version=created.state_version, idempotency_key="revoked-g01-start", actor="operator")


def test_source_intake_failure_finalization_marks_run_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    service, scope, _ = _service(tmp_path)
    created = service.create(_request("worker-failure-create"))
    with scope() as session:
        session.add(SourceIntakeJobModel(
            id="intake-worker-failure",
            run_id=created.run_id,
            thread_id=created.graph_thread_id,
            status="running",
            actor="operator",
            idempotency_key="worker-failure-start",
            attempt=1,
            queued_at=datetime.now(UTC),
            started_at=datetime.now(UTC),
            state_version=created.state_version,
        ))
    monkeypatch.setattr(source_intake_module, "session_scope", scope)
    dispatcher = SourceIntakeDispatcher(Settings(_env_file=None, artifact_root=tmp_path / "artifacts", workspace_root=tmp_path / "workspaces", snapshot_root=tmp_path / "snapshots", delivery_root=tmp_path / "delivery", sandbox_root=tmp_path / "sandboxes"))
    try:
        dispatcher._fail("intake-worker-failure", "SNAPSHOT_CREATION_FAILED", "source disappeared")
    finally:
        dispatcher._executor.shutdown(wait=True)

    with scope() as session:
        run = session.get(MigrationRunModel, created.run_id)
        job = session.get(SourceIntakeJobModel, "intake-worker-failure")
        events = list(session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == created.run_id)))
        assert run is not None and run.status == RunStatus.FAILED.value
        assert job is not None and job.status == "failed"
        assert events[-1].event_type == "SOURCE_INTAKE_FAILED"


def test_source_intake_retry_preserves_failed_attempt_and_queues_new_job(tmp_path: Path):
    service, scope, graph = _service(tmp_path)
    created = service.create(_request("retry-create"))
    with scope() as session:
        run = session.get(MigrationRunModel, created.run_id)
        assert run is not None
        run.status = RunStatus.FAILED.value
        session.add(SourceIntakeJobModel(
            id="intake-failed-attempt",
            run_id=created.run_id,
            thread_id=created.graph_thread_id,
            status="failed",
            actor="operator",
            idempotency_key="failed-attempt",
            attempt=1,
            queued_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            last_error_code="SNAPSHOT_CREATION_FAILED",
            last_error_message="source disappeared",
            state_version=run.state_version,
        ))
        expected_version = run.state_version

    retried = service.retry_source_intake(run_id=created.run_id, expected_state_version=expected_version, idempotency_key="retry-source-1", actor="operator")
    assert retried.status == RunStatus.SOURCE_VALIDATION_RUNNING.value
    assert retried.job_id != "intake-failed-attempt"
    assert graph.calls[-1] == (created.run_id, created.graph_thread_id)
    with scope() as session:
        jobs = list(session.scalars(select(SourceIntakeJobModel).where(SourceIntakeJobModel.run_id == created.run_id).order_by(SourceIntakeJobModel.attempt)))
        assert len(jobs) == 2
        assert jobs[0].status == "failed"
        assert jobs[1].status == "queued"
        assert jobs[1].attempt == 2


def test_source_intake_retry_accepts_retryable_baseline_diagnostic_hold(tmp_path: Path):
    service, scope, graph = _service(tmp_path)
    created = service.create(_request("retry-baseline-hold-create"))
    with scope() as session:
        run = session.get(MigrationRunModel, created.run_id)
        assert run is not None
        run.status = RunStatus.DIAGNOSTIC_HOLD.value
        claim = session.scalar(select(ActiveRunClaimModel).where(ActiveRunClaimModel.run_id == created.run_id))
        assert claim is not None
        claim.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.add(SourceIntakeJobModel(
            id="intake-baseline-hold", run_id=created.run_id, thread_id=created.graph_thread_id,
            status="failed", actor="operator", idempotency_key="baseline-hold-attempt", attempt=1,
            queued_at=datetime.now(UTC), finished_at=datetime.now(UTC),
            last_error_code="BASELINE_PREQUALIFICATION_BLOCKED", last_error_message="lockfile blocked",
            state_version=run.state_version,
        ))
        expected_version = run.state_version

    retried = service.retry_source_intake(
        run_id=created.run_id,
        expected_state_version=expected_version,
        idempotency_key="retry-baseline-hold-1",
        actor="operator",
    )

    assert retried.status == RunStatus.SOURCE_VALIDATION_RUNNING.value
    assert graph.calls[-1] == (created.run_id, created.graph_thread_id)


def test_source_intake_retry_accepts_recoverable_baseline_validation_hold(tmp_path: Path):
    service, scope, graph = _service(tmp_path)
    created = service.create(_request("retry-baseline-validation-create"))
    with scope() as session:
        run = session.get(MigrationRunModel, created.run_id)
        assert run is not None
        run.status = RunStatus.DIAGNOSTIC_HOLD.value
        session.add(SourceIntakeJobModel(
            id="intake-baseline-validation-hold", run_id=created.run_id, thread_id=created.graph_thread_id,
            status="failed", actor="operator", idempotency_key="baseline-validation-attempt", attempt=1,
            queued_at=datetime.now(UTC), finished_at=datetime.now(UTC),
            last_error_code="BaselineValidationApplicationError", last_error_message="dependency evidence was unavailable",
            state_version=run.state_version,
        ))
        expected_version = run.state_version

    retried = service.retry_source_intake(
        run_id=created.run_id,
        expected_state_version=expected_version,
        idempotency_key="retry-baseline-validation-1",
        actor="operator",
    )

    assert retried.status == RunStatus.SOURCE_VALIDATION_RUNNING.value
    assert graph.calls[-1] == (created.run_id, created.graph_thread_id)


def test_source_intake_retry_recovers_restart_hold_after_g03_approval(tmp_path: Path):
    service, scope, graph = _service(tmp_path)
    created = service.create(_request("retry-g03-restart-create"))
    with scope() as session:
        run = session.get(MigrationRunModel, created.run_id)
        assert run is not None
        run.status = RunStatus.DIAGNOSTIC_HOLD.value
        session.add(SourceIntakeJobModel(
            id="intake-g03-restart-hold", run_id=created.run_id, thread_id=created.graph_thread_id,
            status="failed", actor="operator", idempotency_key="g03-restart-attempt", attempt=1,
            queued_at=datetime.now(UTC), finished_at=datetime.now(UTC),
            last_error_code="G03_APPROVAL_REQUIRED", last_error_message="restart misclassified the waiting G03 boundary",
            state_version=run.state_version,
        ))
        session.add(WorkflowEventModel(
            id="event-g03-approved-for-restart", run_id=created.run_id,
            event_type=WorkflowEventType.G03_APPROVED.value, idempotency_key="g03-approved-for-restart",
            actor="operator", reason="G03 approved before restart", sequence=999,
            payload={"decision": "approved"}, occurred_at=datetime.now(UTC),
        ))
        expected_version = run.state_version

    retried = service.retry_source_intake(
        run_id=created.run_id,
        expected_state_version=expected_version,
        idempotency_key="retry-g03-restart-1",
        actor="operator",
    )

    assert retried.status == RunStatus.SOURCE_VALIDATION_RUNNING.value
    assert graph.calls[-1] == (created.run_id, created.graph_thread_id)
    with scope() as session:
        jobs = list(session.scalars(select(SourceIntakeJobModel).where(SourceIntakeJobModel.run_id == created.run_id).order_by(SourceIntakeJobModel.attempt)))
        assert jobs[-1].status == "waiting_g03"


def test_source_intake_retry_recovers_g03_restart_hold_after_gate_advances_run(tmp_path: Path):
    service, scope, graph = _service(tmp_path)
    created = service.create(_request("retry-g03-qualified-create"))
    with scope() as session:
        run = session.get(MigrationRunModel, created.run_id)
        assert run is not None
        run.status = RunStatus.BASELINE_QUALIFIED.value
        session.add(SourceIntakeJobModel(
            id="intake-g03-qualified-hold", run_id=created.run_id, thread_id=created.graph_thread_id,
            status="failed", actor="operator", idempotency_key="g03-qualified-attempt", attempt=1,
            queued_at=datetime.now(UTC), finished_at=datetime.now(UTC),
            last_error_code="G03_APPROVAL_REQUIRED", last_error_message="restart misclassified the waiting G03 boundary",
            state_version=run.state_version,
        ))
        session.add(WorkflowEventModel(
            id="event-g03-approved-for-qualified-restart", run_id=created.run_id,
            event_type=WorkflowEventType.G03_APPROVED.value, idempotency_key="g03-approved-qualified-restart",
            actor="operator", reason="G03 approved before restart", sequence=999,
            payload={"decision": "approved"}, occurred_at=datetime.now(UTC),
        ))
        expected_version = run.state_version

    retried = service.retry_source_intake(
        run_id=created.run_id,
        expected_state_version=expected_version,
        idempotency_key="retry-g03-qualified-1",
        actor="operator",
    )

    assert retried.status == RunStatus.SOURCE_VALIDATION_RUNNING.value
    assert graph.calls[-1] == (created.run_id, created.graph_thread_id)
    with scope() as session:
        jobs = list(session.scalars(select(SourceIntakeJobModel).where(SourceIntakeJobModel.run_id == created.run_id).order_by(SourceIntakeJobModel.attempt)))
        assert jobs[-1].status == "waiting_g03"


def test_source_intake_recovery_leaves_unapproved_g03_boundary_parked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    service, scope, _ = _service(tmp_path)
    created = service.create(_request("waiting-g03-recovery-create"))
    with scope() as session:
        run = session.get(MigrationRunModel, created.run_id)
        assert run is not None
        session.add(SourceIntakeJobModel(
            id="intake-waiting-g03", run_id=created.run_id, thread_id=created.graph_thread_id,
            status="waiting_g03", actor="operator", idempotency_key="waiting-g03-attempt", attempt=1,
            queued_at=datetime.now(UTC), state_version=run.state_version,
        ))

    monkeypatch.setattr(source_intake_module, "session_scope", scope)
    dispatcher = SourceIntakeDispatcher(Settings(
        _env_file=None, artifact_root=tmp_path / "artifacts", workspace_root=tmp_path / "workspaces",
        snapshot_root=tmp_path / "snapshots", delivery_root=tmp_path / "delivery", sandbox_root=tmp_path / "sandboxes",
    ))
    started = []
    dispatcher.start = lambda **kwargs: started.append(kwargs)
    try:
        assert dispatcher.recover() == 0
    finally:
        dispatcher._executor.shutdown(wait=True)

    assert started == []


def test_source_intake_retry_recovers_expired_bound_reservation(tmp_path: Path):
    service, scope, graph = _service(tmp_path)
    created = service.create(_request("retry-expired-reservation-create"))
    with scope() as session:
        run = session.get(MigrationRunModel, created.run_id)
        assert run is not None
        run.status = RunStatus.DIAGNOSTIC_HOLD.value
        claim = session.scalar(select(ActiveRunClaimModel).where(ActiveRunClaimModel.run_id == created.run_id))
        reservation = session.get(TargetReservationModel, "reservation-1")
        assert claim is not None and reservation is not None
        claim.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        reservation.status = "claimed"
        reservation.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.add(SourceIntakeJobModel(
            id="intake-expired-reservation", run_id=created.run_id, thread_id=created.graph_thread_id,
            status="failed", actor="operator", idempotency_key="expired-reservation-attempt", attempt=1,
            queued_at=datetime.now(UTC), finished_at=datetime.now(UTC),
            last_error_code="BaselineValidationApplicationError", last_error_message="baseline evidence was unavailable",
            state_version=run.state_version,
        ))
        expected_version = run.state_version

    retried = service.retry_source_intake(
        run_id=created.run_id,
        expected_state_version=expected_version,
        idempotency_key="retry-expired-reservation-1",
        actor="operator",
    )

    assert retried.status == RunStatus.SOURCE_VALIDATION_RUNNING.value
    assert graph.calls[-1] == (created.run_id, created.graph_thread_id)
    with scope() as session:
        reservation = session.get(TargetReservationModel, "reservation-1")
        assert reservation is not None and reservation.expires_at.replace(tzinfo=UTC) > datetime.now(UTC)


def test_source_intake_retry_accepts_recoverable_restart_idempotency_hold(tmp_path: Path):
    service, scope, graph = _service(tmp_path)
    created = service.create(_request("retry-restart-idempotency-create"))
    with scope() as session:
        run = session.get(MigrationRunModel, created.run_id)
        assert run is not None
        run.status = RunStatus.DIAGNOSTIC_HOLD.value
        session.add(SourceIntakeJobModel(
            id="intake-restart-idempotency", run_id=created.run_id, thread_id=created.graph_thread_id,
            status="failed", actor="operator", idempotency_key="restart-idempotency-attempt", attempt=1,
            queued_at=datetime.now(UTC), finished_at=datetime.now(UTC),
            last_error_code="IdempotencyPayloadMismatchError", last_error_message="recovered start event conflicted",
            state_version=run.state_version,
        ))
        expected_version = run.state_version

    retried = service.retry_source_intake(
        run_id=created.run_id,
        expected_state_version=expected_version,
        idempotency_key="retry-restart-idempotency-1",
        actor="operator",
    )

    assert retried.status == RunStatus.SOURCE_VALIDATION_RUNNING.value
    assert graph.calls[-1] == (created.run_id, created.graph_thread_id)


def test_source_intake_attempt_identity_does_not_change_when_reclaimed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    service, scope, _ = _service(tmp_path)
    created = service.create(_request("stable-attempt-create"))
    with scope() as session:
        job = SourceIntakeJobModel(
            id="intake-stable-attempt", run_id=created.run_id, thread_id=created.graph_thread_id,
            status="queued", actor="operator", idempotency_key="stable-attempt-start", attempt=2,
            queued_at=datetime.now(UTC), state_version=created.state_version,
        )
        session.add(job)
    monkeypatch.setattr(source_intake_module, "session_scope", scope)
    dispatcher = SourceIntakeDispatcher(Settings(_env_file=None, artifact_root=tmp_path / "artifacts", workspace_root=tmp_path / "workspaces", snapshot_root=tmp_path / "snapshots", delivery_root=tmp_path / "delivery", sandbox_root=tmp_path / "sandboxes"))
    try:
        claimed = dispatcher._claim(created.run_id)
    finally:
        dispatcher._executor.shutdown(wait=True)
    assert claimed is not None and claimed.attempt == 2


def test_source_intake_recovery_reuses_existing_started_event(tmp_path: Path):
    service, scope, _ = _service(tmp_path)
    created = service.create(_request("started-event-recovery"))
    with scope() as session:
        run = session.get(MigrationRunModel, created.run_id)
        assert run is not None
        job = SourceIntakeJobModel(
            id="intake-started-event", run_id=created.run_id, thread_id=created.graph_thread_id,
            status="running", actor="operator", idempotency_key="started-event-job", attempt=2,
            queued_at=datetime.now(UTC), started_at=datetime.now(UTC), state_version=run.state_version,
        )
        session.add(job)
        session.add(WorkflowEventModel(
            id="event-existing-started", run_id=created.run_id,
            event_type=WorkflowEventType.SOURCE_INTAKE_STARTED.value,
            idempotency_key="started-event-job:started", actor="operator",
            reason="durable source-intake worker started", sequence=999,
            payload={"worker_id": "previous-worker"}, occurred_at=datetime.now(UTC),
        ))
        session.flush()
        dispatcher = SourceIntakeDispatcher(Settings(
            _env_file=None, artifact_root=tmp_path / "artifacts", workspace_root=tmp_path / "workspaces",
            snapshot_root=tmp_path / "snapshots", delivery_root=tmp_path / "delivery", sandbox_root=tmp_path / "sandboxes",
        ))
        try:
            dispatcher._record_started_event(session, created.run_id, job)
        finally:
            dispatcher._executor.shutdown(wait=True)
        assert len(list(session.scalars(select(WorkflowEventModel).where(
            WorkflowEventModel.run_id == created.run_id,
            WorkflowEventModel.idempotency_key == "started-event-job:started",
        )))) == 1


def test_start_replay_rejects_different_request_payload(tmp_path: Path):
    service, _, _ = _service(tmp_path)
    created = service.create(_request("replay-start-create"))
    started = service.start(run_id=created.run_id, expected_state_version=created.state_version, idempotency_key="start-1", actor="operator")
    assert started.idempotent_replay is False

    with pytest.raises(IdempotencyPayloadMismatchError):
        service.start(run_id=created.run_id, expected_state_version=started.state_version + 99, idempotency_key="start-1", actor="operator")


def test_cancel_replay_rejects_different_request_payload(tmp_path: Path):
    service, _, _ = _service(tmp_path)
    created = service.create(_request("replay-cancel-create"))
    cancelled = service.cancel(run_id=created.run_id, expected_state_version=created.state_version, idempotency_key="cancel-1", actor="operator")
    assert cancelled.status == RunStatus.CANCELLED.value

    with pytest.raises(IdempotencyPayloadMismatchError):
        service.cancel(run_id=created.run_id, expected_state_version=cancelled.state_version + 1, idempotency_key="cancel-1", actor="operator")


@pytest.mark.parametrize("error_code", ["SNAPSHOT_CREATION_FAILED", "BaselineApplicationError"])
def test_retry_source_intake_replay_rejects_different_request_payload(tmp_path: Path, error_code: str):
    service, scope, _ = _service(tmp_path)
    created = service.create(_request("replay-retry-create"))
    with scope() as session:
        run = session.get(MigrationRunModel, created.run_id)
        assert run is not None
        run.status = RunStatus.FAILED.value
        session.add(SourceIntakeJobModel(
            id="intake-replay-failed",
            run_id=created.run_id,
            thread_id=created.graph_thread_id,
            status="failed",
            actor="operator",
            idempotency_key="replay-failed-attempt",
            attempt=1,
            queued_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            last_error_code=error_code,
            last_error_message="source disappeared",
            state_version=run.state_version,
        ))
        expected_version = run.state_version

    retried = service.retry_source_intake(run_id=created.run_id, expected_state_version=expected_version, idempotency_key="retry-source-1", actor="operator")
    assert retried.status == RunStatus.SOURCE_VALIDATION_RUNNING.value
    replay = service.retry_source_intake(run_id=created.run_id, expected_state_version=expected_version, idempotency_key="retry-source-1", actor="operator")
    assert replay.idempotent_replay is True

    with pytest.raises(IdempotencyPayloadMismatchError):
        service.retry_source_intake(run_id=created.run_id, expected_state_version=retried.state_version + 1, idempotency_key="retry-source-1", actor="operator")


def test_run_evidence_is_recorded_with_checksums_and_confined_paths(tmp_path: Path):
    service, scope, _ = _service(tmp_path)
    created = service.create(_request("evidence-1"))

    assert len(created.artifacts) == 8
    assert all(artifact.relative_path.startswith("00_job_setup/") for artifact in created.artifacts)
    assert all(".." not in Path(artifact.relative_path).parts for artifact in created.artifacts)
    with scope() as session:
        metadata = list(session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == created.run_id)))
        assert len(metadata) == 8
        assert {row.checksum for row in metadata} == {artifact.checksum for artifact in created.artifacts}

def test_run_creates_only_registered_external_setup_directories(tmp_path: Path) -> None:
    service, scope, _ = _service(tmp_path)
    created = service.create(_request("external-layout"))
    with scope() as session:
        run = session.get(MigrationRunModel, created.run_id)
        assert run is not None
        root = Path(run.resolved_output_root)
        assert Path(run.artifact_root).is_relative_to(root)
        assert Path(run.log_root).is_relative_to(root)
        assert Path(run.report_root).is_relative_to(root)
        assert Path(run.temporary_root).is_relative_to(root)
        assert (root / ".migration-factory" / "runs" / created.run_id / "artifacts").is_dir()
        assert not (root / "migrated-app").exists()
        assert not (root / ".migration-factory" / "runs" / created.run_id / "source-snapshot").exists()
        assert not (root / ".migration-factory" / "runs" / created.run_id / "baseline-sandbox").exists()
