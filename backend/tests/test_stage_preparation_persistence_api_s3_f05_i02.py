"""Focused AMFA-171 characterisation and regression coverage."""

from app.api.authentication import required_authenticated_actor
from app.api.routes.stages import get_stage_service, router
from app.repositories import stage_workspace_models
from app.services.stage_preparation_service import StageApplicationError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pathlib import Path
import runpy
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.repositories.models.base import Base
from app.repositories.models.workflow import MigrationStageModel, WorkflowEventModel
from app.repositories.models.workflow import ArtifactMetadataModel, MigrationRunModel
from app.repositories.planning_models import StageExecutionPlanModel
from app.repositories.stage_workspace_models import (
    G07ApprovalModel,
    G07DecisionHistoryModel,
    StageWorkspaceModel,
)
from app.domain.stage_workspace import G07Decision
from app.artifact_store import LocalFilesystemArtifactStore
from app.services.stage_preparation_service import StagePreparationApplicationService


@pytest.fixture
def slice_a_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'slice-a.db'}")
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def slice_a_db(slice_a_engine):
    connection = slice_a_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


def _client(service):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_stage_service] = lambda: service
    return TestClient(app)


class _StageService:
    def __init__(self, *, foreign=False):
        self.foreign = foreign
        self.actor = None

    def prepare_stage(self, run_id, request):
        if self.foreign:
            raise StageApplicationError("RUN_NOT_AUTHORIZED", "foreign run", status_code=403)
        self.actor = request.actor
        return {"run_id": run_id, "stage_id": "stage-1", "stage_key": request.stage_key, "status": "WAITING_APPROVAL", "state_version": 1, "event_sequence": 1}

    def get_g07(self, run_id, stage_id, actor):
        if self.foreign:
            raise StageApplicationError("RUN_NOT_AUTHORIZED", "foreign run", status_code=403)
        self.actor = actor
        return {"run_id": run_id, "stage_id": stage_id, "gate_id": "G07", "gate_version": "g07-v1", "status": "pending", "package": {}, "state_version": 1, "event_sequence": 1}


def test_unauthenticated_actor_is_rejected():
    """AMFA-171: a missing server identity cannot become a local actor."""
    try:
        required_authenticated_actor(None)
    except Exception as error:
        assert getattr(error, "status_code", None) == 401
    else:
        raise AssertionError("missing authentication was accepted")


def test_canonical_stage_prepare_route_is_exposed():
    """AMFA-171: preparation is addressed by its stage identifier in the route."""
    paths = {route.path for route in router.routes}
    assert "/runs/{run_id}/stages/{stage_id}/prepare" in paths


def test_append_only_g07_decision_history_has_a_durable_model():
    """AMFA-171: decisions must survive mutable G07 gate-projection updates."""
    assert hasattr(stage_workspace_models, "G07DecisionHistoryModel")


def test_prepare_http_requires_identity_and_uses_server_actor():
    service = _StageService()
    client = _client(service)
    payload = {"expected_state_version": 1, "idempotency_key": "k", "actor": "spoofed", "stage_key": "stage-1", "source_version_family": "angular_18", "target_version_family": "angular_19", "plan_version": "v1"}
    assert client.post("/api/v1/runs/run-1/stages/prepare", json=payload).status_code == 401
    response = client.post("/api/v1/runs/run-1/stages/prepare", json=payload, headers={"x-authenticated-actor": "owner"})
    assert response.status_code == 200
    assert service.actor == "owner"


def test_g07_read_http_is_protected_and_maps_foreign_run_to_403():
    client = _client(_StageService(foreign=True))
    assert client.get("/api/v1/runs/run-1/approvals/G07?stage_id=stage-1").status_code == 401
    response = client.get("/api/v1/runs/run-1/approvals/G07?stage_id=stage-1", headers={"x-authenticated-actor": "foreign"})
    assert response.status_code == 403


def _setup_g07_decision(slice_a_db, tmp_path):
    helpers = runpy.run_path(str(Path(__file__).with_name("test_stage_workspace.py")))
    base = helpers["TestStagePreparationDecideG07"]()
    now = helpers["datetime"].now(helpers["UTC"])
    service, stage_id = base._setup_for_g07(slice_a_db, now, tmp_path)
    request = base._make_simple_req(
        gate_id="G07", expected_state_version=5, idempotency_key="slice-a-decision",
        stage_id=stage_id, decision=G07Decision.APPROVED, comment="approved",
    )
    return base, now, service, stage_id, request


def _decision_events(session):
    return session.query(WorkflowEventModel).filter_by(
        run_id="run-001", event_type="G07_APPROVED",
    ).all()


