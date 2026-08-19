"""Focused regression tests for the post-G03 source-intake continuation defect.

Reproduces and guards the causal chain:
  1. A healthy source_intake job was waiting_g03.
  2. Backend restart called recover() which redispatched waiting_g03.
  3. _continue_after_g03 ran before human G03 approval and hard-failed.
  4. Later G03 approval called resume_after_g03 which silently no-oped.

The fix:
  - recover() excludes waiting_g03 from redispatch (human-gate wait, not crashed work).
  - resume_after_g03 self-heals the narrow stranded condition
    (failed + G03_APPROVAL_REQUIRED + approved current G03 + BASELINE_QUALIFIED).
  - _continue_after_g03 re-arms waiting_g03 instead of hard-failing when G03
    is not yet approved.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.orchestration.source_intake as source_intake_module
from app.core.config import Settings
from app.domain.contracts import RunStatus, WorkflowEventType
from app.domain.preflight import PreflightSnapshot
from app.orchestration.source_intake import SourceIntakeDispatcher
from app.repositories.baseline_g03_models import G03ApprovalModel
from app.repositories.models import (
    ActiveRunClaimModel,
    Base,
    MigrationRunModel,
    PathValidationModel,
    SourceIntakeJobModel,
    TargetReservationModel,
    WorkflowEventModel,
)
from app.repositories.preflight_models import ApprovalGateModel, PreflightModel
from app.services.migration_run_service import CreateRunRequest, MigrationRunService


def _service(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'post-g03.db'}")
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
        source_path="C:/source", target_parent_path=str(tmp_path / "migration-results"),
        generated_output_name="customer-portal-angular-21",
        resolved_output_root=str(tmp_path / "migration-results" / "customer-portal-angular-21"),
        target_output_path=str(tmp_path / "migration-results" / "customer-portal-angular-21"),
    )
    with scope() as session:
        path_snapshot = {
            "validation_id": "path-1", "captured_at": now.isoformat(), "policy_version": "path-v1",
            "status": "passed", "source_path": "C:/source",
            "target_parent_path": str(tmp_path / "migration-results"),
            "generated_output_name": "customer-portal-angular-21",
            "resolved_output_root": str(tmp_path / "migration-results" / "customer-portal-angular-21"),
            "target_output_path": str(tmp_path / "migration-results" / "customer-portal-angular-21"),
            "reservation_id": "reservation-1",
            "reservation_expires_at": (now + timedelta(minutes=15)).isoformat(),
            "source_fingerprint": "sha256:source", "rules": [], "blockers": [], "warnings": [],
            "target_reservation_eligible": True, "checksum": "sha256:path",
        }
        session.add(PreflightModel(
            id="preflight-1", idempotency_key="pf-1", actor="reviewer",
            gate_id="G01", gate_version="g01-v1", state_version=1, status="passed",
            input_checksum="sha256:input", artifact_set_checksum="sha256:artifacts",
            expires_at=snapshot.expires_at, binding={"path_validation_id": "path-1"},
            snapshot=snapshot.model_copy(update={"target_reservation_id": "reservation-1"}).model_dump(mode="json"),
            created_at=now,
        ))
        session.add(PathValidationModel(
            id="path-1", idempotency_key="path-1", actor="operator", status="passed",
            source_fingerprint="sha256:source", checksum="sha256:path",
            snapshot=path_snapshot, created_at=now,
        ))
        session.add(TargetReservationModel(
            id="reservation-1", validation_id="path-1",
            target_path=str(tmp_path / "migration-results" / "customer-portal-angular-21"),
            status="reserved", expires_at=now + timedelta(minutes=15), created_at=now,
        ))
        session.add(ApprovalGateModel(
            id="gate-1", preflight_id="preflight-1", gate_id="G01", gate_version="g01-v1",
            status="approved", state_version=2, input_checksum="sha256:input",
            artifact_set_checksum="sha256:artifacts", expires_at=snapshot.expires_at,
            created_at=now,
        ))
    settings = Settings(
        _env_file=None,
        artifact_root=tmp_path / "artifacts",
        workspace_root=tmp_path / "workspaces",
        snapshot_root=tmp_path / "snapshots",
        delivery_root=tmp_path / "delivery",
        sandbox_root=tmp_path / "sandboxes",
    )
    return MigrationRunService(settings, session_scope_factory=scope, now_provider=lambda: now), scope, settings


def _request(key="create-1", preflight_id="preflight-1"):
    return CreateRunRequest(preflight_id, "sha256:input", "sha256:artifacts", key, "reviewer", {"preserve_ui": True})


def _seed_job(scope, run_id, *, job_id, status, thread_id, attempt=1, error_code=None, error_message=None, state_version=1):
    with scope() as session:
        session.add(SourceIntakeJobModel(
            id=job_id, run_id=run_id, thread_id=thread_id, status=status,
            actor="operator", idempotency_key=job_id, attempt=attempt,
            queued_at=datetime.now(UTC), started_at=datetime.now(UTC) if status == "running" else None,
            finished_at=datetime.now(UTC) if status == "failed" else None,
            last_error_code=error_code, last_error_message=error_message,
            state_version=state_version,
        ))


def _seed_g03_approval(scope, run_id, *, status="approved", state_version=1):
    now = datetime.now(UTC)
    with scope() as session:
        session.add(G03ApprovalModel(
            id=f"g03-{run_id[-8:]}", run_id=run_id, gate_id="G03", gate_version="g03-v1",
            idempotency_key=f"g03-approval-{run_id}", actor="reviewer", status=status,
            decision=status, package_checksum="sha256:g03-pkg",
            evidence_set_checksum="sha256:g03-evidence",
            qualification_status="qualified_with_known_failures",
            policy_version="baseline-policy-v1", state_version=state_version,
            event_sequence=0, sandbox_fingerprint="sha256:sandbox",
            execution_profile_checksum="sha256:profile",
            package={"package_checksum": "sha256:g03-pkg"},
            artifact_ids=[], created_at=now, updated_at=now,
        ))


def _seed_g03_approved_event(scope, run_id):
    now = datetime.now(UTC)
    with scope() as session:
        run = session.get(MigrationRunModel, run_id)
        existing = session.scalar(select(WorkflowEventModel).where(
            WorkflowEventModel.run_id == run_id,
            WorkflowEventModel.idempotency_key == f"g03-event-{run_id}",
        ))
        if existing is not None:
            return
        next_seq = (max(e.sequence for e in session.scalars(
            select(WorkflowEventModel).where(WorkflowEventModel.run_id == run_id)
        )) if session.scalar(select(WorkflowEventModel).where(
            WorkflowEventModel.run_id == run_id
        )) is not None else 0) + 1
        session.add(WorkflowEventModel(
            id=f"event-g03-{run_id[-8:]}", run_id=run_id, stage_id=None,
            event_type=WorkflowEventType.G03_APPROVED.value,
            idempotency_key=f"g03-event-{run_id}", actor="reviewer",
            reason="G03 decision recorded", sequence=next_seq,
            payload={"decision": "approved"}, occurred_at=now,
        ))


def _set_run_status(scope, run_id, status, state_version=None):
    with scope() as session:
        run = session.get(MigrationRunModel, run_id)
        assert run is not None
        run.status = status
        if state_version is not None:
            run.state_version = state_version


def _make_dispatcher(settings, monkeypatch=None, *, record_continue=False, record_run=False):
    dispatcher = SourceIntakeDispatcher(settings)
    if record_continue:
        calls: list[tuple[str, str, str]] = []
        def _fake_continue_after_g03(job_id, run_id, actor):
            calls.append((job_id, run_id, actor))
        monkeypatch.setattr(dispatcher, "_continue_after_g03", _fake_continue_after_g03)
        dispatcher._test_continue_calls = calls
    if record_run:
        run_calls: list[tuple[str, str]] = []
        def _fake_run(run_id, thread_id):
            run_calls.append((run_id, thread_id))
        monkeypatch.setattr(dispatcher, "_run", _fake_run)
        dispatcher._test_run_calls = run_calls
    return dispatcher


def _flush(dispatcher):
    dispatcher._executor.shutdown(wait=True)


# ---------------------------------------------------------------------------
# Test 1 + 7: recover() leaves waiting_g03 dormant (with and without approved G03)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("with_approved_g03", [False, True], ids=["no-approval", "with-approval"])
def test_recover_leaves_waiting_g03_dormant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, with_approved_g03: bool):
    """recover() must not redispatch a dormant waiting_g03 job, regardless of G03 state."""
    service, scope, settings = _service(tmp_path)
    created = service.create(_request("recover-waiting-g03"))
    _set_run_status(scope, created.run_id, RunStatus.SOURCE_VALIDATED.value, state_version=10)
    _seed_job(scope, created.run_id, job_id="intake-waiting", status="waiting_g03",
              thread_id=created.graph_thread_id, state_version=10)
    if with_approved_g03:
        _seed_g03_approval(scope, created.run_id, state_version=10)
        _seed_g03_approved_event(scope, created.run_id)

    dispatcher = _make_dispatcher(settings, monkeypatch, record_run=True)
    monkeypatch.setattr(source_intake_module, "session_scope", scope)
    try:
        count = dispatcher.recover()
    finally:
        _flush(dispatcher)

    assert count == 0
    assert getattr(dispatcher, "_test_run_calls", []) == []
    with scope() as session:
        job = session.get(SourceIntakeJobModel, "intake-waiting")
        assert job is not None and job.status == "waiting_g03"
        events = list(session.scalars(select(WorkflowEventModel).where(
            WorkflowEventModel.run_id == created.run_id,
            WorkflowEventModel.event_type.in_({"BASELINE_BLOCKED", "SOURCE_INTAKE_FAILED"}),
        )))
        assert events == []
        run = session.get(MigrationRunModel, created.run_id)
        assert run.status == RunStatus.SOURCE_VALIDATED.value


# ---------------------------------------------------------------------------
# Test 2: recover() preserves existing behavior for genuinely recoverable running work
# ---------------------------------------------------------------------------

def test_recover_redispatches_running_job_from_dead_worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """recover() must still requeue and dispatch a running job owned by a dead worker."""
    service, scope, settings = _service(tmp_path)
    created = service.create(_request("recover-running"))
    _set_run_status(scope, created.run_id, RunStatus.SOURCE_VALIDATION_RUNNING.value, state_version=5)
    _seed_job(scope, created.run_id, job_id="intake-dead-worker", status="running",
              thread_id=created.graph_thread_id, state_version=5)

    dispatcher = _make_dispatcher(settings, monkeypatch, record_run=True)
    monkeypatch.setattr(source_intake_module, "session_scope", scope)
    try:
        count = dispatcher.recover()
    finally:
        _flush(dispatcher)

    assert count == 1
    assert dispatcher._test_run_calls == [(created.run_id, created.graph_thread_id)]
    with scope() as session:
        job = session.get(SourceIntakeJobModel, "intake-dead-worker")
        assert job is not None and job.status == "queued"


# ---------------------------------------------------------------------------
# Test 3: happy path — waiting_g03 + approved G03 → resume_after_g03 dispatches
# ---------------------------------------------------------------------------

def test_resume_after_g03_happy_path_dispatches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """waiting_g03 + approved G03 → resume_after_g03 dispatches _continue_after_g03."""
    service, scope, settings = _service(tmp_path)
    created = service.create(_request("happy-path"))
    _set_run_status(scope, created.run_id, RunStatus.BASELINE_QUALIFIED.value, state_version=97)
    _seed_job(scope, created.run_id, job_id="intake-happy", status="waiting_g03",
              thread_id=created.graph_thread_id, state_version=52)
    _seed_g03_approval(scope, created.run_id, state_version=97)

    dispatcher = _make_dispatcher(settings, monkeypatch, record_continue=True)
    monkeypatch.setattr(source_intake_module, "session_scope", scope)
    try:
        dispatcher.resume_after_g03(created.run_id)
    finally:
        _flush(dispatcher)

    assert len(dispatcher._test_continue_calls) == 1
    assert dispatcher._test_continue_calls[0][1] == created.run_id


# ---------------------------------------------------------------------------
# Test 4: stranded repro — failed + G03_APPROVAL_REQUIRED + approved G03 → self-heals
# ---------------------------------------------------------------------------

def test_resume_after_g03_self_heals_stranded_failed_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The exact repro: failed+G03_APPROVAL_REQUIRED + approved G03 + BASELINE_QUALIFIED → re-arm + dispatch."""
    service, scope, settings = _service(tmp_path)
    created = service.create(_request("stranded-repro"))
    _set_run_status(scope, created.run_id, RunStatus.BASELINE_QUALIFIED.value, state_version=98)
    _seed_job(scope, created.run_id, job_id="intake-stranded", status="failed",
              thread_id=created.graph_thread_id, attempt=1,
              error_code="G03_APPROVAL_REQUIRED",
              error_message="Approved G03 is required before discovery.",
              state_version=52)
    _seed_g03_approval(scope, created.run_id, state_version=98)

    dispatcher = _make_dispatcher(settings, monkeypatch, record_continue=True)
    monkeypatch.setattr(source_intake_module, "session_scope", scope)
    try:
        dispatcher.resume_after_g03(created.run_id)
    finally:
        _flush(dispatcher)

    assert len(dispatcher._test_continue_calls) == 1
    assert dispatcher._test_continue_calls[0][1] == created.run_id
    with scope() as session:
        jobs = list(session.scalars(select(SourceIntakeJobModel).where(
            SourceIntakeJobModel.run_id == created.run_id,
        ).order_by(SourceIntakeJobModel.attempt)))
        assert len(jobs) == 2
        assert jobs[0].status == "failed"
        assert jobs[0].last_error_code == "G03_APPROVAL_REQUIRED"
        assert jobs[1].attempt == 2
        assert jobs[1].status in {"waiting_g03", "running"}
        queued_events = list(session.scalars(select(WorkflowEventModel).where(
            WorkflowEventModel.run_id == created.run_id,
            WorkflowEventModel.event_type == WorkflowEventType.SOURCE_INTAKE_QUEUED.value,
        )))
        assert any("re-arm" in (e.reason or "") for e in queued_events)


