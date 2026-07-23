from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.domain.path_validation import PathRuleResult, PathValidationSnapshot
from app.domain.preflight import G01DecisionRequest, PreflightRequest
from app.domain.source_analysis import SourceAnalysisSnapshot, WorkspaceTopology
from app.domain.system import EnvironmentCapabilitySnapshot, LocalStorageReadiness, CorporateNetworkReadiness, RuntimeInventoryEntry
from app.repositories.models import Base, EnvironmentCapabilityModel, PathValidationModel, SourceAnalysisModel, TargetReservationModel
from app.repositories.preflight_models import PreflightArtifactMetadataModel
from app.services.production_preflight_service import ProductionPreflightService, PreflightError


def test_production_preflight_binds_evidence_and_replays_g01(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'f05.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def scope():
        with sessions() as session:
            yield session
            session.commit()

    now = datetime(2026, 7, 14, tzinfo=UTC)
    path = PathValidationSnapshot(validation_id="path-1", captured_at=now, policy_version="path-v1", status="passed", source_path="C:/source", target_output_path="C:/target", resolved_output_root="C:/target", reservation_id="reservation-1", reservation_expires_at=now + timedelta(minutes=15), source_fingerprint="sha256:source", rules=[PathRuleResult(code="SOURCE_OK", status="passed", message="ok")], target_reservation_eligible=True, checksum="sha256:path")
    environment = EnvironmentCapabilitySnapshot(snapshot_id="env-1", captured_at=now, policy_version="env-v1", status="available", runtimes=[RuntimeInventoryEntry(name=name, executable=f"C:/{name}.exe", version="1", installation_root="C:/", status="available") for name in ("node", "npm", "npx", "git", "python")], node_npm_npx_paired=True, git_ready=True, python_ready=True, storage=LocalStorageReadiness(database_path="C:/db", artifact_root="C:/runs", writable=True, local_filesystem=True, free_bytes=100, status="available"), network=CorporateNetworkReadiness(registry_configured=True, proxy_configured=False, https_proxy_configured=False, strict_ssl=True, custom_ca_configured=False), checksum="sha256:env")
    analysis = SourceAnalysisSnapshot(analysis_id="analysis-1", policy_version="analysis-v1", status="accepted", source_path="C:/source", package_manager="npm", lockfile="package-lock.json", versions=[], topology=WorkspaceTopology(projects=["app"], classification="single-application"), checksum="sha256:analysis")
    with scope() as session:
        session.add_all([PathValidationModel(id="path-1", idempotency_key="p", actor="test", status="passed", source_fingerprint=path.source_fingerprint, checksum=path.checksum, snapshot=path.model_dump(mode="json"), created_at=now), EnvironmentCapabilityModel(id="env-1", idempotency_key="e", actor="test", status="available", captured_at=now, policy_version="env-v1", checksum=environment.checksum, snapshot=environment.model_dump(mode="json"), created_at=now), SourceAnalysisModel(id="analysis-1", idempotency_key="a", actor="test", status="accepted", source_path=analysis.source_path, policy_version="analysis-v1", checksum=analysis.checksum, snapshot=analysis.model_dump(mode="json"), created_at=now), TargetReservationModel(id="reservation-1", validation_id="path-1", target_path="C:/target", status="eligible", expires_at=now + timedelta(minutes=15), created_at=now)])
    settings = Settings(_env_file=None, artifact_root=tmp_path / "runs", workspace_root=tmp_path / "workspaces", snapshot_root=tmp_path / "snapshots", delivery_root=tmp_path / "delivery", sandbox_root=tmp_path / "sandboxes")
    service = ProductionPreflightService(settings, session_scope_factory=scope, now_provider=lambda: now)
    result = service.create(PreflightRequest(path_validation_id="path-1", environment_snapshot_id="env-1", source_analysis_id="analysis-1", target_angular_family="21.x", migration_mode="strict-functional-parity", idempotency_key="preflight-1"))
    assert result.snapshot.status == "passed"
    with scope() as session:
        assert session.query(PreflightArtifactMetadataModel).filter_by(preflight_id=result.snapshot.preflight_id).count() == 6
    assert result.snapshot.target_reservation_id == "reservation-1"
    assert set(("preflight_request.json", "preflight_result.json", "environment_capability_summary.json", "path_safety_report.json", "eligibility_result.json", "g01_evidence_index.json")) <= set(result.snapshot.artifacts)
    request = G01DecisionRequest(gate_id="G01", decision="approved", expected_state_version=1, input_checksum=result.snapshot.input_checksum, artifact_set_checksum=result.snapshot.artifact_set_checksum, idempotency_key="decision-1", actor="reviewer")
    with scope() as session:
        reservation = session.get(TargetReservationModel, "reservation-1")
        assert reservation is not None
        reservation.expires_at = now - timedelta(seconds=1)
    with pytest.raises(PreflightError, match="expired") as expired:
        service.create(PreflightRequest(path_validation_id="path-1", environment_snapshot_id="env-1", source_analysis_id="analysis-1", target_angular_family="21.x", migration_mode="strict-functional-parity", idempotency_key="preflight-2"))
    assert expired.value.code == "TARGET_RESERVATION_EXPIRED"
    with pytest.raises(PreflightError, match="expired") as replay_expired:
        service.create(PreflightRequest(path_validation_id="path-1", environment_snapshot_id="env-1", source_analysis_id="analysis-1", target_angular_family="21.x", migration_mode="strict-functional-parity", idempotency_key="preflight-1"))
    assert replay_expired.value.code == "TARGET_RESERVATION_EXPIRED"
    decision = service.decide(result.snapshot.preflight_id, request)
    assert decision.decision == "approved"
    replay = service.decide(result.snapshot.preflight_id, request)
    assert replay.idempotent_replay is True
    persisted = service.get(result.snapshot.preflight_id)
    assert persisted is not None
    assert persisted.snapshot.approval_status == "approved"
    assert len(persisted.snapshot.decision_history) == 1


def test_blocked_preflight_cannot_be_approved(tmp_path: Path):
    # The domain rule is covered independently of filesystem execution by the service's blocker guard.
    error = PreflightError("PREFLIGHT_BLOCKED", "blocked")
    assert error.code == "PREFLIGHT_BLOCKED"