def _history_snapshot(history):
    return {
        column.name: deepcopy(getattr(history, column.name))
        for column in G07DecisionHistoryModel.__table__.columns
    }


def _setup_completed_stage_workflow(session, tmp_path, *, run_id="run-001"):
    helpers = runpy.run_path(str(Path(__file__).with_name("test_stage_workspace.py")))
    base = helpers["TestStagePreparationDecideG07"]()
    now = helpers["datetime"].now(helpers["UTC"])
    run = base._create_run(session, run_id=run_id)
    run.run_root = str(Path(run.source_path).parent)
    service = StagePreparationApplicationService(
        session_scope_factory=lambda: session, now_provider=lambda: now,
    )
    service._authoritative_snapshot_fingerprint = lambda snapshot: "sha256:src-fp"
    prepare_request = base._make_prepare_req(idempotency_key=f"{run_id}-prepare")
    prepared = service.prepare_stage(run_id, prepare_request)
    decision_request = base._make_simple_req(
        gate_id="G07", expected_state_version=prepared.state_version,
        idempotency_key=f"{run_id}-decision", stage_id=prepared.stage_id,
        decision=G07Decision.APPROVED, comment="approved",
    )
    decision = service.decide_g07(run_id, prepared.stage_id, decision_request)
    sandbox_request = base._make_simple_req(
        expected_state_version=decision.state_version,
        idempotency_key=f"{run_id}-sandbox", actor="operator",
    )
    sandbox = service.create_sandbox(run_id, prepared.stage_id, sandbox_request)
    return service, prepared, decision_request, sandbox_request, decision, sandbox


def _relevant_stage_events(session, run_id, correlation):
    return [
        event for event in session.query(WorkflowEventModel).filter_by(run_id=run_id).all()
        if event.stage_id == correlation or event.payload.get("stage_id") == correlation
    ]


def test_g07_first_decision_appends_one_immutable_history_record(slice_a_db, tmp_path):
    _, _, service, stage_id, request = _setup_g07_decision(slice_a_db, tmp_path)
    first = service.decide_g07("run-001", stage_id, request)
    history = slice_a_db.query(G07DecisionHistoryModel).one()

    assert slice_a_db.query(G07DecisionHistoryModel).count() == 1
    assert first.decision_id == history.id
    assert history.actor == request.actor
    assert history.decision == request.decision.value
    assert history.comment == request.comment
    assert history.gate_version == "g07-v1"
    assert history.idempotency_key == request.idempotency_key
    assert history.request_checksum == service._checksum({
        "run_id": "run-001", "stage_id": stage_id, "actor": request.actor,
        "decision": request.decision.value, "comment": request.comment,
        "package_checksum": history.payload_checksum,
    })
    assert len(_decision_events(slice_a_db)) == 1


def test_g07_identical_replay_reuses_immutable_decision(slice_a_db, tmp_path):
    _, now, service, stage_id, request = _setup_g07_decision(slice_a_db, tmp_path)
    first = service.decide_g07("run-001", stage_id, request)
    history = slice_a_db.query(G07DecisionHistoryModel).one()
    original = (history.id, history.request_checksum, history.decision, history.comment, history.created_at)

    replay = StagePreparationApplicationService(
        session_scope_factory=lambda: slice_a_db, now_provider=lambda: now,
    ).decide_g07("run-001", stage_id, request)

    persisted = slice_a_db.query(G07DecisionHistoryModel).one()
    assert replay.idempotent_replay is True
    assert first.decision_id == replay.decision_id == persisted.id
    assert slice_a_db.query(G07DecisionHistoryModel).count() == 1
    assert (persisted.id, persisted.request_checksum, persisted.decision, persisted.comment, persisted.created_at) == original
    assert len(_decision_events(slice_a_db)) == 1