# ---------------------------------------------------------------------------
# Test 5: failed + unrelated error_code + approved G03 → MUST NOT auto-revive
# ---------------------------------------------------------------------------

def test_resume_after_g03_does_not_revive_unrelated_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A failed job with a different error code must not be auto-revived."""
    service, scope, settings = _service(tmp_path)
    created = service.create(_request("unrelated-failure"))
    _set_run_status(scope, created.run_id, RunStatus.FAILED.value, state_version=50)
    _seed_job(scope, created.run_id, job_id="intake-snapshot-fail", status="failed",
              thread_id=created.graph_thread_id, attempt=1,
              error_code="SNAPSHOT_CREATION_FAILED",
              error_message="source disappeared",
              state_version=40)
    _seed_g03_approval(scope, created.run_id, state_version=50)

    dispatcher = _make_dispatcher(settings, monkeypatch, record_continue=True)
    monkeypatch.setattr(source_intake_module, "session_scope", scope)
    try:
        dispatcher.resume_after_g03(created.run_id)
    finally:
        _flush(dispatcher)

    assert getattr(dispatcher, "_test_continue_calls", []) == []
    with scope() as session:
        jobs = list(session.scalars(select(SourceIntakeJobModel).where(
            SourceIntakeJobModel.run_id == created.run_id,
        )))
        assert len(jobs) == 1
        assert jobs[0].status == "failed"
        assert jobs[0].last_error_code == "SNAPSHOT_CREATION_FAILED"


# ---------------------------------------------------------------------------
# Test 6: repeated/idempotent G03 approval → no duplicate dispatch
# ---------------------------------------------------------------------------

def test_resume_after_g03_idempotent_no_duplicate_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Calling resume_after_g03 twice must not create a duplicate continuation."""
    service, scope, settings = _service(tmp_path)
    created = service.create(_request("idempotent"))
    _set_run_status(scope, created.run_id, RunStatus.BASELINE_QUALIFIED.value, state_version=98)
    _seed_job(scope, created.run_id, job_id="intake-stranded-idem", status="failed",
              thread_id=created.graph_thread_id, attempt=1,
              error_code="G03_APPROVAL_REQUIRED",
              error_message="Approved G03 is required before discovery.",
              state_version=52)
    _seed_g03_approval(scope, created.run_id, state_version=98)

    dispatcher = _make_dispatcher(settings, monkeypatch, record_continue=True)
    monkeypatch.setattr(source_intake_module, "session_scope", scope)
    try:
        dispatcher.resume_after_g03(created.run_id)
        _flush(dispatcher)
        dispatcher2 = _make_dispatcher(settings, monkeypatch, record_continue=True)
        monkeypatch.setattr(source_intake_module, "session_scope", scope)
        dispatcher2.resume_after_g03(created.run_id)
        _flush(dispatcher2)
    finally:
        pass

    total_calls = len(dispatcher._test_continue_calls) + len(dispatcher2._test_continue_calls)
    assert total_calls == 1
    with scope() as session:
        rearm_jobs = list(session.scalars(select(SourceIntakeJobModel).where(
            SourceIntakeJobModel.run_id == created.run_id,
            SourceIntakeJobModel.status == "waiting_g03",
        )))
        assert len(rearm_jobs) <= 1


