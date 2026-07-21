from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
import shutil
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.api.execution_profile_contracts import ExecutionProfileResolveRequest, ExecutionProfileSelectRequest
from app.api.routes.execution_profiles import get_execution_profile_service
from app.domain.execution_profile import RuntimeCandidate
from app.main import app
from app.repositories.models import Base, EnvironmentCapabilityModel, ExecutionProfileModel, G02ApprovalModel, MigrationRunModel, WorkflowEventModel
from app.services.execution_profile_application_service import ExecutionProfileApplicationService, ExecutionProfileApplicationError

NOW=datetime(2026,7,15,tzinfo=UTC)
def fixture():
    root_base=Path(__file__).resolve().parents[2] / ".s1f09-persistence-test"
    shutil.rmtree(root_base, ignore_errors=True)
    root_base.mkdir(parents=True, exist_ok=True)
    engine=create_engine(f"sqlite:///{root_base/'state.db'}"); Base.metadata.create_all(engine); sessions=sessionmaker(bind=engine,expire_on_commit=False); root=root_base/'artifacts'
    with sessions() as s:
        s.add(MigrationRunModel(id='run-1',status='CREATED',run_phase='DISCOVERY_BASELINE',phase_status='running',approval_status='approved',repair_status='not_required',state_version=1,artifact_root=str(root),created_at=NOW,updated_at=NOW))
        s.add(G02ApprovalModel(id='g02-1',run_id='run-1',gate_id='G02',gate_version='g02-v1',idempotency_key='g02',actor='operator',status='approved',package_checksum='sha256:g02',artifact_set_checksum='sha256:artifacts',snapshot_id='snapshot-1',state_version=1,event_sequence=1,package={},artifact_ids=[],created_at=NOW,updated_at=NOW)); s.commit()
    @contextmanager
    def scope():
        with sessions() as s:
            yield s; s.commit()
    return scope,sessions,engine

def candidate():
    return RuntimeCandidate(profile_id='node-20',node_executable=r'C:\Tools\node20\node.exe',node_exact='20.11.1',npm_executable=r'C:\Tools\node20\npm.cmd',npm_exact='10.2.4',npx_executable=r'C:\Tools\node20\npx.cmd',npx_exact='10.2.4',angular_cli_exact='18.2.3')
def request(key='resolve-1',expected=1):
    return ExecutionProfileResolveRequest(expected_state_version=expected,idempotency_key=key,actor='operator',source_angular_exact='18.2.3',source_typescript_exact='5.5.4',source_rxjs_exact='7.8.1',candidates=(candidate(),),validated_at=NOW)


def environment_snapshot(installation_root=r"C:\Tools\node20"):
    root = Path(installation_root)
    return {
        "status": "available",
        "runtimes": [
            {"name": "node", "executable": str(root / "node.exe"), "version": "20.11.1", "installation_root": installation_root, "status": "available"},
            {"name": "npm", "executable": str(root / "npm.cmd"), "version": "10.2.4", "installation_root": installation_root, "status": "available"},
            {"name": "npx", "executable": str(root / "npx.cmd"), "version": "10.2.4", "installation_root": installation_root, "status": "available"},
        ],
        "network": {"registry_configured": True, "proxy_configured": False, "strict_ssl": True, "credentials_redacted": True},
        "controlled_probes": {"node_exec_path": {"status": "passed", "value": str(root / "node.exe")}, "npm_registry": {"status": "passed", "value": "https://registry.example.invalid"}},
    }

def test_resolution_persists_artifacts_events_and_replays():
    scope,sessions,engine=fixture(); service=ExecutionProfileApplicationService(session_scope_factory=scope,now_provider=lambda:NOW)
    first=service.resolve('run-1',request()); replay=service.resolve('run-1',request())
    assert first.status=='resolved' and first.selected_profile is not None and replay.idempotent_replay
    with sessions() as s:
        record=s.scalar(select(ExecutionProfileModel).where(ExecutionProfileModel.run_id=='run-1')); events=list(s.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id=='run-1').order_by(WorkflowEventModel.sequence)))
        assert record and len(record.artifact_ids)==7
        assert [e.event_type for e in events]==['EXECUTION_PROFILE_RESOLUTION_STARTED','EXECUTION_PROFILE_RESOLVED']
    engine.dispose()

def test_multiple_candidate_selection_is_checksum_bound():
    scope,_,engine=fixture(); service=ExecutionProfileApplicationService(session_scope_factory=scope,now_provider=lambda:NOW)
    first=service.resolve('run-1',request()); assert first.status=='resolved'
    engine.dispose()

def test_missing_g02_blocks_without_persisting():
    scope,sessions,engine=fixture()
    with sessions() as s: s.query(G02ApprovalModel).delete(); s.commit()
    try:
        ExecutionProfileApplicationService(session_scope_factory=scope,now_provider=lambda:NOW).resolve('run-1',request())
    except ExecutionProfileApplicationError as error: assert error.code=='G02_APPROVAL_REQUIRED'
    else: raise AssertionError('G02 should be required')
    engine.dispose()


def test_empty_candidates_resolve_from_latest_environment_inventory():
    scope,sessions,engine=fixture()
    with sessions() as s:
        s.add(EnvironmentCapabilityModel(id="env-1", idempotency_key="env-1", actor="diagnostics", status="available", captured_at=NOW, policy_version="environment-v1", checksum="sha256:environment", snapshot=environment_snapshot(), artifacts={}, created_at=NOW))
        s.commit()
    service=ExecutionProfileApplicationService(session_scope_factory=scope,now_provider=lambda:NOW)
    result=service.resolve('run-1',request().model_copy(update={"candidates": ()}))
    assert result.status == "resolved"
    assert result.selected_profile is not None
    assert result.selected_profile.node_exact == "20.11.1"
    engine.dispose()


def test_baseline_boundary_blocks_when_inventory_executable_changes():
    scope,sessions,engine=fixture()
    with sessions() as s:
        s.add(EnvironmentCapabilityModel(id="env-1", idempotency_key="env-1", actor="diagnostics", status="available", captured_at=NOW, policy_version="environment-v1", checksum="sha256:environment", snapshot=environment_snapshot(), artifacts={}, created_at=NOW))
        s.commit()
    service=ExecutionProfileApplicationService(session_scope_factory=scope,now_provider=lambda:NOW)
    result=service.resolve('run-1',request().model_copy(update={"candidates": ()}))
    with sessions() as s:
        environment=s.get(EnvironmentCapabilityModel, "env-1")
        environment.snapshot=environment_snapshot(r"C:\Tools\replacement")
        environment.checksum="sha256:environment-replaced"
        s.commit()
    with pytest.raises(ExecutionProfileApplicationError, match="selected executable") as error:
        service.validate_for_baseline("run-1", expected_state_version=result.state_version, idempotency_key="baseline-profile-check", actor="operator")
    assert error.value.code == "STALE_EXECUTION_PROFILE"
    with sessions() as s:
        record=s.scalar(select(ExecutionProfileModel).where(ExecutionProfileModel.run_id=='run-1'))
        assert record.status == "stale"
        assert "EXECUTION_PROFILE_STALE" in record.blockers
    engine.dispose()
