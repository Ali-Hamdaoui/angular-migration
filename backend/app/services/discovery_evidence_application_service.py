import hashlib,json
from datetime import UTC,datetime
from pathlib import Path
from uuid import uuid4
from sqlalchemy import select
from app.api.discovery_contracts import DiscoveryEvidenceResponse
from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType,WorkflowEventType
from app.repositories.models import ArtifactMetadataModel,MigrationRunModel
from app.repositories.discovery_models import DiscoveryEvidenceModel
from app.repositories.session import session_scope
from app.services.discovery_service import DiscoveryService
from app.state.transition_service import StateTransitionService,TransitionRequest
class DiscoveryEvidenceError(ValueError):
 def __init__(self,code,message,status_code=422): self.code,self.message,self.status_code=code,message,status_code;super().__init__(message)
class DiscoveryEvidenceApplicationService:
 def __init__(self,*,session_scope_factory=session_scope,coordinator=None,now_provider=None): self.scope=session_scope_factory;self.coordinator=coordinator or DiscoveryService();self.now=now_provider or (lambda:datetime.now(UTC))
 def capture(self,run_id,request):
  checksum='sha256:'+hashlib.sha256(json.dumps(request.model_dump(mode='json'),sort_keys=True,separators=(',',':')).encode()).hexdigest()
  with self.scope() as s:
   old=s.scalar(select(DiscoveryEvidenceModel).where(DiscoveryEvidenceModel.run_id==run_id,DiscoveryEvidenceModel.idempotency_key==request.idempotency_key))
   if old:
    if old.request_checksum!=checksum: raise DiscoveryEvidenceError('IDEMPOTENCY_KEY_REUSED','Idempotency key was used with a different payload.',409)
    return self.dto(old,True)
   run=s.get(MigrationRunModel,run_id)
   if not run: raise DiscoveryEvidenceError('RUN_NOT_FOUND','Migration run does not exist.',404)
   if run.state_version!=request.expected_state_version: raise DiscoveryEvidenceError('STALE_STATE_VERSION','The run state version is stale.',409)
   meta={x.id.removeprefix('metadata-'):x for x in s.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id==run_id)).all()}
   if any(x not in meta for x in request.prerequisite_artifact_ids): raise DiscoveryEvidenceError('PREREQUISITE_ARTIFACT_NOT_FOUND','A prerequisite artifact is not registered.',409)
   if any(not request.prerequisite_artifact_checksums.get(x) for x in request.prerequisite_artifact_ids): raise DiscoveryEvidenceError('PREREQUISITE_ARTIFACT_CHECKSUM_REQUIRED','Every prerequisite artifact requires an expected checksum.',409)
   if any(meta[x].checksum!=request.prerequisite_artifact_checksums[x] for x in request.prerequisite_artifact_ids): raise DiscoveryEvidenceError('PREREQUISITE_ARTIFACT_CHECKSUM_MISMATCH','A prerequisite checksum does not match.',409)
   self.transition(s,run,request,WorkflowEventType.DISCOVERY_STARTED,'discovery started',{})
   workspace=Path((run.workspace_aliases or {}).get('SOURCE_SNAPSHOT',''))
  try: results,drafts=self.coordinator.discover(workspace)
  except Exception as e: return self.block(run_id,request,checksum,str(e))
  with self.scope() as s:
   run=s.get(MigrationRunModel,run_id); store=LocalFilesystemArtifactStore(Path(run.artifact_root),fixed_run_root=Path(run.artifact_root)); ids=[];checks={}
   for draft in drafts:
    a=store.write_text_artifact(run_id,'02_analysis/'+draft.name,draft.content,ArtifactType.JSON,created_by='discovery-evidence',created_at=self.now(),policy_version='discovery-v1');ids.append(a.ref.artifact_id);checks[a.ref.artifact_id]=a.ref.checksum;s.add(ArtifactMetadataModel(id='metadata-'+a.ref.artifact_id,run_id=run_id,stage_id=None,artifact_type=a.ref.artifact_type.value,relative_path=a.ref.relative_path,checksum=a.ref.checksum,created_at=a.ref.created_at))
    self.transition(s,run,request,WorkflowEventType.SCANNER_COMPLETED,'scanner completed',{'scanner':draft.name})
   t=self.transition(s,run,request,WorkflowEventType.DISCOVERY_COMPLETED,'discovery completed',{'artifact_count':len(ids)})
   row=DiscoveryEvidenceModel(id='discovery-'+uuid4().hex[:12],run_id=run_id,idempotency_key=request.idempotency_key,request_checksum=checksum,actor=request.actor,status='completed',scanner_results=[x.model_dump(mode='json') for x in results],artifact_ids=ids,artifact_checksums=checks,prerequisite_artifact_ids=request.prerequisite_artifact_ids,error_code=None,state_version=t.next_state_version,event_sequence=t.event_sequence,created_at=self.now(),updated_at=self.now());s.add(row);s.flush();return self.dto(row)
 def get(self,run_id):
  with self.scope() as s:
   row=s.scalar(select(DiscoveryEvidenceModel).where(DiscoveryEvidenceModel.run_id==run_id).order_by(DiscoveryEvidenceModel.created_at.desc()));return self.dto(row) if row else None
 def block(self,run_id,request,checksum,message): raise DiscoveryEvidenceError('DISCOVERY_DEPENDENCY_FAILED',message,422)
 def transition(self,s,run,r,event,reason,payload): return StateTransitionService(s).apply_transition(TransitionRequest(run_id=run.id,expected_state_version=run.state_version,idempotency_key=r.idempotency_key+':'+event.value+':'+str(payload.get('scanner','')),event_type=event,actor=r.actor,reason=reason,occurred_at=self.now(),payload=payload))
 def dto(self,row,replay=False): return DiscoveryEvidenceResponse(run_id=row.run_id,discovery_id=row.id,status=row.status,scanner_results=row.scanner_results,artifact_ids=row.artifact_ids,artifact_checksums=row.artifact_checksums,prerequisite_artifact_ids=row.prerequisite_artifact_ids,error_code=row.error_code,state_version=row.state_version,event_sequence=row.event_sequence,idempotent_replay=replay)