# ---------------------------------------------------------------------------
# Test 8: full regression sequence — waiting_g03 → recover() → approve G03 → dispatch
# ---------------------------------------------------------------------------

def test_full_regression_sequence_recover_then_approve_then_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """waiting_g03 → recover() leaves it dormant → approve G03 → resume_after_g03 → _continue_after_g03 dispatched."""
    service, scope, settings = _service(tmp_path)
    created = service.create(_request("full-regression"))
    _set_run_status(scope, created.run_id, RunStatus.SOURCE_VALIDATED.value, state_version=52)
    _seed_job(scope, created.run_id, job_id="intake-regression", status="waiting_g03",
              thread_id=created.graph_thread_id, state_version=52)

    # Simulate backend restart: recover() must leave waiting_g03 untouched.
    dispatcher = _make_dispatcher(settings, monkeypatch, record_run=True)
    monkeypatch.setattr(source_intake_module, "session_scope", scope)
    try:
        count = dispatcher.recover()
    finally:
        _flush(dispatcher)
    assert count == 0
    assert dispatcher._test_run_calls == []
    with scope() as session:
        job = session.get(SourceIntakeJobModel, "intake-regression")
        assert job is not None and job.status == "waiting_g03"

    # Simulate human G03 approval.
    _set_run_status(scope, created.run_id, RunStatus.BASELINE_QUALIFIED.value, state_version=98)
    _seed_g03_approval(scope, created.run_id, state_version=98)

    # resume_after_g03 (called by BaselineG03ApplicationService.decide) dispatches.
    dispatcher2 = _make_dispatcher(settings, monkeypatch, record_continue=True)
    monkeypatch.setattr(source_intake_module, "session_scope", scope)
    try:
        dispatcher2.resume_after_g03(created.run_id)
    finally:
        _flush(dispatcher2)

    assert len(dispatcher2._test_continue_calls) == 1
    assert dispatcher2._test_continue_calls[0][1] == created.run_id


