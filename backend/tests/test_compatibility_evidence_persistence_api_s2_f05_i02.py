from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.compatibility_contracts import FeasibilityCreateRequest, G05DecisionRequest
from app.api.routes import compatibility as compatibility_routes
from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.compatibility import CompatibilityCatalogue, CompatibilityCatalogueEntry
from app.domain.contracts import ArtifactType
from app.domain.execution_profile import RuntimeCandidate
from app.main import app
from app.repositories.models import (
    ArtifactMetadataModel,
    Base,
    CompatibilityCatalogueModel,
    CompatibilityResolutionModel,
    G05ApprovalModel,
    MigrationRunModel,
    PlanningJobModel,
    RegistrySnapshotModel,
    WorkflowEventModel,
)
from app.repositories.session import create_database_engine
from app.services.compatibility_application_service import CompatibilityResolver
from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider
from app.services.compatibility_evidence_application_service import CompatibilityEvidenceApplicationService


NOW = datetime(2026, 7, 19, tzinfo=UTC)


def _catalogue():
    return CompatibilityCatalogue.build(
        "catalog-v1",
        tuple(
            CompatibilityCatalogueEntry(
                stage_id=f"angular-{major}-to-{major + 1}",
                source_family=f"angular-{major}.x",
                target_family=f"angular-{major + 1}.x",
                target_angular_exact=f"{major + 1}.0.0",
                target_cli_exact=f"{major + 1}.0.0",
                node_major=20,
                npm_major=10,
                support_level="historical_experimental",
                fixture_status="incomplete",
                validation_policy_id="angular-stage-standard-v2",
                known_risks=("historical_fixture_evidence_incomplete",),
            )
            for major in range(18, 21)
        ),
    )


def _candidate(**changes):
    values = dict(
        profile_id="node-20-approved",
        node_executable=r"C:\Tools\node\node.exe",
        node_exact="20.11.1",
        npm_executable=r"C:\Tools\node\npm.cmd",
        npm_exact="10.2.4",
        npx_executable=r"C:\Tools\node\npx.cmd",
        npx_exact="10.2.4",
    )
    values.update(changes)
    return RuntimeCandidate(**values)


def setup(tmp_path: Path, *, catalogue=None):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'test.db'}", sqlite_wal_enabled=False)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    run_root = tmp_path / "artifacts" / "run-1"
    store = LocalFilesystemArtifactStore(tmp_path / "artifacts", fixed_run_root=run_root)
    store.ensure_run_layout("run-1")
    prerequisite = store.write_text_artifact("run-1", "02_analysis/findings.json", '{"finding":"builder"}', ArtifactType.JSON, created_at=NOW)
    with sessions.begin() as session:
        session.add(MigrationRunModel(id="run-1", status="RUNNING", run_phase="FEASIBILITY", phase_status="running", approval_status="approved", repair_status="not_required", state_version=1, actor="operator", artifact_root=str(run_root), created_at=NOW, updated_at=NOW))
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

    catalogue = catalogue or _catalogue()
    resolver = CompatibilityResolver(catalogue)
    service = CompatibilityEvidenceApplicationService(session_scope_factory=scope, resolver=resolver, now_provider=lambda: NOW)
    payload = FeasibilityCreateRequest(expected_state_version=1, idempotency_key="feasibility-1", source_angular_exact="18.2.4", catalogue_version=catalogue.version, registry_snapshot_id="registry-1", registry_snapshot_checksum="sha256:" + "b" * 64, prerequisite_artifacts=[{"artifact_id": prerequisite.ref.artifact_id, "checksum": prerequisite.ref.checksum}], runtime_candidates=(_candidate(),), workspace_fingerprint="sha256:" + "c" * 64)
    return service, payload, sessions, store, resolver


def test_persists_six_immutable_evidence_artifacts_and_ordered_events(tmp_path):
    service, payload, sessions, store, _ = setup(tmp_path)

    result = service.resolve("run-1", payload, "operator")

    assert result.status == "feasible_with_warnings"
    assert len(result.artifact_ids) == 6
    assert all(checksum.startswith("sha256:") for checksum in result.artifact_checksums.values())
    with sessions() as session:
        assert session.query(CompatibilityCatalogueModel).count() == 1
        assert session.query(RegistrySnapshotModel).count() == 1
        assert session.query(CompatibilityResolutionModel).count() == 1
        assert session.query(G05ApprovalModel).count() == 1
        assert [event.event_type for event in session.query(WorkflowEventModel).order_by(WorkflowEventModel.sequence)] == ["COMPATIBILITY_RESOLUTION_STARTED", "COMPATIBILITY_RESOLUTION_COMPLETED", "G05_CREATED"]
        assert session.query(MigrationRunModel).one().state_version == 3
    package = store.read_artifact_by_id(result.artifact_ids[-1])
    assert package.ref.checksum == result.artifact_checksums[result.artifact_ids[-1]]
    assert "artifact_root" not in package.content


