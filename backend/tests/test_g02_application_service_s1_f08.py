from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.api.g02_contracts import G02DecisionRequest
from app.domain.snapshot import CreateSourceSnapshotRequest
from app.repositories.models import Base, G02ApprovalModel, MigrationRunModel, WorkflowEventModel
from app.services.g02_application_service import G02ApprovalApplicationService
from app.services.source_snapshot_application_service import SourceSnapshotApplicationService
from app.snapshots import SnapshotService
from app.workspaces.services import BaselineBoundaryError, WorkspaceService
from app.state.transition_service import StateTransitionService
from app.domain.contracts import WorkflowEventType

def _fixture(tmp_path: Path):
    source = tmp_path / "external-source"; source.mkdir(); (source / "app.ts").write_text("export const app = true;\n", encoding="utf-8")
    output = tmp_path / "external-output"; run_root = output / ".migration-factory" / "runs" / "run-1"; snapshot_root = run_root / "source-snapshot"; artifact_root = run_root / "artifacts"; now = datetime.now(UTC)
    engine = create_engine(f"sqlite:///{tmp_path / 'g02.db'}"); Base.metadata.create_all(engine); sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as session:
        session.add(MigrationRunModel(id="run-1", status="CREATED", run_phase="PREFLIGHT_SNAPSHOT", phase_status="running", approval_status="approved", repair_status="not_required", state_version=1, source_path=str(source), artifact_root=str(artifact_root), workspace_aliases={"SOURCE_SNAPSHOT": str(snapshot_root)}, created_at=now, updated_at=now)); session.commit()
    @contextmanager
    def scope():
        with sessions() as session:
            yield session
            session.commit()
    snapshot_service = SourceSnapshotApplicationService(SimpleNamespace(platform_repository_root=tmp_path / "platform"), session_scope_factory=scope, snapshot_service_factory=lambda root: SnapshotService(root))
    snapshot_service.create("run-1", CreateSourceSnapshotRequest(expected_state_version=1, idempotency_key="snapshot-1", actor="operator"))
    return source, snapshot_root, sessions, scope, engine

def _request(decision="approved", key="g02-1", expected=4, comment=None):
    return G02DecisionRequest(expected_state_version=expected, idempotency_key=key, actor="operator", decision=decision, comment=comment, gate_id="G02")

def test_g02_approval_persists_boundary_events_evidence_and_replays(tmp_path: Path):
    _, _, sessions, scope, engine = _fixture(tmp_path); service = G02ApprovalApplicationService(session_scope_factory=scope)
    result = service.decide("run-1", _request()); replay = service.decide("run-1", _request())
    assert result.status == "approved"; assert result.baseline_input_boundary.startswith("snapshot-"); assert replay.idempotent_replay is True
    with sessions() as session:
        events = list(session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == "run-1").order_by(WorkflowEventModel.sequence))); record = session.scalar(select(G02ApprovalModel).where(G02ApprovalModel.run_id == "run-1"))
        run = session.get(MigrationRunModel, "run-1"); assert [event.event_type for event in events] == ["SNAPSHOT_STARTED", "SNAPSHOT_PROGRESS_UPDATED", "SNAPSHOT_CREATED", "G02_CREATED", "SOURCE_INTEGRITY_VERIFIED", "G02_APPROVED"]; assert record is not None; assert len(record.artifact_ids) == 11; assert record.baseline_input_boundary == result.baseline_input_boundary; assert run is not None; assert run.approval_status == "approved"; assert run.phase_status == "running"
    engine.dispose()

def test_changed_source_marks_g02_stale_and_never_establishes_boundary(tmp_path: Path):
    source, _, _, scope, engine = _fixture(tmp_path); source.joinpath("app.ts").write_text("changed\n", encoding="utf-8")
    result = G02ApprovalApplicationService(session_scope_factory=scope).decide("run-1", _request())
    assert result.status == "stale"; assert result.baseline_input_boundary is None; assert result.stale_reason; engine.dispose()

def test_tampered_snapshot_manifest_is_fail_closed(tmp_path: Path):
    _, snapshot_root, _, scope, engine = _fixture(tmp_path); manifest = next(snapshot_root.glob("*/source-manifest.json")); manifest.chmod(0o644); manifest.write_text(manifest.read_text(encoding="utf-8").replace("source-snapshot-policy-v1", "tampered-policy"), encoding="utf-8")
    from app.services.g02_application_service import G02ApplicationError
    with pytest.raises(G02ApplicationError) as error: G02ApprovalApplicationService(session_scope_factory=scope).decide("run-1", _request())
    assert error.value.code == "SNAPSHOT_EVIDENCE_INVALID"; engine.dispose()

