import asyncio
import json
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.baseline_parity_contracts import BaselineParityCaptureRequest
from app.api.routes import baseline_parity as baseline_parity_routes
from app.api.routes.runs import stream_run_events
from app.api.routes import runs as runs_routes
from app.main import app
from fastapi.testclient import TestClient
from app.repositories.models import ArtifactMetadataModel, Base, BaselineParityEvidenceModel, BaselineQualificationModel, BaselineValidationModel, MigrationRunModel, WorkflowEventModel
from app.services.baseline_parity_application_service import BaselineParityApplicationService

NOW = datetime(2026, 7, 16, tzinfo=UTC)


def fixture(tmp_path):
    sandbox = tmp_path / "baseline"
    source = sandbox / "src"
    source.mkdir(parents=True)
    (sandbox / "angular.json").write_text(json.dumps({"projects": {"app": {"sourceRoot": "src"}}}), encoding="utf-8")
    (source / "app.routes.ts").write_text("export const routes = [{path: 'home'}];", encoding="utf-8")
    (source / "api.service.ts").write_text("const apiUrl = 'https://api.example.test';", encoding="utf-8")
    artifact_root = tmp_path / "artifacts"
    engine = create_engine(f"sqlite:///{tmp_path / 'state.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as session:
        session.add(MigrationRunModel(id="run-1", run_root=str(tmp_path), status="CREATED", run_phase="BASELINE", phase_status="running", approval_status="approved", repair_status="not_required", state_version=1, artifact_root=str(artifact_root), workspace_aliases={"BASELINE_SANDBOX": str(sandbox)}, created_at=NOW, updated_at=NOW))
        session.add(BaselineQualificationModel(id="baseline-1", run_id="run-1", idempotency_key="baseline", actor="operator", status="qualified", snapshot_id="snapshot-1", sandbox_path=str(sandbox), input_fingerprint="sha256:input", sandbox_fingerprint="sha256:sandbox", package={}, lockfile={}, sources=[], scripts=[], registry={}, blockers=[], warnings=[], authorization_status="authorized", checksum="sha256:baseline", artifact_ids=[], state_version=1, event_sequence=1, created_at=NOW, updated_at=NOW))
        session.add(BaselineValidationModel(id="validation-1", run_id="run-1", idempotency_key="test-1", actor="operator", kind="test", status="failed", targets=[], results=[{"kind": "test", "target_id": "script:test", "status": "failed", "failed_tests": ["FAIL C:/source/app.spec.ts:42 expected 1"]}], parser_summary={}, artifact_ids=[], artifact_checksums={}, prerequisite_artifact_ids=[], baseline_checksum="sha256:baseline", state_version=1, event_sequence=1, created_at=NOW, updated_at=NOW))
        session.commit()

    @contextmanager
    def scope():
        with sessions() as session:
            yield session
            session.commit()

    return scope, sessions, engine


def test_capture_persists_checksum_bound_evidence_artifacts_and_events(tmp_path):
    scope, sessions, engine = fixture(tmp_path)
    service = BaselineParityApplicationService(scope=scope, now_provider=lambda: NOW)

    result = service.capture("run-1", BaselineParityCaptureRequest(expected_state_version=1, idempotency_key="parity-1", actor="operator"))

    assert result.status == "captured"
    assert result.failures[0]["origin"] == "pre-existing"
    assert result.routes[0]["path"] == "home"
    assert result.backend_integration["api_roots"] == ["https://api.example.test"]
    assert len(result.artifact_ids) == 5
    with sessions() as session:
        record = session.get(BaselineParityEvidenceModel, result.evidence_id)
        assert record.artifact_checksums
        assert [event.event_type for event in session.scalars(select(WorkflowEventModel).order_by(WorkflowEventModel.sequence)).all()][-3:] == ["BASELINE_FAILURES_FINGERPRINTED", "BASELINE_ROUTE_ANCHOR_CREATED", "BASELINE_BACKEND_ANCHOR_CREATED"]
    engine.dispose()


def test_capture_replays_idempotently_and_rejects_stale_state(tmp_path):
    scope, _sessions, engine = fixture(tmp_path)
    service = BaselineParityApplicationService(scope=scope, now_provider=lambda: NOW)
    request = BaselineParityCaptureRequest(expected_state_version=1, idempotency_key="parity-1", actor="operator")
    first = service.capture("run-1", request)
    replay = service.capture("run-1", request)
    assert replay.evidence_id == first.evidence_id
    assert replay.idempotent_replay is True

    stale = BaselineParityCaptureRequest(expected_state_version=1, idempotency_key="parity-2", actor="operator")
    try:
        service.capture("run-1", stale)
    except Exception as error:
        assert getattr(error, "code") == "STALE_STATE_VERSION"
    else:
        raise AssertionError("stale capture was accepted")
    engine.dispose()


def test_recapture_preserves_old_artifacts_and_versions_changed_evidence(tmp_path):
    scope, sessions, engine = fixture(tmp_path)
    service = BaselineParityApplicationService(scope=scope, now_provider=lambda: NOW)
    first = service.capture("run-1", BaselineParityCaptureRequest(expected_state_version=1, idempotency_key="parity-1", actor="operator"))
    with sessions() as session:
        validation = session.get(BaselineValidationModel, "validation-1")
        validation.results = [{"kind": "test", "target_id": "script:test", "status": "failed", "failed_tests": ["a newer failure"]}]
        session.commit()

    second = service.capture("run-1", BaselineParityCaptureRequest(
        expected_state_version=first.state_version, idempotency_key="parity-2", actor="operator",
    ))

    assert second.artifact_ids != first.artifact_ids
    assert any("a newer failure" in item["message"] for item in second.failures)
    engine.dispose()



def test_capture_is_available_through_versioned_api(monkeypatch, tmp_path):
    scope, _sessions, engine = fixture(tmp_path)
    service = BaselineParityApplicationService(scope=scope, now_provider=lambda: NOW)
    app.dependency_overrides[baseline_parity_routes.get_service] = lambda: service

    with TestClient(app) as client:
        response = client.post("/api/v1/runs/run-1/baseline/parity", json={"expected_state_version": 1, "idempotency_key": "api-1", "actor": "operator"})
        assert response.status_code == 200
        assert response.json()["status"] == "captured"
        for section in ("failures", "routes", "backend-integration", "anchors"):
            section_response = client.get(f"/api/v1/runs/run-1/baseline/{section}")
            assert section_response.status_code == 200
    engine.dispose()


def test_capture_events_are_replayable_through_sse_after_reopen(monkeypatch, tmp_path):
    scope, _sessions, engine = fixture(tmp_path)
    service = BaselineParityApplicationService(scope=scope, now_provider=lambda: NOW)
    result = service.capture("run-1", BaselineParityCaptureRequest(expected_state_version=1, idempotency_key="sse-1", actor="operator"))

    class Request:
        headers = {"last-event-id": "0"}
        query_params = {}
        calls = 0

        async def is_disconnected(self):
            self.calls += 1
            return self.calls > 1

    monkeypatch.setattr(runs_routes, "session_scope", scope)
    response = stream_run_events("run-1", Request())
    first = asyncio.run(response.body_iterator.__anext__())

    assert f"id: {result.event_sequence - 2}" in first
    assert "event: BASELINE_FAILURES_FINGERPRINTED" in first
    engine.dispose()


def test_capture_rejects_missing_and_mismatched_prerequisite_checksums(tmp_path):
    scope, sessions, engine = fixture(tmp_path)
    with sessions() as session:
        session.add(ArtifactMetadataModel(id="metadata-prereq", run_id="run-1", stage_id=None, artifact_type="json", relative_path="01_baseline/prereq.json", checksum="sha256:actual", created_at=NOW))
        session.commit()
    service = BaselineParityApplicationService(scope=scope, now_provider=lambda: NOW)
    missing = BaselineParityCaptureRequest(expected_state_version=1, idempotency_key="prereq-missing", actor="operator", prerequisite_artifact_ids=["prereq"])
    try:
        service.capture("run-1", missing)
    except Exception as error:
        assert getattr(error, "code") == "PREREQUISITE_ARTIFACT_CHECKSUM_REQUIRED"
    else:
        raise AssertionError("missing prerequisite checksum was accepted")
    mismatch = BaselineParityCaptureRequest(expected_state_version=1, idempotency_key="prereq-mismatch", actor="operator", prerequisite_artifact_ids=["prereq"], prerequisite_artifact_checksums={"prereq": "sha256:wrong"})
    try:
        service.capture("run-1", mismatch)
    except Exception as error:
        assert getattr(error, "code") == "PREREQUISITE_ARTIFACT_CHECKSUM_MISMATCH"
    else:
        raise AssertionError("mismatched prerequisite checksum was accepted")
    engine.dispose()


def test_installation_failure_diagnostics_are_fingerprinted():
    service = BaselineParityApplicationService()
    installation = type("Installation", (), {"status": "failed", "blockers": ["BASELINE_INSTALL_FAILED"], "artifact_ids": ["stderr-1"]})()
    store = type("Store", (), {"read_artifact_by_id": lambda self, artifact_id: type("Artifact", (), {"content": "npm ERR! E401 unauthorized"})()})()
    failures, diagnostics = service._failures([], [installation], store)
    assert any(item["kind"] == "install" for item in diagnostics)
    assert any(item["kind"] == "install" for item in failures)


def test_parity_recapture_uses_only_the_latest_validation_for_each_kind():
    history = [
        SimpleNamespace(id="test-old", kind="test"),
        SimpleNamespace(id="lint-current", kind="lint"),
        SimpleNamespace(id="test-current", kind="test"),
    ]

    selected = BaselineParityApplicationService._latest_validations(history)

    assert [(item.kind, item.id) for item in selected] == [
        ("test", "test-current"), ("lint", "lint-current"),
    ]