def test_api_exposes_snapshot_and_decision_with_idempotent_replay(tmp_path):
    service, payload, sessions, _, _ = setup(tmp_path)
    app.dependency_overrides[compatibility_routes.get_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.post("/api/v1/runs/run-1/feasibility", headers={"x-authenticated-actor": "operator", "x-correlation-id": "corr-1"}, json=payload.model_dump(mode="json"))
        assert response.status_code == 200
        body = response.json()
        assert len(body["artifact_ids"]) == 6
        assert all(link.startswith("/api/v1/artifacts/") for link in body["artifact_links"].values())
        replay = client.post("/api/v1/runs/run-1/feasibility", headers={"x-authenticated-actor": "operator"}, json=payload.model_dump(mode="json"))
        assert replay.status_code == 200
        assert replay.json()["idempotent_replay"] is True
        decision = G05DecisionRequest(expected_state_version=3, idempotency_key="g05-decision-1", gate_version=body["gate_version"], package_checksum=body["package_checksum"], artifact_set_checksum=body["package"]["artifact_set_checksum"], workspace_fingerprint=payload.workspace_fingerprint, decision="approve_with_comment", comment="Proceed with the documented experimental risk.")
        decision_response = client.post("/api/v1/runs/run-1/approvals/G05/decisions", headers={"x-authenticated-actor": "operator"}, json=decision.model_dump(mode="json"))
        assert decision_response.status_code == 200
        assert decision_response.json()["accepted"] is True
        assert client.post("/api/v1/runs/run-1/approvals/G05/decisions", headers={"x-authenticated-actor": "operator"}, json=decision.model_dump(mode="json")).json()["idempotent_replay"] is True
    finally:
        app.dependency_overrides.pop(compatibility_routes.get_service, None)
    with sessions() as session:
        assert session.query(G05ApprovalModel).count() == 2
        assert session.query(MigrationRunModel).one().state_version == 4
        job = session.query(PlanningJobModel).one()
        assert (job.status, job.current_step, job.attempt, job.correlation_id) == ("generating_plan", "generating_plan", 0, "planning:run-1")


def test_rejects_stale_state_checksum_and_unauthorized_actor_without_mutation(tmp_path):
    service, payload, sessions, _, _ = setup(tmp_path)
    with pytest.raises(Exception) as unauthorized:
        service.resolve("run-1", payload, "other-operator")
    assert getattr(unauthorized.value, "code", None) == "RUN_NOT_AUTHORIZED"
    with pytest.raises(Exception) as stale:
        service.resolve("run-1", payload.model_copy(update={"expected_state_version": 2}), "operator")
    assert getattr(stale.value, "code", None) == "STALE_STATE_VERSION"
    with sessions() as session:
        assert session.query(CompatibilityResolutionModel).count() == 0
        assert session.query(WorkflowEventModel).count() == 0


def test_reuses_versioned_catalogue_and_registry_metadata_on_new_resolution(tmp_path):
    service, payload, sessions, _, _ = setup(tmp_path)

    service.resolve("run-1", payload, "operator")
    service.resolve("run-1", payload.model_copy(update={"expected_state_version": 3, "idempotency_key": "feasibility-2"}), "operator")

    with sessions() as session:
        assert session.query(CompatibilityCatalogueModel).count() == 1
        assert session.query(RegistrySnapshotModel).count() == 1
        assert session.query(CompatibilityResolutionModel).count() == 2


def test_catalog_v2_node_22_profile_creates_approvable_g05_and_continuation_job(tmp_path):
    catalogue = CompatibilityCatalogueProvider().load()
    service, payload, sessions, _, _ = setup(tmp_path, catalogue=catalogue)
    payload = payload.model_copy(update={
        "runtime_candidates": (_candidate(profile_id="node-22-approved", node_exact="22.23.1", npm_exact="10.9.8", npx_exact="10.9.8"),),
    })

    result = service.resolve("run-1", payload, "operator")
    decision = G05DecisionRequest(
        expected_state_version=result.state_version,
        idempotency_key="g05-v2-approve",
        gate_version=result.gate_version,
        package_checksum=result.package_checksum,
        artifact_set_checksum=result.package["artifact_set_checksum"],
        workspace_fingerprint=payload.workspace_fingerprint,
        decision="approve",
    )
    accepted = service.decide_g05("run-1", decision, "operator")

    assert result.status == "feasible_with_warnings"
    assert result.gate_status == "pending"
    assert accepted.accepted is True
    with sessions() as session:
        gate = session.query(G05ApprovalModel).filter_by(run_id="run-1", status="approved").one()
        job = session.query(PlanningJobModel).one()
        assert gate.package_checksum == result.package_checksum
        assert (job.status, job.current_step) == ("generating_plan", "generating_plan")


def test_feasibility_requires_physical_workspace_fingerprint(tmp_path):
    service, payload, sessions, _, _ = setup(tmp_path)

    with pytest.raises(Exception) as error:
        service.resolve("run-1", payload.model_copy(update={"workspace_fingerprint": None}), "operator")

    assert getattr(error.value, "code", None) == "COMPATIBILITY_WORKSPACE_FINGERPRINT_REQUIRED"
    with sessions() as session:
        assert session.query(CompatibilityResolutionModel).count() == 0
        assert session.query(G05ApprovalModel).count() == 0


def test_g05_cannot_approve_legacy_package_without_workspace_fingerprint(tmp_path):
    service, payload, sessions, _, _ = setup(tmp_path)
    result = service.resolve("run-1", payload, "operator")
    with sessions.begin() as session:
        gate = session.query(G05ApprovalModel).filter_by(run_id="run-1", status="pending").one()
        gate.workspace_fingerprint = None

    decision = G05DecisionRequest(
        expected_state_version=result.state_version,
        idempotency_key="g05-missing-fingerprint",
        gate_version=result.gate_version,
        package_checksum=result.package_checksum,
        artifact_set_checksum=result.package["artifact_set_checksum"],
        workspace_fingerprint=None,
        decision="approve",
    )

    with pytest.raises(Exception) as error:
        service.decide_g05("run-1", decision, "operator")

    assert getattr(error.value, "code", None) == "G05_WORKSPACE_FINGERPRINT_REQUIRED"
    with sessions() as session:
        gate = session.query(G05ApprovalModel).filter_by(run_id="run-1").order_by(G05ApprovalModel.created_at.desc()).first()
        assert gate.status == "stale"
        assert "fingerprint" in (gate.stale_reason or "").lower()