def test_g02_can_be_initialized_then_decided_and_replay_revalidates_package(tmp_path: Path):
    _, _, sessions, scope, engine = _fixture(tmp_path); service = G02ApprovalApplicationService(session_scope_factory=scope); initialized = service.initialize("run-1", _request(key="package-1")); assert initialized.status == "pending"; assert initialized.package["integrity"]["status"] == "verified"
    with sessions() as session:
        run = session.get(MigrationRunModel, "run-1"); assert run is not None; assert run.approval_status == "pending"; assert run.phase_status == "waiting_approval"
    approved = service.decide("run-1", _request(key="decision-1", expected=initialized.state_version)); assert approved.status == "approved"
    with sessions() as session:
        record = session.scalar(select(G02ApprovalModel).where(G02ApprovalModel.run_id == "run-1")); assert record is not None; record.package_checksum = "sha256:tampered"; session.commit()
    with pytest.raises(Exception) as error: service.decide("run-1", _request(key="decision-1", expected=approved.state_version))
    assert getattr(error.value, "code", None) == "STALE_EVIDENCE"; engine.dispose()

def test_baseline_workspace_requires_approved_verified_g02_boundary(tmp_path: Path):
    with pytest.raises(BaselineBoundaryError): WorkspaceService(tmp_path / "workspaces").create_baseline_workspace_from_snapshot(run_id="run-1", snapshot_root=tmp_path / "snapshot", source_root=tmp_path / "source", g02_service=None)

def test_new_decision_key_revalidates_and_marks_existing_g02_stale(tmp_path: Path):
    source, _, _, scope, engine = _fixture(tmp_path); service = G02ApprovalApplicationService(session_scope_factory=scope); approved = service.decide("run-1", _request(key="decision-1")); source.joinpath("app.ts").write_text("tampered\n", encoding="utf-8")
    stale = service.decide("run-1", _request(key="decision-2", expected=approved.state_version))
    assert stale.status == "stale"
    with scope() as session: assert session.scalar(select(G02ApprovalModel).where(G02ApprovalModel.run_id == "run-1")).status == "stale"
    engine.dispose()

def test_get_is_read_only_and_repeated_reads_remain_approved(tmp_path: Path):
    source, _, sessions, scope, engine = _fixture(tmp_path); service = G02ApprovalApplicationService(session_scope_factory=scope); service.decide("run-1", _request()); source.joinpath("app.ts").write_text("tampered\n", encoding="utf-8")
    assert service.get("run-1", "G02").status == "approved"
    assert service.get("run-1", "G02").status == "approved"
    with sessions() as session:
        assert session.scalar(select(G02ApprovalModel).where(G02ApprovalModel.run_id == "run-1")).status == "approved"
    engine.dispose()

def test_normal_run_state_changes_do_not_stale_approved_g02(tmp_path: Path):
    _, _, sessions, scope, engine = _fixture(tmp_path); service = G02ApprovalApplicationService(session_scope_factory=scope); service.decide("run-1", _request())
    with scope() as session:
        run = session.get(MigrationRunModel, "run-1")
        StateTransitionService(session).append_audit_event(run_id="run-1", idempotency_key="normal-progress", event_type=WorkflowEventType.COMMAND_OUTPUT_AVAILABLE, actor="worker", reason="normal progress", occurred_at=datetime.now(UTC))
        assert run.state_version > 6
    assert service.get("run-1", "G02").status == "approved"
    engine.dispose()

def test_policy_version_change_invalidates_existing_g02(tmp_path: Path):
    _, _, _, scope, engine = _fixture(tmp_path); service = G02ApprovalApplicationService(session_scope_factory=scope); service.decide("run-1", _request())
    with pytest.raises(Exception) as error: G02ApprovalApplicationService(session_scope_factory=scope, policy_version="source-snapshot-policy-v2").authorize_baseline("run-1")
    assert error.value.code == "STALE_EVIDENCE"; engine.dispose()

def test_authorize_baseline_resolves_persisted_approval(tmp_path: Path):
    _, _, _, scope, engine = _fixture(tmp_path); service = G02ApprovalApplicationService(session_scope_factory=scope); approved = service.decide("run-1", _request()); package = service.authorize_baseline("run-1")
    assert package.snapshot_id == approved.baseline_input_boundary; engine.dispose()