def test_g07_identical_replay_after_restart_uses_immutable_history(slice_a_engine, tmp_path):
    helpers = runpy.run_path(str(Path(__file__).with_name("test_stage_workspace.py")))
    base = helpers["TestStagePreparationDecideG07"]()
    now = helpers["datetime"].now(helpers["UTC"])
    first_session = Session(slice_a_engine)

    @contextmanager
    def durable_scope():
        scoped_session = Session(slice_a_engine, expire_on_commit=False)
        try:
            yield scoped_session
            scoped_session.commit()
        except Exception:
            scoped_session.rollback()
            raise
        finally:
            scoped_session.close()

    try:
        base._create_run(first_session)
        first_session.commit()
        first_service = StagePreparationApplicationService(
            session_scope_factory=durable_scope, now_provider=lambda: now,
        )
        preparation = first_service.prepare_stage(
            "run-001", base._make_prepare_req(idempotency_key="restart-g07-setup"),
        )
        stage_id = preparation.stage_id
        request = base._make_simple_req(
            gate_id="G07", expected_state_version=preparation.state_version,
            idempotency_key="restart-g07-decision", stage_id=stage_id,
            decision=G07Decision.APPROVED, comment="approved",
        )
        first = first_service.decide_g07("run-001", stage_id, request)
        with Session(slice_a_engine) as reader:
            history = reader.query(G07DecisionHistoryModel).one()
            before = _history_snapshot(history)
            assert reader.query(G07DecisionHistoryModel).count() == 1
            assert len(_decision_events(reader)) == 1
    finally:
        first_session.close()

    second_session = Session(slice_a_engine)
    try:
        restarted_service = StagePreparationApplicationService(
            session_scope_factory=durable_scope, now_provider=lambda: now,
        )
        replay = restarted_service.decide_g07("run-001", stage_id, request)
        persisted = second_session.query(G07DecisionHistoryModel).one()

        assert restarted_service is not first_service
        assert replay.idempotent_replay is True
        assert replay.decision_id == first.decision_id == persisted.id
        assert second_session.query(G07DecisionHistoryModel).count() == 1
        assert _history_snapshot(persisted) == before
        assert len(_decision_events(second_session)) == 1
    finally:
        second_session.close()


def test_g07_same_idempotency_key_changed_payload_conflicts(slice_a_db, tmp_path):
    base, _, service, stage_id, request = _setup_g07_decision(slice_a_db, tmp_path)
    first = service.decide_g07("run-001", stage_id, request)
    history = slice_a_db.query(G07DecisionHistoryModel).one()
    original = (history.id, history.request_checksum, history.decision, history.comment, history.created_at)
    changed = base._make_simple_req(
        gate_id="G07", expected_state_version=5, idempotency_key=request.idempotency_key,
        stage_id=stage_id, decision=G07Decision.APPROVED, comment="changed",
    )

    with pytest.raises(StageApplicationError, match="IDEMPOTENCY_PAYLOAD_MISMATCH") as error:
        service.decide_g07("run-001", stage_id, changed)

    assert error.value.status_code == 409
    assert slice_a_db.query(G07DecisionHistoryModel).count() == 1
    persisted = slice_a_db.query(G07DecisionHistoryModel).one()
    assert first.decision_id == persisted.id
    assert (persisted.id, persisted.request_checksum, persisted.decision, persisted.comment, persisted.created_at) == original
    assert len(_decision_events(slice_a_db)) == 1


def test_g07_history_remains_immutable_after_gate_becomes_stale(slice_a_db, tmp_path):
    _, _, service, stage_id, request = _setup_g07_decision(slice_a_db, tmp_path)
    service.decide_g07("run-001", stage_id, request)
    history = slice_a_db.query(G07DecisionHistoryModel).one()
    before = _history_snapshot(history)

    stage_plan = slice_a_db.get(StageExecutionPlanModel, "stage-plan-170")
    stage_plan.stage_plan["execution_profile_id"] = "drifted-profile"
    slice_a_db.flush()

    with pytest.raises(StageApplicationError, match="G07_STALE") as error:
        service.decide_g07("run-001", stage_id, request)

    gate = service.get_g07("run-001", stage_id)
    persisted = slice_a_db.query(G07DecisionHistoryModel).one()
    assert error.value.status_code == 409
    assert gate.status == "stale"
    assert gate.stale_reason == "G07_BINDINGS_CHANGED"
    assert slice_a_db.query(G07DecisionHistoryModel).count() == 1
    assert _history_snapshot(persisted) == before
    assert len(_decision_events(slice_a_db)) == 1


def test_old_approved_decision_cannot_authorize_changed_bindings(slice_a_db, tmp_path):
    _, _, service, stage_id, request = _setup_g07_decision(slice_a_db, tmp_path)
    approved = service.decide_g07("run-001", stage_id, request)
    history = slice_a_db.query(G07DecisionHistoryModel).one()
    before = _history_snapshot(history)

    stage_plan = slice_a_db.get(StageExecutionPlanModel, "stage-plan-170")
    stage_plan.stage_plan["execution_profile_id"] = "drifted-profile"
    slice_a_db.flush()
    sandbox_request = type("Req", (), {
        "expected_state_version": approved.state_version,
        "idempotency_key": "changed-bindings-sandbox", "actor": request.actor,
    })()

    with pytest.raises(StageApplicationError, match="G07_STALE") as error:
        service.create_sandbox("run-001", stage_id, sandbox_request)

    persisted = slice_a_db.query(G07DecisionHistoryModel).one()
    assert error.value.status_code == 409
    assert slice_a_db.query(StageWorkspaceModel).filter_by(stage_id=stage_id).count() == 0
    assert slice_a_db.query(WorkflowEventModel).filter_by(
        run_id="run-001", event_type="STAGE_SANDBOX_READY",
    ).count() == 0
    assert slice_a_db.query(G07DecisionHistoryModel).count() == 1
    assert _history_snapshot(persisted) == before
    assert len(_decision_events(slice_a_db)) == 1