# ---------------------------------------------------------------------------
# Test 9: _continue_after_g03 re-arms waiting_g03 when G03 not yet approved
# ---------------------------------------------------------------------------

def test_continue_after_g03_rearms_waiting_g03_when_g03_not_approved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """If _continue_after_g03 is reached before G03 approval, it re-arms waiting_g03 instead of failing."""
    service, scope, settings = _service(tmp_path)
    created = service.create(_request("premature-dispatch"))
    _set_run_status(scope, created.run_id, RunStatus.SOURCE_VALIDATED.value, state_version=52)
    _seed_job(scope, created.run_id, job_id="intake-premature", status="running",
              thread_id=created.graph_thread_id, state_version=52)
    # No G03 approval seeded.

    dispatcher = _make_dispatcher(settings, monkeypatch)
    monkeypatch.setattr(source_intake_module, "session_scope", scope)
    try:
        dispatcher._continue_after_g03("intake-premature", created.run_id, "operator")
    finally:
        _flush(dispatcher)

    with scope() as session:
        job = session.get(SourceIntakeJobModel, "intake-premature")
        assert job is not None
        assert job.status == "waiting_g03"
        assert job.started_at is None
        run = session.get(MigrationRunModel, created.run_id)
        assert run.status == RunStatus.SOURCE_VALIDATED.value
        block_events = list(session.scalars(select(WorkflowEventModel).where(
            WorkflowEventModel.run_id == created.run_id,
            WorkflowEventModel.event_type.in_({"BASELINE_BLOCKED", "SOURCE_INTAKE_FAILED"}),
        )))
        assert block_events == []


