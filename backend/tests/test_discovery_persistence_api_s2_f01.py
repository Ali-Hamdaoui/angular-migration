"""S2-F01 verification: durable discovery evidence is authoritative and replayable."""

import asyncio
import json
from contextlib import contextmanager
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.discovery_contracts import DiscoveryCaptureRequest
from app.artifact_store import LocalFilesystemArtifactStore
from app.api.routes import discovery as discovery_routes
from app.api.routes import runs as runs_routes
from app.main import app
from app.repositories.models import ArtifactMetadataModel, Base, DiscoveryEvidenceModel, G03ApprovalModel, MigrationRunModel, WorkflowEventModel
from app.services.discovery_evidence_application_service import DiscoveryEvidenceApplicationService

NOW = datetime(2026, 7, 18, tzinfo=UTC)


def fixture(tmp_path):
    workspace = tmp_path / "source-snapshot"
    workspace.mkdir()
    (workspace / "package.json").write_text(json.dumps({"dependencies": {"@angular/core": "18.2.0"}, "scripts": {"test": "ng test"}}), encoding="utf-8")
    (workspace / "angular.json").write_text(json.dumps({"projects": {"app": {"projectType": "application", "architect": {"build": {"builder": "@angular-devkit/build-angular:application"}}}}}), encoding="utf-8")
    engine = create_engine(f"sqlite:///{tmp_path / 'state.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as session:
        session.add(MigrationRunModel(id="run-1", status="CREATED", run_phase="DISCOVERY_BASELINE", phase_status="running", approval_status="approved", repair_status="not_required", state_version=1, artifact_root=str(tmp_path / "artifacts"), workspace_aliases={"SOURCE_SNAPSHOT": str(workspace)}, created_at=NOW, updated_at=NOW))
        session.add(ArtifactMetadataModel(id="metadata-baseline", run_id="run-1", stage_id=None, artifact_type="json", relative_path="baseline.json", checksum="sha256:baseline", created_at=NOW))
        session.add(G03ApprovalModel(id="g03-1", run_id="run-1", gate_id="G03", gate_version="g03-v1", idempotency_key="g03-1", actor="operator", status="approved", decision="approved", package_checksum="sha256:package", evidence_set_checksum="sha256:evidence", qualification_status="qualified", policy_version="g03-v1", state_version=1, event_sequence=1, sandbox_fingerprint="sha256:sandbox", execution_profile_checksum="sha256:profile", package={}, artifact_ids=[], comment=None, created_at=NOW, updated_at=NOW))
        session.commit()
    @contextmanager
    def scope():
        with sessions() as session:
            yield session
            session.commit()
    return scope, sessions, engine


def request(key="discovery-1", version=1, checksum="sha256:baseline"):
    return DiscoveryCaptureRequest(expected_state_version=version, idempotency_key=key, actor="operator", prerequisite_artifact_ids=["baseline"], prerequisite_artifact_checksums={"baseline": checksum})


def test_discovery_persists_immutable_evidence_events_and_idempotent_replay(tmp_path):
    scope, sessions, engine = fixture(tmp_path)
    service = DiscoveryEvidenceApplicationService(session_scope_factory=scope, now_provider=lambda: NOW)
    result = service.capture("run-1", request())
    assert service.capture("run-1", request()).idempotent_replay
    with sessions() as session:
        record = session.get(DiscoveryEvidenceModel, result.discovery_id)
        events = list(session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == "run-1").order_by(WorkflowEventModel.sequence)))
        assert record is not None and len(result.artifact_ids) == 7
        assert [event.event_type for event in events] == ["DISCOVERY_STARTED", *["SCANNER_COMPLETED"] * 7, "DISCOVERY_COMPLETED"]
        assert [event.sequence for event in events] == list(range(1, 10))
        assert all(value.startswith("sha256:") for value in result.artifact_checksums.values())
        store = LocalFilesystemArtifactStore(tmp_path / "artifacts", fixed_run_root=tmp_path / "artifacts")
        artifact = store.read_artifact_by_id(result.artifact_ids[0])
        assert artifact.ref.checksum == result.artifact_checksums[artifact.ref.artifact_id]
        replacement = store.write_text_artifact("run-1", artifact.ref.relative_path, artifact.content, artifact.ref.artifact_type, created_by="test")
        assert replacement.ref.relative_path != artifact.ref.relative_path
        assert store.read_artifact_by_id(artifact.ref.artifact_id).content == artifact.content
    engine.dispose()


def test_discovery_rejects_tampered_prerequisite_and_stale_state_before_events(tmp_path):
    scope, sessions, engine = fixture(tmp_path)
    service = DiscoveryEvidenceApplicationService(session_scope_factory=scope, now_provider=lambda: NOW)
    for payload, code in ((request("tampered", checksum="sha256:tampered"), "PREREQUISITE_ARTIFACT_CHECKSUM_MISMATCH"), (request("stale", version=2), "STALE_STATE_VERSION")):
        try:
            service.capture("run-1", payload)
        except Exception as error:
            assert getattr(error, "code") == code
        else:
            raise AssertionError(f"{code} was accepted")
    with sessions() as session:
        assert session.scalar(select(DiscoveryEvidenceModel)) is None
        assert session.scalar(select(WorkflowEventModel)) is None
    engine.dispose()


def test_discovery_versioned_api_and_sse_replay_expose_authoritative_events(monkeypatch, tmp_path):
    scope, _sessions, engine = fixture(tmp_path)
    app.dependency_overrides[discovery_routes.service] = lambda: DiscoveryEvidenceApplicationService(session_scope_factory=scope, now_provider=lambda: NOW)
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/runs/run-1/discovery", json=request().model_dump(mode="json"))
            assert response.status_code == 200
            assert client.get("/api/v1/runs/run-1/discovery").json()["discovery_id"] == response.json()["discovery_id"]
        class Request:
            headers = {"last-event-id": "0"}; query_params = {}; calls = 0
            async def is_disconnected(self):
                self.calls += 1
                return self.calls > 1
        monkeypatch.setattr(runs_routes, "session_scope", scope)
        assert "event: DISCOVERY_STARTED" in asyncio.run(runs_routes.stream_run_events("run-1", Request()).body_iterator.__anext__())
    finally:
        app.dependency_overrides.pop(discovery_routes.service, None)
        engine.dispose()



def test_discovery_execution_failure_persists_a_blocked_result_and_event(tmp_path):
    scope, sessions, engine = fixture(tmp_path)

    class FailingCoordinator:
        def discover(self, _workspace):
            raise OSError("fixture storage interruption")

    service = DiscoveryEvidenceApplicationService(session_scope_factory=scope, coordinator=FailingCoordinator(), now_provider=lambda: NOW)
    result = service.capture("run-1", request("failure"))
    assert result.status == "blocked"
    assert result.error_code == "DISCOVERY_DEPENDENCY_FAILED"
    with sessions() as session:
        record = session.get(DiscoveryEvidenceModel, result.discovery_id)
        events = list(session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == "run-1").order_by(WorkflowEventModel.sequence)))
        assert record is not None and record.artifact_ids == []
        assert [event.event_type for event in events] == ["DISCOVERY_STARTED", "DISCOVERY_BLOCKED"]
    engine.dispose()