def test_stage_gate_decision_workspace_and_events_share_correlation(slice_a_db, tmp_path):
    _, prepared, _, _, _, _ = _setup_completed_stage_workflow(slice_a_db, tmp_path)
    correlation = prepared.stage_id
    stage = slice_a_db.get(MigrationStageModel, correlation)
    gate = slice_a_db.query(G07ApprovalModel).filter_by(stage_id=correlation).one()
    history = slice_a_db.query(G07DecisionHistoryModel).filter_by(stage_id=correlation).one()
    workspace = slice_a_db.query(StageWorkspaceModel).filter_by(stage_id=correlation).one()
    events = _relevant_stage_events(slice_a_db, "run-001", correlation)

    assert stage.id == correlation
    assert gate.stage_id == correlation
    assert history.stage_id == history.correlation_id == correlation
    assert workspace.stage_id == correlation
    assert {event.event_type for event in events} >= {
        "STAGE_CREATED", "G07_CREATED", "G07_APPROVED", "STAGE_SANDBOX_READY",
    }
    assert all(event.stage_id == correlation or event.payload.get("stage_id") == correlation for event in events)


def test_identical_replays_preserve_one_correlation_chain(slice_a_db, tmp_path):
    helpers = runpy.run_path(str(Path(__file__).with_name("test_stage_workspace.py")))
    base = helpers["TestStagePreparationDecideG07"]()
    now = helpers["datetime"].now(helpers["UTC"])
    run = base._create_run(slice_a_db)
    run.run_root = str(Path(run.source_path).parent)
    service = StagePreparationApplicationService(session_scope_factory=lambda: slice_a_db, now_provider=lambda: now)
    service._authoritative_snapshot_fingerprint = lambda snapshot: "sha256:src-fp"
    prepare_request = base._make_prepare_req(idempotency_key="run-001-prepare")
    prepared = service.prepare_stage("run-001", prepare_request)
    decision_request = base._make_simple_req(
        gate_id="G07", expected_state_version=prepared.state_version,
        idempotency_key="run-001-decision", stage_id=prepared.stage_id,
        decision=G07Decision.APPROVED, comment="approved",
    )
    decision = service.decide_g07("run-001", prepared.stage_id, decision_request)
    correlation = prepared.stage_id
    prepare_replay = service.prepare_stage("run-001", prepare_request)
    decision_replay = service.decide_g07("run-001", correlation, decision_request)
    sandbox_request = base._make_simple_req(
        expected_state_version=decision.state_version, idempotency_key="run-001-sandbox", actor="operator",
    )
    service.create_sandbox("run-001", correlation, sandbox_request)
    sandbox_replay = service.create_sandbox("run-001", correlation, sandbox_request)

    assert prepare_replay.idempotent_replay is True
    assert decision_replay.idempotent_replay is True
    assert sandbox_replay.idempotent_replay is True
    assert prepare_replay.stage_id == correlation
    assert slice_a_db.query(MigrationStageModel).filter_by(run_id="run-001").count() == 1
    assert slice_a_db.query(G07ApprovalModel).filter_by(stage_id=correlation).count() == 1
    assert slice_a_db.query(G07DecisionHistoryModel).filter_by(stage_id=correlation).count() == 1
    assert slice_a_db.query(StageWorkspaceModel).filter_by(stage_id=correlation).count() == 1
    events = _relevant_stage_events(slice_a_db, "run-001", correlation)
    for event_type in ("STAGE_CREATED", "G07_CREATED", "G07_APPROVED", "STAGE_SANDBOX_READY"):
        assert sum(event.event_type == event_type for event in events) == 1