# ---------------------------------------------------------------------------
# Startup-recovery hook: recover() self-heals the historical stranded signature
# by delegating to resume_after_g03 -> _rearm_stranded_after_g03.
# ---------------------------------------------------------------------------

def _seed_stranded(scope, run_id, *, job_id="intake-stranded-startup", thread_id=None,
                   error_code="G03_APPROVAL_REQUIRED",
                   state_version=52, with_approval=True, run_status=None, approval_version=98):
    _set_run_status(scope, run_id, run_status or RunStatus.BASELINE_QUALIFIED.value, state_version=approval_version)
    _seed_job(scope, run_id, job_id=job_id, status="failed",
              thread_id=thread_id or run_id, attempt=1,
              error_code=error_code,
              error_message="Approved G03 is required before discovery.",
              state_version=state_version)
    if with_approval:
        _seed_g03_approval(scope, run_id, state_version=approval_version)


def test_recover_self_heals_stranded_after_g03_on_startup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """recover() self-heals failed+G03_APPROVAL_REQUIRED + BASELINE_QUALIFIED + approved G03 → one successor dispatched."""
    service, scope, settings = _service(tmp_path)
    created = service.create(_request("startup-stranded"))
    _seed_stranded(scope, created.run_id, job_id="intake-startup-1", thread_id=created.graph_thread_id)

    dispatcher = _make_dispatcher(settings, monkeypatch, record_continue=True)
    monkeypatch.setattr(source_intake_module, "session_scope", scope)
    try:
        count = dispatcher.recover()
    finally:
        _flush(dispatcher)

    assert count == 1
    assert len(dispatcher._test_continue_calls) == 1
    assert dispatcher._test_continue_calls[0][1] == created.run_id
    with scope() as session:
        jobs = list(session.scalars(select(SourceIntakeJobModel).where(
            SourceIntakeJobModel.run_id == created.run_id,
        ).order_by(SourceIntakeJobModel.attempt)))
        assert len(jobs) == 2
        assert jobs[0].status == "failed"
        assert jobs[0].last_error_code == "G03_APPROVAL_REQUIRED"
        assert jobs[1].attempt == 2
        assert jobs[1].status in {"waiting_g03", "running", "completed"}
        queued_events = list(session.scalars(select(WorkflowEventModel).where(
            WorkflowEventModel.run_id == created.run_id,
            WorkflowEventModel.event_type == WorkflowEventType.SOURCE_INTAKE_QUEUED.value,
        )))
        assert any("re-arm" in (e.reason or "") for e in queued_events)


