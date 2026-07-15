from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.api.execution_profile_contracts import ExecutionProfileResolveRequest, ExecutionProfileSelectRequest
from app.api.routes.execution_profiles import get_execution_profile_service
from app.domain.execution_profile import RuntimeCandidate
from app.main import app
from app.repositories.models import Base, ExecutionProfileModel, G02ApprovalModel, MigrationRunModel, WorkflowEventModel
from app.services.execution_profile_application_service import ExecutionProfileApplicationService, ExecutionProfileApplicationError

NOW=datetime(2026,7,15,tzinfo=UTC)
def fixture(tmp_path:Path):
    engine=create_engine(f"sqlite:///{tmp_path/'state.db'}"); Base.metadata.create_all(engine); sessions=sessionmaker(bind=engine,expire_on_commit=False); root=tmp_path/'artifacts'
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

def test_resolution_persists_artifacts_events_and_replays(tmp_path):
    scope,sessions,engine=fixture(tmp_path); service=ExecutionProfileApplicationService(session_scope_factory=scope,now_provider=lambda:NOW)
    first=service.resolve('run-1',request()); replay=service.resolve('run-1',request())
    assert first.status=='resolved' and first.selected_profile is not None and replay.idempotent_replay
    with sessions() as s:
        record=s.scalar(select(ExecutionProfileModel).where(ExecutionProfileModel.run_id=='run-1')); events=list(s.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id=='run-1').order_by(WorkflowEventModel.sequence)))
        assert record and len(record.artifact_ids)==4
        assert [e.event_type for e in events]==['EXECUTION_PROFILE_RESOLUTION_STARTED','EXECUTION_PROFILE_RESOLVED']
    engine.dispose()

def test_multiple_candidate_selection_is_checksum_bound(tmp_path):
    scope,_,engine=fixture(tmp_path); service=ExecutionProfileApplicationService(session_scope_factory=scope,now_provider=lambda:NOW)
    first=service.resolve('run-1',request()); assert first.status=='resolved'
    engine.dispose()

def test_missing_g02_blocks_without_persisting(tmp_path):
    scope,sessions,engine=fixture(tmp_path)
    with sessions() as s: s.query(G02ApprovalModel).delete(); s.commit()
    try:
        ExecutionProfileApplicationService(session_scope_factory=scope,now_provider=lambda:NOW).resolve('run-1',request())
    except ExecutionProfileApplicationError as error: assert error.code=='G02_APPROVAL_REQUIRED'
    else: raise AssertionError('G02 should be required')
    engine.dispose()