def test_correlation_chain_survives_session_and_service_restart(slice_a_engine, tmp_path):
    @contextmanager
    def durable_scope():
        scoped_session = Session(slice_a_engine, expire_on_commit=False)
        try:
            yield scoped_session
            scoped_session.commit()
        except Exception:
            scoped_session.rollback()
            raise
        finally:
            scoped_session.close()

    first_session = Session(slice_a_engine)
    try:
        helpers = runpy.run_path(str(Path(__file__).with_name("test_stage_workspace.py")))
        base = helpers["TestStagePreparationDecideG07"]()
        now = helpers["datetime"].now(helpers["UTC"])
        run = base._create_run(first_session)
        run.run_root = str(Path(run.source_path).parent)
        first_session.commit()
        first_service = StagePreparationApplicationService(session_scope_factory=durable_scope, now_provider=lambda: now)
        first_service._authoritative_snapshot_fingerprint = lambda snapshot: "sha256:src-fp"
        prepared = first_service.prepare_stage("run-001", base._make_prepare_req(idempotency_key="restart-chain-prepare"))
        decision_request = base._make_simple_req(
            gate_id="G07", expected_state_version=prepared.state_version,
            idempotency_key="restart-chain-decision", stage_id=prepared.stage_id,
            decision=G07Decision.APPROVED, comment="approved",
        )
        decision = first_service.decide_g07("run-001", prepared.stage_id, decision_request)
        first_service.create_sandbox("run-001", prepared.stage_id, base._make_simple_req(
            expected_state_version=decision.state_version, idempotency_key="restart-chain-sandbox", actor="operator",
        ))
        correlation = prepared.stage_id
    finally:
        first_session.close()

    second_session = Session(slice_a_engine)
    try:
        restarted_service = StagePreparationApplicationService(session_scope_factory=durable_scope, now_provider=lambda: now)
        gate = restarted_service.get_g07("run-001", correlation)
        history = second_session.query(G07DecisionHistoryModel).filter_by(stage_id=correlation).one()
        workspace = second_session.query(StageWorkspaceModel).filter_by(stage_id=correlation).one()
        events = _relevant_stage_events(second_session, "run-001", correlation)

        assert restarted_service is not first_service
        assert second_session.get(MigrationStageModel, correlation).id == correlation
        assert gate.stage_id == history.stage_id == history.correlation_id == workspace.stage_id == correlation
        assert {event.event_type for event in events} >= {"G07_CREATED", "G07_APPROVED", "STAGE_SANDBOX_READY"}
    finally:
        second_session.close()


def test_distinct_stage_workflows_do_not_share_correlation(slice_a_db, tmp_path):
    _, first, _, _, _, _ = _setup_completed_stage_workflow(slice_a_db, tmp_path, run_id="run-001")
    second_engine = create_engine(f"sqlite:///{tmp_path / 'second-stage-workflow.db'}")
    Base.metadata.create_all(second_engine)
    second_connection = second_engine.connect()
    second_transaction = second_connection.begin()
    second_session = Session(bind=second_connection)
    try:
        _, second, _, _, _, _ = _setup_completed_stage_workflow(second_session, tmp_path, run_id="run-002")
        second_history = second_session.query(G07DecisionHistoryModel).filter_by(stage_id=second.stage_id).one()
    finally:
        second_session.close()
        if second_transaction.is_active:
            second_transaction.rollback()
        second_connection.close()
        second_engine.dispose()

    assert first.stage_id != second.stage_id
    assert slice_a_db.query(G07DecisionHistoryModel).filter_by(stage_id=first.stage_id).one().correlation_id == first.stage_id
    assert second_history.correlation_id == second.stage_id


def _sandbox_evidence(session, stage_id):
    workspace = session.query(StageWorkspaceModel).filter_by(stage_id=stage_id).one()
    metadata = {row.id.removeprefix("metadata-"): row for row in session.query(ArtifactMetadataModel).filter_by(stage_id=stage_id)}
    return workspace, metadata[workspace.copy_report_artifact_id], metadata[workspace.verification_artifact_id]


def _read_evidence(run, metadata):
    store = LocalFilesystemArtifactStore(Path(run.artifact_root), fixed_run_root=Path(run.artifact_root))
    stored = store.read_artifact_by_id(metadata.id.removeprefix("metadata-"))
    assert stored.ref.checksum == metadata.checksum == f"sha256:{hashlib.sha256(stored.content.encode()).hexdigest()}"
    return stored, json.loads(stored.content)


