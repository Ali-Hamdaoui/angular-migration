from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.planning_contracts import PlanCreateRequest
from app.api.routes import plans as plans_routes
from app.api.routes.plans import get_service
from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType
from app.main import app
from app.repositories.models import (
    ActivePlanVersionModel,
    ArtifactMetadataModel,
    Base,
    BuildSystemDecisionModel,
    MigrationPlanModel,
    MigrationRunModel,
    StageExecutionPlanModel,
    WorkflowEventModel,
    ExecutionProfileModel,
)
from app.repositories.compatibility_models import CompatibilityResolutionModel, G05ApprovalModel
from app.repositories.session import create_database_engine
from app.services.planning_evidence_application_service import PlanningEvidenceApplicationService
from app.domain.compatibility import calculate_stage1_profile_checksum
from app.services.compatibility_evidence_application_service import CompatibilityEvidenceApplicationService


NOW = datetime(2026, 7, 19, tzinfo=UTC)


def setup(tmp_path: Path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'test.db'}", sqlite_wal_enabled=False)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    run_root = tmp_path / "artifacts" / "run-1"
    store = LocalFilesystemArtifactStore(tmp_path / "artifacts", fixed_run_root=run_root)
    store.ensure_run_layout("run-1")
    prerequisite = store.write_text_artifact("run-1", "02_analysis/findings.json", '{"finding":"builder"}', ArtifactType.JSON, created_at=NOW)
    with sessions.begin() as session:
        session.add(MigrationRunModel(id="run-1", status="RUNNING", run_phase="PLANNING", phase_status="running", approval_status="approved", repair_status="not_required", state_version=1, actor="operator", artifact_root=str(run_root), created_at=NOW, updated_at=NOW))
        session.add(ArtifactMetadataModel(id="metadata-" + prerequisite.ref.artifact_id, run_id="run-1", stage_id=None, artifact_type="json", relative_path=prerequisite.ref.relative_path, checksum=prerequisite.ref.checksum, created_at=NOW))

    def scope():
        from contextlib import contextmanager

        @contextmanager
        def managed():
            session = sessions()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        return managed()

    service = PlanningEvidenceApplicationService(scope=scope, now_provider=lambda: NOW, artifact_store_factory=lambda _run: store)
    payload = PlanCreateRequest(
        expected_state_version=1,
        idempotency_key="plan-1",
        source_exact="18.2.13",
        source_family="angular-18.x",
        target_family="angular-21.x",
        catalogue_version="catalog-v1",
        input_fingerprint="sha256:" + "1" * 64,
        execution_profile_id="profile-node22-npm10",
        target_cli_exact="19.2.0",
        stage_route=[
            ("angular-18.x", "angular-19.x", "stage-18-to-19", "19.2.0"),
            ("angular-19.x", "angular-20.x", "stage-19-to-20", "20.0.0"),
            ("angular-20.x", "angular-21.x", "stage-20-to-21", "21.0.0"),
        ],
        builder="@angular-devkit/build-angular:application",
        prerequisite_artifacts=[{"artifact_id": prerequisite.ref.artifact_id, "checksum": prerequisite.ref.checksum}],
    )
    artifact_set_checksum = "sha256:" + hashlib.sha256(json.dumps([(prerequisite.ref.artifact_id, prerequisite.ref.checksum)], separators=(",", ":")).encode()).hexdigest()
    payload = payload.model_copy(update={"input_fingerprint": artifact_set_checksum})
    package_checksum = "sha256:" + "2" * 64
    profile_checksum = "sha256:" + "6" * 64
    stage1_profile = {
        "profile_id": payload.execution_profile_id, "angular_exact": "19.2.0", "angular_cli_exact": "21.0.0",
        "node_exact": "22.0.0", "npm_exact": "10.0.0", "npx_exact": "10.0.0",
        "node_executable": "node", "npm_executable": "npm", "npx_executable": "npx",
        "operating_system": "windows", "architecture": "amd64", "catalogue_version": payload.catalogue_version,
        "source_angular_exact": payload.source_exact, "source_execution_profile_checksum": profile_checksum,
    }
    stage1_profile["stage1_profile_checksum"] = calculate_stage1_profile_checksum(stage1_profile)
    stage1_profile["checksum"] = stage1_profile["stage1_profile_checksum"]
    package = {
        "source_exact": payload.source_exact,
        "source_family": payload.source_family,
        "target_family": payload.target_family,
        "catalogue_version": payload.catalogue_version,
        "selected_profile": stage1_profile,
        "route": [
            {"source_family": item[0], "target_family": item[1], "stage_id": item[2], "target_angular_exact": item[3], "target_cli_exact": payload.target_cli_exact if index == 0 else item[3]}
            for index, item in enumerate(payload.stage_route)
        ],
    }
    with sessions.begin() as session:
        session.add(ExecutionProfileModel(
            id="profile-resolution-1", run_id="run-1", idempotency_key="profile-1", request_checksum="sha256:" + "7" * 64,
            policy_version="angular-source-runtime-v1", status="resolved", source_angular_exact=payload.source_exact,
            selected_profile_id=payload.execution_profile_id, selected_checksum=profile_checksum,
            profiles=[{"profile_id": payload.execution_profile_id, "checksum": profile_checksum}], blockers=[], guidance=[], artifact_ids=[],
            state_version=1, event_sequence=1, created_at=NOW, updated_at=NOW,
        ))
        session.add(CompatibilityResolutionModel(
            id="resolution-1", run_id="run-1", idempotency_key="feasibility-1", request_checksum="sha256:" + "3" * 64,
            actor="operator", status="resolved", catalogue_version=payload.catalogue_version, catalogue_checksum="sha256:" + "4" * 64,
            registry_snapshot_id="registry-1", registry_snapshot_checksum="sha256:" + "5" * 64, registry_snapshot={},
            runtime_candidates=[], source_exact=payload.source_exact, source_family=payload.source_family,
            target_family=payload.target_family, support_level="supported", route=package["route"], selected_profile=package["selected_profile"],
            blockers=[], warnings=[], package=package, package_checksum=package_checksum,
            artifact_set_checksum=artifact_set_checksum, artifact_ids=[prerequisite.ref.artifact_id], artifact_checksums={prerequisite.ref.artifact_id: prerequisite.ref.checksum},
             source_execution_profile_checksum=profile_checksum, stage1_profile_checksum=stage1_profile["stage1_profile_checksum"],
             workspace_fingerprint=None, plan_version=None, state_version=1, event_sequence=1, created_at=NOW, updated_at=NOW,
        ))
        session.add(G05ApprovalModel(
            id="g05-1", run_id="run-1", gate_id="G05", gate_version="g05-v1", idempotency_key="gate:feasibility-1",
            actor="operator", status="approved", decision="approve", package_checksum=package_checksum,
            artifact_set_checksum=artifact_set_checksum, workspace_fingerprint=None, plan_version=None,
            state_version=1, event_sequence=1, artifact_ids=[prerequisite.ref.artifact_id],
            prerequisite_artifact_ids=[prerequisite.ref.artifact_id],
            prerequisite_artifact_checksums={prerequisite.ref.artifact_id: prerequisite.ref.checksum},
            input_bundle_checksum=CompatibilityEvidenceApplicationService._input_bundle_checksum(
                [{"artifact_id": prerequisite.ref.artifact_id, "checksum": prerequisite.ref.checksum}],
                package_checksum, None, None,
            ),
            comment=None,
            stale_reason=None, expires_at=None, created_at=NOW, updated_at=NOW,
        ))
    return service, payload, sessions, store


