from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.repositories.models import Base, G03ApprovalModel, G04ApprovalModel, MigrationRunModel, SourceSnapshotModel
from app.services.planning_input_resolver import PlanningInputResolutionError, PlanningInputResolver
from app.services.registry_snapshot_builder import RegistrySnapshotBuilder


NOW = datetime(2026, 7, 28, tzinfo=UTC)
FINGERPRINT = "sha256:" + "3" * 64


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _g04(*, workspace_fingerprint=None):
    return G04ApprovalModel(
        id="g04-1", run_id="run-1", gate_id="G04", gate_version="g04-v1",
        idempotency_key="g04-1", actor="operator", status="approved", decision="approve",
        package_checksum="sha256:" + "4" * 64, artifact_set_checksum="sha256:" + "5" * 64,
        workspace_fingerprint=workspace_fingerprint, plan_version=None, state_version=1, event_sequence=1,
        artifact_ids=[], comment=None, stale_reason=None,
        created_at=NOW, updated_at=NOW,
    )


def _g03(*, fingerprint=FINGERPRINT):
    return G03ApprovalModel(
        id="g03-1", run_id="run-1", gate_id="G03", gate_version="g03-v1",
        idempotency_key="g03-1", actor="operator", status="approved", decision="approved",
        package_checksum="sha256:" + "1" * 64, evidence_set_checksum="sha256:" + "2" * 64,
        qualification_status="qualified", policy_version="g03-v1", state_version=1, event_sequence=1,
        sandbox_fingerprint=fingerprint, execution_profile_checksum="sha256:" + "7" * 64,
        package={}, artifact_ids=[], comment=None, created_at=NOW, updated_at=NOW,
    )


def test_legacy_g04_without_fingerprint_rebinds_to_approved_g03():
    session = _session()
    gate = _g04()
    session.add_all([_g03(), gate])
    session.flush()

    assert PlanningInputResolver._workspace_fingerprint(session, "run-1", gate) == FINGERPRINT


def test_g04_fingerprint_must_match_approved_g03():
    session = _session()
    gate = _g04(workspace_fingerprint="sha256:" + "9" * 64)
    session.add_all([_g03(), gate])
    session.flush()

    with pytest.raises(PlanningInputResolutionError) as error:
        PlanningInputResolver._workspace_fingerprint(session, "run-1", gate)

    assert error.value.code == "PLANNING_G04_WORKSPACE_FINGERPRINT_MISMATCH"


def test_missing_g03_fingerprint_fails_closed():
    session = _session()
    gate = _g04()
    session.add_all([_g03(fingerprint=""), gate])
    session.flush()

    with pytest.raises(PlanningInputResolutionError) as error:
        PlanningInputResolver._workspace_fingerprint(session, "run-1", gate)

    assert error.value.code == "PLANNING_WORKSPACE_FINGERPRINT_MISSING"


def test_exact_source_version_falls_back_to_created_npm_v1_snapshot(tmp_path):
    snapshot = tmp_path / "source-snapshot"
    snapshot.mkdir()
    (snapshot / "package-lock.json").write_text(
        '{"lockfileVersion":1,"dependencies":{"@angular/core":{"version":"11.0.4"}}}',
        encoding="utf-8",
    )
    session = _session()
    run = MigrationRunModel(
        id="run-1", status="FAILED", run_phase="FEASIBILITY_PLANNING", phase_status="failed",
        approval_status="approved", repair_status="not_required", state_version=1,
        source_version_detected="~11.0.4", actor="operator", created_at=NOW, updated_at=NOW,
    )
    session.add_all([
        run,
        SourceSnapshotModel(
            id="snapshot-1", run_id="run-1", execution_id=None, idempotency_key="snapshot-1",
            actor="operator", backend_instance_id=None, status="created", heartbeat_at=None,
            source_path=str(tmp_path / "source"), snapshot_path=str(snapshot), manifest_id="manifest-1",
            fingerprint="sha256:" + "8" * 64, policy_version="source-snapshot-v1", file_count=1,
            total_size_bytes=1, exclusions=[], git_metadata={}, artifact_ids=[], state_version=1,
            event_sequence=1, error_code=None, error_message=None, created_at=NOW, updated_at=NOW,
        ),
    ])
    session.flush()

    assert PlanningInputResolver._exact_source_from_evidence(session, run) == "11.0.4"
    assert run.source_version_detected == "11.0.4"
    assert run.source_version_family == "angular-11.x"


def test_registry_snapshot_uses_approved_exact_source_when_preflight_has_only_range():
    packages = RegistrySnapshotBuilder._resolved_packages(
        [{"package": "@angular/core", "declared": "~11.0.4", "resolved": None}],
        "11.0.4",
    )

    assert packages == [{
        "package": "@angular/core",
        "declared": "~11.0.4",
        "resolved": "11.0.4",
        "resolution_source": "approved_source_snapshot",
    }]