def test_sandbox_creation_persists_immutable_copy_report(slice_a_db, tmp_path):
    _, prepared, _, _, _, _ = _setup_completed_stage_workflow(slice_a_db, tmp_path)
    workspace, copy_metadata, _ = _sandbox_evidence(slice_a_db, prepared.stage_id)
    _, payload = _read_evidence(slice_a_db.get(MigrationRunModel, "run-001"), copy_metadata)
    assert copy_metadata.relative_path.endswith("sandbox_copy_report.json")
    assert (payload["workspace_id"], payload["correlation_id"]) == (workspace.id, prepared.stage_id)
    assert (payload["file_count"], payload["total_size_bytes"]) == (workspace.file_count, workspace.total_size_bytes)


def test_sandbox_creation_persists_immutable_verification_evidence(slice_a_db, tmp_path):
    _, prepared, _, _, _, _ = _setup_completed_stage_workflow(slice_a_db, tmp_path)
    workspace, copy_metadata, verification_metadata = _sandbox_evidence(slice_a_db, prepared.stage_id)
    _, payload = _read_evidence(slice_a_db.get(MigrationRunModel, "run-001"), verification_metadata)
    assert payload["correlation_id"] == prepared.stage_id
    assert (payload["source_fingerprint"], payload["sandbox_fingerprint"]) == (workspace.source_fingerprint, workspace.workspace_fingerprint)
    assert (payload["file_count"], payload["total_size_bytes"]) == (workspace.file_count, workspace.total_size_bytes)
    assert (payload["copy_report_artifact_id"], payload["copy_report_checksum"]) == (copy_metadata.id.removeprefix("metadata-"), copy_metadata.checksum)


def test_sandbox_replay_reuses_copy_and_verification_artifacts(slice_a_db, tmp_path):
    service, prepared, _, sandbox_request, _, _ = _setup_completed_stage_workflow(slice_a_db, tmp_path)
    workspace, copy_metadata, verification_metadata = _sandbox_evidence(slice_a_db, prepared.stage_id)
    replay = service.create_sandbox("run-001", prepared.stage_id, sandbox_request)
    replay_workspace, replay_copy, replay_verification = _sandbox_evidence(slice_a_db, prepared.stage_id)
    assert replay.idempotent_replay is True
    assert replay_workspace.id == workspace.id
    assert (replay_copy.id, replay_copy.checksum, replay_verification.id, replay_verification.checksum) == (copy_metadata.id, copy_metadata.checksum, verification_metadata.id, verification_metadata.checksum)
    assert slice_a_db.query(ArtifactMetadataModel).filter_by(stage_id=prepared.stage_id).count() == 3
    assert slice_a_db.query(WorkflowEventModel).filter_by(run_id="run-001", stage_id=prepared.stage_id, event_type="STAGE_SANDBOX_READY").count() == 1


def test_sandbox_evidence_survives_session_and_service_restart(slice_a_engine, tmp_path):
    @contextmanager
    def durable_scope():
        scoped = Session(slice_a_engine, expire_on_commit=False)
        try:
            yield scoped
            scoped.commit()
        except Exception:
            scoped.rollback()
            raise
        finally:
            scoped.close()

    helpers = runpy.run_path(str(Path(__file__).with_name("test_stage_workspace.py")))
    base, now = helpers["TestStagePreparationDecideG07"](), helpers["datetime"].now(helpers["UTC"])
    first_session = Session(slice_a_engine)
    try:
        run = base._create_run(first_session)
        run.run_root = str(Path(run.source_path).parent)
        first_session.commit()
        first_service = StagePreparationApplicationService(session_scope_factory=durable_scope, now_provider=lambda: now)
        first_service._authoritative_snapshot_fingerprint = lambda snapshot: "sha256:src-fp"
        prepared = first_service.prepare_stage("run-001", base._make_prepare_req(idempotency_key="restart-evidence-prepare"))
        approved = first_service.decide_g07("run-001", prepared.stage_id, base._make_simple_req(gate_id="G07", expected_state_version=prepared.state_version, idempotency_key="restart-evidence-decision", stage_id=prepared.stage_id, decision=G07Decision.APPROVED, comment="approved"))
        first_service.create_sandbox("run-001", prepared.stage_id, base._make_simple_req(expected_state_version=approved.state_version, idempotency_key="restart-evidence-sandbox", actor="operator"))
        stage_id = prepared.stage_id
    finally:
        first_session.close()

    second_session = Session(slice_a_engine)
    try:
        run = second_session.get(MigrationRunModel, "run-001")
        workspace, copy_metadata, verification_metadata = _sandbox_evidence(second_session, stage_id)
        _, copy_payload = _read_evidence(run, copy_metadata)
        _, verification_payload = _read_evidence(run, verification_metadata)
        restarted_service = StagePreparationApplicationService(session_scope_factory=durable_scope, now_provider=lambda: now)
        assert restarted_service.get_g07("run-001", stage_id).stage_id == stage_id
        assert workspace.stage_id == copy_payload["correlation_id"] == verification_payload["correlation_id"] == stage_id
    finally:
        second_session.close()


