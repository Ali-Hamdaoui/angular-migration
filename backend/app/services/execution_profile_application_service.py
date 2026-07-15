"""Durable application service for S1-F09 execution-profile resolution."""
from __future__ import annotations
import hashlib, json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from sqlalchemy import select
from app.api.execution_profile_contracts import ExecutionProfileResponse
from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType, WorkflowEventType
from app.domain.execution_profile import RuntimeCandidate, RuntimeResolutionRequest, SourceRuntimeResolver
from app.repositories.models import ArtifactMetadataModel, EnvironmentCapabilityModel, ExecutionProfileModel, G02ApprovalModel, MigrationRunModel, WorkflowEventModel
from app.repositories.session import session_scope
from app.state.transition_service import StateTransitionService, TransitionRequest, StaleStateVersionError

class ExecutionProfileApplicationError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422):
        super().__init__(message); self.code=code; self.message=message; self.status_code=status_code

class ExecutionProfileApplicationService:
    POLICY_VERSION = "angular-source-runtime-v1"
    def __init__(self, *, session_scope_factory=session_scope, resolver=None, now_provider=None):
        self._scope=session_scope_factory; self._resolver=resolver or SourceRuntimeResolver(); self._now=now_provider or (lambda: datetime.now(UTC))

    def list(self, run_id: str) -> ExecutionProfileResponse | None:
        with self._scope() as session:
            record=session.scalar(select(ExecutionProfileModel).where(ExecutionProfileModel.run_id==run_id).order_by(ExecutionProfileModel.created_at.desc()))
            return self._response(record) if record else None

    def resolve(self, run_id: str, request) -> ExecutionProfileResponse:
        now=self._now()
        with self._scope() as session:
            run=self._run(session,run_id)
            inventory_candidates, inventory_checksum = self._inventory_candidates(session)
            candidates = tuple(request.candidates) or inventory_candidates
            request_payload = request.model_dump(mode="json")
            request_payload["inventory_checksum"] = inventory_checksum
            request_checksum=self._checksum(request_payload)
            existing=session.scalar(select(ExecutionProfileModel).where(ExecutionProfileModel.run_id==run_id,ExecutionProfileModel.idempotency_key==request.idempotency_key))
            if existing:
                if existing.request_checksum != request_checksum: raise ExecutionProfileApplicationError("IDEMPOTENCY_PAYLOAD_MISMATCH","The idempotency key was already used with a different payload.",409)
                return self._response(existing, replay=True)
            self._require_g02(session,run_id)
            if run.state_version != request.expected_state_version: raise ExecutionProfileApplicationError("STALE_STATE_VERSION","The run state version is stale.",409)
            resolution=self._resolver.resolve(RuntimeResolutionRequest(source_angular_exact=request.source_angular_exact,source_typescript_exact=request.source_typescript_exact,source_rxjs_exact=request.source_rxjs_exact,candidates=candidates,validated_at=request.validated_at))
            artifact_ids=self._write_artifacts(session,run,resolution,request_checksum,now)
            started=StateTransitionService(session).apply_transition(TransitionRequest(run_id=run_id,expected_state_version=run.state_version,idempotency_key=request.idempotency_key+":started",event_type=WorkflowEventType.EXECUTION_PROFILE_RESOLUTION_STARTED,actor=request.actor,reason="execution profile resolution started",occurred_at=now,payload={"source_angular_exact":request.source_angular_exact}))
            event_type=WorkflowEventType.EXECUTION_PROFILE_RESOLVED if resolution.status != "blocked" else WorkflowEventType.EXECUTION_PROFILE_BLOCKED
            finished=StateTransitionService(session).apply_transition(TransitionRequest(run_id=run_id,expected_state_version=started.next_state_version,idempotency_key=request.idempotency_key,event_type=event_type,actor=request.actor,reason="execution profile resolution completed",occurred_at=now,payload={"status":resolution.status,"policy_version":resolution.policy_version}))
            selected=resolution.selected_profile.model_dump(mode="json") if resolution.selected_profile else None
            record=ExecutionProfileModel(id=f"profile-resolution-{uuid4().hex[:12]}",run_id=run_id,idempotency_key=request.idempotency_key,request_checksum=request_checksum,policy_version=resolution.policy_version,status=resolution.status,source_angular_exact=request.source_angular_exact,selected_profile_id=resolution.selected_profile.profile_id if resolution.selected_profile else None,selected_checksum=resolution.selected_profile.checksum if resolution.selected_profile else None,profiles=[p.model_dump(mode="json") for p in resolution.compatible_profiles],blockers=list(resolution.blockers),guidance=list(resolution.guidance),artifact_ids=artifact_ids,state_version=finished.next_state_version,event_sequence=finished.event_sequence,created_at=now,updated_at=now)
            session.add(record); session.flush(); return self._response(record)

    def select(self, run_id: str, request) -> ExecutionProfileResponse:
        now=self._now()
        with self._scope() as session:
            run=self._run(session,run_id); record=session.scalar(select(ExecutionProfileModel).where(ExecutionProfileModel.run_id==run_id).order_by(ExecutionProfileModel.created_at.desc()))
            if record is None: raise ExecutionProfileApplicationError("PROFILE_RESOLUTION_REQUIRED","Resolve execution profiles before selecting one.",409)
            existing=session.scalar(select(WorkflowEventModel).where(WorkflowEventModel.run_id==run_id,WorkflowEventModel.idempotency_key==request.idempotency_key))
            if existing: return self._response(record,replay=True)
            if run.state_version != request.expected_state_version: raise ExecutionProfileApplicationError("STALE_STATE_VERSION","The run state version is stale.",409)
            if record.status != "selection_required": raise ExecutionProfileApplicationError("PROFILE_SELECTION_NOT_REQUIRED","Explicit selection is not required for this resolution.",409)
            profile=next((p for p in record.profiles if p.get("profile_id")==request.profile_id and p.get("checksum")==request.checksum),None)
            if profile is None: raise ExecutionProfileApplicationError("PROFILE_CHECKSUM_MISMATCH","The selected profile is not an eligible checksum-bound candidate.",409)
            transition=StateTransitionService(session).apply_transition(TransitionRequest(run_id=run_id,expected_state_version=run.state_version,idempotency_key=request.idempotency_key,event_type=WorkflowEventType.EXECUTION_PROFILE_SELECTED,actor=request.actor,reason="source runtime profile selected",occurred_at=now,payload={"profile_id":request.profile_id,"checksum":request.checksum}))
            record.status="selected"; record.selected_profile_id=request.profile_id; record.selected_checksum=request.checksum; record.state_version=transition.next_state_version; record.event_sequence=transition.event_sequence; record.updated_at=now; session.flush(); return self._response(record)

    def validate_for_baseline(self, run_id: str, *, expected_state_version: int, idempotency_key: str, actor: str):
        """Fail closed immediately before a baseline command or sandbox starts."""
        now = self._now()
        with self._scope() as session:
            run = self._run(session, run_id)
            record = session.scalar(select(ExecutionProfileModel).where(ExecutionProfileModel.run_id == run_id).order_by(ExecutionProfileModel.created_at.desc()))
            if record is None or record.status not in {"resolved", "selected"} or not record.selected_profile_id:
                raise ExecutionProfileApplicationError("EXECUTION_PROFILE_REQUIRED", "A selected execution profile is required before baseline start.", 409)
            if run.state_version != expected_state_version:
                raise ExecutionProfileApplicationError("STALE_STATE_VERSION", "The run state version is stale.", 409)
            candidates, _ = self._inventory_candidates(session)
            selected = next((profile for profile in record.profiles if profile.get("profile_id") == record.selected_profile_id and profile.get("checksum") == record.selected_checksum), None)
            if selected is None or record.policy_version != self.POLICY_VERSION or not any(self._candidate_matches_profile(candidate, selected) for candidate in candidates):
                transition = StateTransitionService(session).apply_transition(TransitionRequest(run_id=run_id, expected_state_version=run.state_version, idempotency_key=idempotency_key, event_type=WorkflowEventType.EXECUTION_PROFILE_BLOCKED, actor=actor, reason="selected execution profile is stale at baseline boundary", occurred_at=now, payload={"profile_id": record.selected_profile_id, "checksum": record.selected_checksum}))
                record.status = "stale"; record.blockers = list(dict.fromkeys([*(record.blockers or []), "EXECUTION_PROFILE_STALE"])); record.state_version = transition.next_state_version; record.event_sequence = transition.event_sequence; record.updated_at = now; session.flush(); session.commit()
                raise ExecutionProfileApplicationError("STALE_EXECUTION_PROFILE", "The selected executable or compatibility policy changed; resolve the execution profile again.", 409)
            from app.domain.execution_profile import ExecutionProfile
            return ExecutionProfile.model_validate(selected)

    @staticmethod
    def _candidate_matches_profile(candidate, profile: dict) -> bool:
        return all(candidate_value == profile_value for candidate_value, profile_value in ((candidate.node_executable, profile.get("node_executable")), (candidate.node_exact, profile.get("node_exact")), (candidate.npm_executable, profile.get("package_manager_executable")), (candidate.npm_exact, profile.get("package_manager_exact")), (candidate.npx_executable, profile.get("npx_executable")), (candidate.npx_exact, profile.get("npx_exact"))))

    @staticmethod
    def _inventory_candidates(session) -> tuple[tuple[RuntimeCandidate, ...], str | None]:
        environment = session.scalar(select(EnvironmentCapabilityModel).order_by(EnvironmentCapabilityModel.created_at.desc()))
        if environment is None:
            return (), None
        snapshot = environment.snapshot
        runtimes = {item["name"]: item for item in snapshot.get("runtimes", [])}
        required = [runtimes.get(name) for name in ("node", "npm", "npx")]
        if snapshot.get("status") == "blocked" or any(not item or item.get("status") != "available" or not item.get("executable") or not item.get("version") for item in required):
            return (), environment.checksum
        roots = {str(item.get("installation_root", "")).lower() for item in required}
        if len(roots) != 1:
            return (), environment.checksum
        network = snapshot.get("network", {})
        candidate = RuntimeCandidate(profile_id=f"environment-{environment.id}", operating_system="windows", architecture="amd64", node_executable=required[0]["executable"], node_exact=required[0]["version"], npm_executable=required[1]["executable"], npm_exact=required[1]["version"], npx_executable=required[2]["executable"], npx_exact=required[2]["version"], registry_configured=bool(network.get("registry_configured")), proxy_configured=bool(network.get("proxy_configured")), certificate_valid=bool(network.get("strict_ssl")), environment_allowlist_valid=bool(network.get("credentials_redacted", True)), cache_policy_valid=True, network_policy="approved-registries-only", available=True)
        return (candidate,), environment.checksum

    def _require_g02(self,session,run_id):
        g02=session.scalar(select(G02ApprovalModel).where(G02ApprovalModel.run_id==run_id).order_by(G02ApprovalModel.created_at.desc()))
        if g02 is None or g02.status not in {"approved","approved_with_comment"}: raise ExecutionProfileApplicationError("G02_APPROVAL_REQUIRED","An approved G02 source-integrity boundary is required.",409)

    @staticmethod
    def _run(session,run_id):
        run=session.get(MigrationRunModel,run_id)
        if run is None: raise ExecutionProfileApplicationError("RUN_NOT_FOUND","Migration run does not exist.",404)
        return run

    def _write_artifacts(self,session,run,resolution,request_checksum,now):
        root=Path(run.artifact_root or "").resolve(); store=LocalFilesystemArtifactStore(root,fixed_run_root=root); store.ensure_run_layout(run.id); ids=[]
        payload={"status":resolution.status,"policy_version":resolution.policy_version,"compatible_profiles":[p.model_dump(mode="json") for p in resolution.compatible_profiles],"blockers":list(resolution.blockers),"guidance":list(resolution.guidance)}
        for name,data in (("source_runtime_resolution.json",payload),("runtime_validation_report.json",{"status":resolution.status,"blockers":list(resolution.blockers),"policy_version":resolution.policy_version}),("runtime_environment_redacted.json",{"redacted":True,"policy_version":resolution.policy_version})): 
            stored=store.write_text_artifact(run.id,"global/execution-profile/"+name,json.dumps(data,sort_keys=True,indent=2,default=str),ArtifactType.JSON,created_by="execution-profile-service",created_at=now,input_hashes={"request":request_checksum},policy_version=resolution.policy_version); ids.append(stored.ref.artifact_id); session.add(ArtifactMetadataModel(id="metadata-"+stored.ref.artifact_id,run_id=run.id,stage_id=None,artifact_type=stored.ref.artifact_type.value,relative_path=stored.ref.relative_path,checksum=stored.ref.checksum,created_at=now))
        if resolution.selected_profile:
            stored=store.write_text_artifact(run.id,"global/execution-profile/execution_profile.json",json.dumps(resolution.selected_profile.model_dump(mode="json"),sort_keys=True,indent=2,default=str),ArtifactType.JSON,created_by="execution-profile-service",created_at=now,input_hashes={"request":request_checksum},policy_version=resolution.policy_version); ids.append(stored.ref.artifact_id); session.add(ArtifactMetadataModel(id="metadata-"+stored.ref.artifact_id,run_id=run.id,stage_id=None,artifact_type=stored.ref.artifact_type.value,relative_path=stored.ref.relative_path,checksum=stored.ref.checksum,created_at=now))
        return ids

    @staticmethod
    def _checksum(payload): return "sha256:"+hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
    @staticmethod
    def _response(record,replay=False):
        from app.domain.execution_profile import ExecutionProfile
        profiles=tuple(ExecutionProfile.model_validate(p) for p in record.profiles); selected=next((p for p in profiles if p.profile_id==record.selected_profile_id),None)
        return ExecutionProfileResponse(run_id=record.run_id,status=record.status,policy_version=record.policy_version,source_angular_exact=record.source_angular_exact,compatible_profiles=profiles,selected_profile=selected,blockers=tuple(record.blockers or ()),guidance=tuple(record.guidance or ()),artifact_ids=tuple(record.artifact_ids or ()),state_version=record.state_version,event_sequence=record.event_sequence,idempotent_replay=replay)