def test_recover_does_not_self_heal_without_approved_g03(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Same stranded state but NO approved G03 → no recovery, no successor."""
    service, scope, settings = _service(tmp_path)
    created = service.create(_request("startup-no-g03"))
    _seed_stranded(scope, created.run_id, job_id="intake-startup-no-g03",
                   thread_id=created.graph_thread_id, with_approval=False)

    dispatcher = _make_dispatcher(settings, monkeypatch, record_continue=True)
    monkeypatch.setattr(source_intake_module, "session_scope", scope)
    try:
        count = dispatcher.recover()
    finally:
        _flush(dispatcher)

    assert count == 0
    assert getattr(dispatcher, "_test_continue_calls", []) == []
    with scope() as session:
        jobs = list(session.scalars(select(SourceIntakeJobModel).where(
            SourceIntakeJobModel.run_id == created.run_id,
        )))
        assert len(jobs) == 1
        assert jobs[0].status == "failed"


def test_recover_does_not_self_heal_unrelated_error_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """failed job with unrelated error code → no recovery, no successor."""
    service, scope, settings = _service(tmp_path)
    created = service.create(_request("startup-unrelated"))
    _seed_stranded(scope, created.run_id, job_id="intake-startup-unrelated",
                   thread_id=created.graph_thread_id,
                   error_code="SNAPSHOT_CREATION_FAILED")

    dispatcher = _make_dispatcher(settings, monkeypatch, record_continue=True)
    monkeypatch.setattr(source_intake_module, "session_scope", scope)
    try:
        count = dispatcher.recover()
    finally:
        _flush(dispatcher)

    assert count == 0
    assert getattr(dispatcher, "_test_continue_calls", []) == []
    with scope() as session:
        jobs = list(session.scalars(select(SourceIntakeJobModel).where(
            SourceIntakeJobModel.run_id == created.run_id,
        )))
        assert len(jobs) == 1
        assert jobs[0].status == "failed"
        assert jobs[0].last_error_code == "SNAPSHOT_CREATION_FAILED"


def test_recover_does_not_self_heal_when_run_not_baseline_qualified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """failed+G03_APPROVAL_REQUIRED + approved G03 but run not BASELINE_QUALIFIED → no recovery."""
    service, scope, settings = _service(tmp_path)
    created = service.create(_request("startup-wrong-status"))
    _seed_stranded(scope, created.run_id, job_id="intake-startup-wrong-status",
                   thread_id=created.graph_thread_id,
                   run_status=RunStatus.DIAGNOSTIC_HOLD.value)

    dispatcher = _make_dispatcher(settings, monkeypatch, record_continue=True)
    monkeypatch.setattr(source_intake_module, "session_scope", scope)
    try:
        count = dispatcher.recover()
    finally:
        _flush(dispatcher)

    assert count == 0
    assert getattr(dispatcher, "_test_continue_calls", []) == []
    with scope() as session:
        jobs = list(session.scalars(select(SourceIntakeJobModel).where(
            SourceIntakeJobModel.run_id == created.run_id,
        )))
        assert len(jobs) == 1
        assert jobs[0].status == "failed"


def test_recover_repeated_startup_replay_no_duplicate_successor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """recover() then recover() again → exactly one successor, no duplicate dispatch."""
    service, scope, settings = _service(tmp_path)
    created = service.create(_request("startup-replay"))
    _seed_stranded(scope, created.run_id, job_id="intake-startup-replay",
                   thread_id=created.graph_thread_id)

    dispatcher = _make_dispatcher(settings, monkeypatch, record_continue=True)
    monkeypatch.setattr(source_intake_module, "session_scope", scope)
    try:
        first = dispatcher.recover()
        _flush(dispatcher)
        dispatcher2 = _make_dispatcher(settings, monkeypatch, record_continue=True)
        monkeypatch.setattr(source_intake_module, "session_scope", scope)
        dispatcher2.recover()
        _flush(dispatcher2)
    finally:
        pass

    assert first == 1
    total = len(dispatcher._test_continue_calls) + len(dispatcher2._test_continue_calls)
    assert total == 1
    with scope() as session:
        jobs = list(session.scalars(select(SourceIntakeJobModel).where(
            SourceIntakeJobModel.run_id == created.run_id,
        ).order_by(SourceIntakeJobModel.attempt)))
        assert len(jobs) == 2
        assert jobs[0].status == "failed"
        assert jobs[0].last_error_code == "G03_APPROVAL_REQUIRED"
        assert jobs[1].attempt == 2
        queued_events = list(session.scalars(select(WorkflowEventModel).where(
            WorkflowEventModel.run_id == created.run_id,
            WorkflowEventModel.event_type == WorkflowEventType.SOURCE_INTAKE_QUEUED.value,
        )))
        assert len(queued_events) == 1


def test_recover_self_heal_preserves_failed_predecessor_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The immutable failed predecessor must remain; only one re-arm successor is added."""
    service, scope, settings = _service(tmp_path)
    created = service.create(_request("startup-history"))
    _seed_stranded(scope, created.run_id, job_id="intake-startup-history",
                   thread_id=created.graph_thread_id)

    dispatcher = _make_dispatcher(settings, monkeypatch, record_continue=True)
    monkeypatch.setattr(source_intake_module, "session_scope", scope)
    try:
        dispatcher.recover()
    finally:
        _flush(dispatcher)

    with scope() as session:
        predecessor = session.get(SourceIntakeJobModel, "intake-startup-history")
        assert predecessor is not None
        assert predecessor.status == "failed"
        assert predecessor.last_error_code == "G03_APPROVAL_REQUIRED"
        assert predecessor.finished_at is not None
        successors = list(session.scalars(select(SourceIntakeJobModel).where(
            SourceIntakeJobModel.run_id == created.run_id,
            SourceIntakeJobModel.attempt > predecessor.attempt,
        )))
        assert len(successors) == 1


def test_recover_self_heal_does_not_touch_waiting_g03_with_approval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A waiting_g03 run with approved G03 present alongside a stranded run must remain dormant on startup."""
    service, scope, settings = _service(tmp_path)
    stranded = service.create(_request("startup-coexist-stranded"))
    _seed_stranded(scope, stranded.run_id, job_id="intake-coexist-stranded",
                   thread_id=stranded.graph_thread_id)
    dormant = service.create(_request("startup-coexist-dormant"))
    _set_run_status(scope, dormant.run_id, RunStatus.SOURCE_VALIDATED.value, state_version=60)
    _seed_job(scope, dormant.run_id, job_id="intake-coexist-dormant", status="waiting_g03",
              thread_id=dormant.graph_thread_id, state_version=60)
    _seed_g03_approval(scope, dormant.run_id, state_version=60)
    _seed_g03_approved_event(scope, dormant.run_id)

    dispatcher = _make_dispatcher(settings, monkeypatch, record_continue=True)
    monkeypatch.setattr(source_intake_module, "session_scope", scope)
    try:
        count = dispatcher.recover()
    finally:
        _flush(dispatcher)

    assert count == 1
    assert all(c[1] == stranded.run_id for c in dispatcher._test_continue_calls)
    with scope() as session:
        dormant_job = session.get(SourceIntakeJobModel, "intake-coexist-dormant")
        assert dormant_job is not None and dormant_job.status == "waiting_g03"
        run = session.get(MigrationRunModel, dormant.run_id)
        assert run.status == RunStatus.SOURCE_VALIDATED.value


def test_recover_concurrent_self_heal_at_most_one_successor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Two concurrent resume_after_g03 attempts on the same stranded run commit at most one successor.

    The WorkflowEvent unique constraint on (run_id, idempotency_key) makes the
    duplicate audit-event insert roll back one transaction, which also rolls
    back its sibling rearm job row in the same session.
    """
    engine = create_engine(f"sqlite:///{tmp_path / 'post-g03-concurrent.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def cscope():
        with sessions() as session:
            yield session
            session.commit()

    now = datetime.now(UTC)
    snapshot = PreflightSnapshot(
        preflight_id="preflight-c", gate_id="G01", gate_version="g01-v1", state_version=1,
        status="passed", created_at=now, expires_at=now + timedelta(minutes=5),
        input_checksum="sha256:input", artifact_set_checksum="sha256:artifacts",
        target_angular_family="21.x", migration_mode="strict-functional-parity",
        source_path="C:/source", target_parent_path=str(tmp_path / "migration-results-c"),
        generated_output_name="customer-portal-angular-21",
        resolved_output_root=str(tmp_path / "migration-results-c" / "customer-portal-angular-21"),
        target_output_path=str(tmp_path / "migration-results-c" / "customer-portal-angular-21"),
    )
    with cscope() as session:
        session.add(PreflightModel(
            id="preflight-c", idempotency_key="pf-c", actor="reviewer",
            gate_id="G01", gate_version="g01-v1", state_version=1, status="passed",
            input_checksum="sha256:input", artifact_set_checksum="sha256:artifacts",
            expires_at=snapshot.expires_at, binding={"path_validation_id": "path-c"},
            snapshot=snapshot.model_copy(update={"target_reservation_id": "reservation-c"}).model_dump(mode="json"),
            created_at=now,
        ))
        session.add(PathValidationModel(
            id="path-c", idempotency_key="path-c", actor="operator", status="passed",
            source_fingerprint="sha256:source", checksum="sha256:pathc",
            snapshot={"validation_id": "path-c", "captured_at": now.isoformat(), "policy_version": "path-v1",
                      "status": "passed", "source_path": "C:/source",
                      "target_parent_path": str(tmp_path / "migration-results-c"),
                      "generated_output_name": "customer-portal-angular-21",
                      "resolved_output_root": str(tmp_path / "migration-results-c" / "customer-portal-angular-21"),
                      "target_output_path": str(tmp_path / "migration-results-c" / "customer-portal-angular-21"),
                      "reservation_id": "reservation-c",
                      "reservation_expires_at": (now + timedelta(minutes=15)).isoformat(),
                      "source_fingerprint": "sha256:source", "rules": [], "blockers": [], "warnings": [],
                      "target_reservation_eligible": True, "checksum": "sha256:pathc"},
            created_at=now,
        ))
        session.add(TargetReservationModel(
            id="reservation-c", validation_id="path-c",
            target_path=str(tmp_path / "migration-results-c" / "customer-portal-angular-21"),
            status="reserved", expires_at=now + timedelta(minutes=15), created_at=now,
        ))
        session.add(ApprovalGateModel(
            id="gate-c", preflight_id="preflight-c", gate_id="G01", gate_version="g01-v1",
            status="approved", state_version=2, input_checksum="sha256:input",
            artifact_set_checksum="sha256:artifacts", expires_at=snapshot.expires_at,
            created_at=now,
        ))
    settings = Settings(
        _env_file=None,
        artifact_root=tmp_path / "artifacts-c",
        workspace_root=tmp_path / "workspaces-c",
        snapshot_root=tmp_path / "snapshots-c",
        delivery_root=tmp_path / "delivery-c",
        sandbox_root=tmp_path / "sandboxes-c",
    )
    service = MigrationRunService(settings, session_scope_factory=cscope, now_provider=lambda: now)
    created = service.create(_request("concurrent-create-c", preflight_id="preflight-c"))
    _set_run_status(cscope, created.run_id, RunStatus.BASELINE_QUALIFIED.value, state_version=98)
    _seed_job(cscope, created.run_id, job_id="intake-concurrent", status="failed",
              thread_id=created.graph_thread_id, attempt=1,
              error_code="G03_APPROVAL_REQUIRED",
              error_message="Approved G03 is required before discovery.",
              state_version=52)
    _seed_g03_approval(cscope, created.run_id, state_version=98)

    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def _run_concurrent(dispatcher):
        monkeypatch.setattr(source_intake_module, "session_scope", cscope)
        barrier.wait()
        try:
            dispatcher.resume_after_g03(created.run_id)
        except Exception as exc:  # noqa: BLE001 - one racer is expected to lose the idempotency race
            errors.append(exc)
        finally:
            _flush(dispatcher)

    d1 = _make_dispatcher(settings, monkeypatch, record_continue=True)
    d2 = _make_dispatcher(settings, monkeypatch, record_continue=True)
    t1 = threading.Thread(target=_run_concurrent, args=(d1,))
    t2 = threading.Thread(target=_run_concurrent, args=(d2,))
    t1.start(); t2.start()
    t1.join(); t2.join()

    total = len(d1._test_continue_calls) + len(d2._test_continue_calls)
    with cscope() as session:
        successors = list(session.scalars(select(SourceIntakeJobModel).where(
            SourceIntakeJobModel.run_id == created.run_id,
            SourceIntakeJobModel.attempt > 1,
        )))
    assert len(successors) <= 1
    assert total <= 1