@pytest.mark.parametrize("which", ["copy", "verification"])
def test_tampered_sandbox_evidence_artifact_is_rejected(slice_a_db, tmp_path, which):
    service, prepared, _, sandbox_request, _, _ = _setup_completed_stage_workflow(slice_a_db, tmp_path)
    _, copy_metadata, verification_metadata = _sandbox_evidence(slice_a_db, prepared.stage_id)
    metadata = copy_metadata if which == "copy" else verification_metadata
    run = slice_a_db.get(MigrationRunModel, "run-001")
    Path(run.artifact_root, metadata.relative_path).write_text('{"tampered":true}', encoding="utf-8")
    with pytest.raises(StageApplicationError, match="ARTIFACT_TAMPERED"):
        service.create_sandbox("run-001", prepared.stage_id, sandbox_request)
    assert slice_a_db.query(WorkflowEventModel).filter_by(run_id="run-001", stage_id=prepared.stage_id, event_type="STAGE_SANDBOX_READY").count() == 1


def test_required_sandbox_evidence_failure_prevents_ready_success(slice_a_db, tmp_path, monkeypatch):
    helpers = runpy.run_path(str(Path(__file__).with_name("test_stage_workspace.py")))
    base, now = helpers["TestStagePreparationDecideG07"](), helpers["datetime"].now(helpers["UTC"])
    run = base._create_run(slice_a_db)
    run.run_root = str(Path(run.source_path).parent)
    service = StagePreparationApplicationService(session_scope_factory=lambda: slice_a_db, now_provider=lambda: now)
    service._authoritative_snapshot_fingerprint = lambda snapshot: "sha256:src-fp"
    prepared = service.prepare_stage("run-001", base._make_prepare_req(idempotency_key="evidence-failure-prepare"))
    approved = service.decide_g07("run-001", prepared.stage_id, base._make_simple_req(gate_id="G07", expected_state_version=prepared.state_version, idempotency_key="evidence-failure-decision", stage_id=prepared.stage_id, decision=G07Decision.APPROVED, comment="approved"))
    monkeypatch.setattr(service, "_persist_sandbox_evidence", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("evidence failure")))
    with pytest.raises(StageApplicationError, match="SANDBOX_COPY_FAILED"):
        service.create_sandbox("run-001", prepared.stage_id, base._make_simple_req(expected_state_version=approved.state_version, idempotency_key="evidence-failure-sandbox", actor="operator"))
    assert slice_a_db.query(StageWorkspaceModel).filter_by(stage_id=prepared.stage_id).one().copy_status == "failed"
    assert slice_a_db.query(WorkflowEventModel).filter_by(run_id="run-001", stage_id=prepared.stage_id, event_type="STAGE_SANDBOX_READY").count() == 0


def test_interrupted_copy_reconstruction_persists_recovery_evidence(slice_a_db, tmp_path):
    service, prepared, _, sandbox_request, _, _ = _setup_completed_stage_workflow(slice_a_db, tmp_path)
    workspace, copy_metadata, verification_metadata = _sandbox_evidence(slice_a_db, prepared.stage_id)
    for metadata in (copy_metadata, verification_metadata):
        slice_a_db.delete(metadata)
    for event in slice_a_db.query(WorkflowEventModel).filter_by(run_id="run-001", stage_id=prepared.stage_id, event_type="STAGE_SANDBOX_READY"):
        slice_a_db.delete(event)
    workspace.copy_status = "copying"
    workspace.copy_report_artifact_id = workspace.copy_report_artifact_checksum = None
    workspace.verification_artifact_id = workspace.verification_artifact_checksum = None
    slice_a_db.flush()

    recovered = service.create_sandbox("run-001", prepared.stage_id, sandbox_request)
    restored, restored_copy, restored_verification = _sandbox_evidence(slice_a_db, prepared.stage_id)
    run = slice_a_db.get(MigrationRunModel, "run-001")
    _, copy_payload = _read_evidence(run, restored_copy)
    _, verification_payload = _read_evidence(run, restored_verification)
    replay = service.create_sandbox("run-001", prepared.stage_id, sandbox_request)

    assert recovered.status == "sandbox_ready" and replay.idempotent_replay is True
    assert restored.id == workspace.id and restored.copy_status == "verified"
    assert copy_payload["recovery"]["reconstruction_invoked"] is True
    assert verification_payload["recovery"]["detected_incomplete"] is True
    assert copy_payload["correlation_id"] == verification_payload["correlation_id"] == prepared.stage_id
    assert slice_a_db.query(StageWorkspaceModel).filter_by(stage_id=prepared.stage_id).count() == 1
    assert slice_a_db.query(WorkflowEventModel).filter_by(run_id="run-001", stage_id=prepared.stage_id, event_type="STAGE_SANDBOX_READY").count() == 1