def test_persists_plan_stage_decision_pointer_artifacts_and_events(tmp_path):
    service, payload, sessions, store = setup(tmp_path)

    result = service.create("run-1", payload, "operator")

    assert len(result.artifact_ids) == 7
    assert result.plan["version"] == 1
    assert result.stage_plan["stage_id"] == "stage-18-to-19"
    assert result.builder_decision["action"] == "preserve"
    with sessions() as session:
        assert session.query(MigrationPlanModel).count() == 1
        assert session.query(StageExecutionPlanModel).count() == 1
        assert session.query(BuildSystemDecisionModel).count() == 1
        assert session.query(ActivePlanVersionModel).count() == 2
        assert session.query(ArtifactMetadataModel).count() == 8
        assert [event.event_type for event in session.query(WorkflowEventModel).order_by(WorkflowEventModel.sequence)] == ["MIGRATION_PLAN_CREATED", "STAGE_PLAN_CREATED"]
        assert session.query(MigrationRunModel).one().state_version == 3
    assert all(store.read_artifact_by_id(item).ref.checksum == result.artifact_checksums[item] for item in result.artifact_ids)


def test_api_exposes_plan_reads_and_idempotent_replay(tmp_path):
    service, payload, _, _ = setup(tmp_path)
    app.dependency_overrides[get_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.post("/api/v1/runs/run-1/plans", headers={"x-authenticated-actor": "operator"}, json=payload.model_dump(mode="json"))
        assert response.status_code == 200
        body = response.json()
        assert len(body["artifact_ids"]) == 7
        assert client.get("/api/v1/runs/run-1/plan", headers={"x-authenticated-actor": "operator"}).status_code == 200
        assert client.get("/api/v1/runs/run-1/stages/stage-18-to-19/plan", headers={"x-authenticated-actor": "operator"}).status_code == 200
        replay = client.post("/api/v1/runs/run-1/plans", headers={"x-authenticated-actor": "operator"}, json=payload.model_dump(mode="json"))
        assert replay.status_code == 200
        assert replay.json()["idempotent_replay"] is True
    finally:
        app.dependency_overrides.pop(get_service, None)


def test_rejects_stale_and_unauthorized_requests_without_persisting(tmp_path):
    service, payload, sessions, _ = setup(tmp_path)
    with pytest.raises(Exception) as unauthorized:
        service.create("run-1", payload, "other-operator")
    assert getattr(unauthorized.value, "code", None) == "RUN_NOT_AUTHORIZED"
    with pytest.raises(Exception) as stale:
        service.create("run-1", payload.model_copy(update={"expected_state_version": 2}), "operator")
    assert getattr(stale.value, "code", None) == "STALE_STATE_VERSION"
    with sessions() as session:
        assert session.query(MigrationPlanModel).count() == 0
        assert session.query(WorkflowEventModel).count() == 0


def test_tampered_plan_artifact_is_rejected_on_read(tmp_path):
    service, payload, _, store = setup(tmp_path)
    result = service.create("run-1", payload, "operator")
    stored = store.read_artifact_by_id(result.artifact_ids[0])
    (store._fixed_run_root / stored.ref.relative_path).write_text("tampered", encoding="utf-8")

    with pytest.raises(Exception) as error:
        service.get_plan("run-1", "operator")
    assert getattr(error.value, "code", None) == "PLAN_ARTIFACT_INTEGRITY_FAILED"