def test_recovery_evidence_failure_prevents_ready_success(slice_a_db, tmp_path, monkeypatch):
    service, prepared, _, sandbox_request, _, _ = _setup_completed_stage_workflow(slice_a_db, tmp_path)
    workspace, copy_metadata, verification_metadata = _sandbox_evidence(slice_a_db, prepared.stage_id)
    for row in (copy_metadata, verification_metadata):
        slice_a_db.delete(row)
    for event in slice_a_db.query(WorkflowEventModel).filter_by(run_id="run-001", stage_id=prepared.stage_id, event_type="STAGE_SANDBOX_READY"):
        slice_a_db.delete(event)
    workspace.copy_status = "copying"
    workspace.copy_report_artifact_id = workspace.copy_report_artifact_checksum = None
    workspace.verification_artifact_id = workspace.verification_artifact_checksum = None
    slice_a_db.flush()
    monkeypatch.setattr(service, "_persist_sandbox_evidence", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("recovery evidence failure")))
    with pytest.raises(RuntimeError, match="recovery evidence failure"):
        service.create_sandbox("run-001", prepared.stage_id, sandbox_request)
    assert workspace.copy_status == "copying"
    assert slice_a_db.query(WorkflowEventModel).filter_by(run_id="run-001", stage_id=prepared.stage_id, event_type="STAGE_SANDBOX_READY").count() == 0


def test_stage_start_artifact_is_canonical_input_manifest_evidence(slice_a_db, tmp_path):
    _, prepared, _, _, _, _ = _setup_completed_stage_workflow(slice_a_db, tmp_path)
    run = slice_a_db.get(MigrationRunModel, "run-001")
    metadata = slice_a_db.query(ArtifactMetadataModel).filter_by(stage_id=prepared.stage_id).filter(ArtifactMetadataModel.relative_path.like("%stage_start_evidence.json")).one()
    _, payload = _read_evidence(run, metadata)
    assert payload["run_id"] == "run-001" and payload["stage_id"] == prepared.stage_id
    assert payload["input_snapshot"]["fingerprint"] == "sha256:src-fp"
    assert payload["input_file_count"] >= 1 and payload["input_total_size_bytes"] >= 0
    assert payload["migration_plan"]["checksum"] and payload["stage_plan"]["checksum"] and payload["g06"]["id"]


def test_stage_start_evidence_failure_does_not_publish_false_waiting_approval_success(slice_a_db, tmp_path, monkeypatch):
    helpers = runpy.run_path(str(Path(__file__).with_name("test_stage_workspace.py")))
    base, now = helpers["TestStagePreparationDecideG07"](), helpers["datetime"].now(helpers["UTC"])
    base._create_run(slice_a_db)
    service = StagePreparationApplicationService(session_scope_factory=lambda: slice_a_db, now_provider=lambda: now)
    monkeypatch.setattr(service, "_persist_stage_start_evidence", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("stage evidence failure")))
    with pytest.raises(RuntimeError, match="stage evidence failure"):
        service.prepare_stage("run-001", base._make_prepare_req(idempotency_key="stage-evidence-failure"))
    slice_a_db.rollback()
    assert slice_a_db.query(G07ApprovalModel).filter_by(run_id="run-001").count() == 0
    assert slice_a_db.query(WorkflowEventModel).filter_by(run_id="run-001", event_type="G07_CREATED").count() == 0


def test_existing_sandbox_contract_retrieves_authoritative_state_after_restart(slice_a_db, tmp_path):
    service, prepared, _, sandbox_request, _, _ = _setup_completed_stage_workflow(slice_a_db, tmp_path)
    replay = service.create_sandbox("run-001", prepared.stage_id, sandbox_request)
    workspace, copy_metadata, verification_metadata = _sandbox_evidence(slice_a_db, prepared.stage_id)
    assert replay.idempotent_replay is True and replay.status == "sandbox_ready"
    assert replay.verification["post_fingerprint"]["fingerprint"] == workspace.workspace_fingerprint
    assert workspace.stage_id == prepared.stage_id
    assert copy_metadata.checksum == workspace.copy_report_artifact_checksum
    assert verification_metadata.checksum == workspace.verification_artifact_checksum
