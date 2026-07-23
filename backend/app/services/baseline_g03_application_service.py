from __future__ import annotations
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from sqlalchemy import select
from app.api.baseline_g03_contracts import BaselineAssessmentResponse
from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.baseline_qualification import BaselineEvidence, BaselinePolicyService, G03ApprovalPackageBuilder, G03ApprovalService, G03Decision, KnownFailurePolicy
from app.domain.contracts import ArtifactType, RunStatus, WorkflowEventType
from app.repositories.models import ArtifactMetadataModel, BaselineAssessmentModel, BaselineParityEvidenceModel, BaselineQualificationModel, BaselineValidationModel, CommandExecutionModel, ExecutionProfileModel, MigrationRunModel
from app.repositories.baseline_g03_models import G03ApprovalModel
from app.repositories.session import session_scope
from app.state.transition_service import StateTransitionService, TransitionRequest
class BaselineG03ApplicationError(ValueError):
    def __init__(self, code, message, status_code=422): self.code,self.message,self.status_code=code,message,status_code
class BaselineG03ApplicationService:
    def __init__(self, *, scope=session_scope, now_provider=None): self.scope=scope; self.now=now_provider or (lambda:datetime.now(UTC))
    def get(self, run_id):
        with self.scope() as s:
            row=s.scalar(select(BaselineAssessmentModel).where(BaselineAssessmentModel.run_id==run_id).order_by(BaselineAssessmentModel.created_at.desc()))
            approval = s.scalar(select(G03ApprovalModel).where(G03ApprovalModel.run_id == run_id).order_by(G03ApprovalModel.updated_at.desc()))
            return self.dto(row, g03_decision=approval.decision if approval else None) if row else None
    def qualify(self, run_id, request):
        with self.scope() as s:
            run=s.get(MigrationRunModel,run_id)
            if not run: raise BaselineG03ApplicationError("RUN_NOT_FOUND","Migration run does not exist.",404)
            row=s.scalar(select(BaselineAssessmentModel).where(BaselineAssessmentModel.run_id==run_id,BaselineAssessmentModel.idempotency_key==request.idempotency_key))
            if row: return self.dto(row,True)
            self.version(run,request.expected_state_version)
            baseline=s.scalar(select(BaselineQualificationModel).where(BaselineQualificationModel.run_id==run_id).order_by(BaselineQualificationModel.created_at.desc()))
            if not baseline: raise BaselineG03ApplicationError("BASELINE_EVIDENCE_REQUIRED","Baseline prequalification evidence is required.",409)
            parity=s.scalar(select(BaselineParityEvidenceModel).where(BaselineParityEvidenceModel.run_id==run_id).order_by(BaselineParityEvidenceModel.created_at.desc()))
            vals=list(s.scalars(select(BaselineValidationModel).where(BaselineValidationModel.run_id==run_id)))
            profile=s.scalar(select(ExecutionProfileModel).where(ExecutionProfileModel.run_id==run_id).order_by(ExecutionProfileModel.updated_at.desc()))
            installation = s.scalar(select(CommandExecutionModel).where(CommandExecutionModel.run_id == run_id, CommandExecutionModel.command_id == "npm-ci-bootstrap").order_by(CommandExecutionModel.finished_at.desc()))
            commands = list(s.scalars(select(CommandExecutionModel).where(CommandExecutionModel.run_id == run_id).order_by(CommandExecutionModel.requested_at, CommandExecutionModel.id)))
            evidence_ids = list(dict.fromkeys([*(baseline.artifact_ids or []), *(item for validation in vals for item in (validation.artifact_ids or [])), *(request.prerequisite_artifact_ids or []), *(profile.artifact_ids or [] if profile else [])]))
            registered = {row.id.removeprefix("metadata-"): row for row in s.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run_id)).all()}
            missing = [artifact_id for artifact_id in evidence_ids if artifact_id not in registered]
            if missing:
                raise BaselineG03ApplicationError("BASELINE_EVIDENCE_ARTIFACT_MISSING", f"Registered baseline evidence is missing: {', '.join(missing)}", 409)
            evidence_artifacts = tuple({"artifact_id": artifact_id, "checksum": registered[artifact_id].checksum} for artifact_id in evidence_ids)
            runtime_status = "selected" if profile and profile.selected_profile_id and profile.selected_checksum else "not_proven"
            install_status = self.installation_status(installation)
            evidence=BaselineEvidence(runtime={"status":runtime_status},install={"status":install_status},validations=tuple({"kind":v.kind,"status":self.validation_status(v)} for v in vals),parity={"failures":parity.failures if parity else [],"confidence":parity.confidence if parity else {}},source_integrity={"verified":True},evidence_artifacts=evidence_artifacts,sandbox_fingerprint=baseline.sandbox_fingerprint or "",execution_profile_checksum=profile.selected_checksum if profile and profile.selected_checksum else "",state_version=run.state_version)
            q=BaselinePolicyService().evaluate(evidence,policy=KnownFailurePolicy(request.policy),company_policy_allows_known_failures=request.company_policy_allows_known_failures)
            package=G03ApprovalPackageBuilder().build(run_id=run_id,actor=request.actor,evidence=evidence,qualification=q)
            validation_statuses = {validation.kind: validation.status for validation in vals}
            generated_output_ids = [artifact_id for artifact_id, item in registered.items() if item.relative_path.endswith("generated_output_inventory.json")]
            data={"run_id":run_id,"generated_at":self.now().isoformat(),"status":q.status.value,"policy":q.policy.value,"policy_version":q.policy_version,"blockers":list(q.blockers),"warnings":list(q.warnings),"known_failures":list(q.known_failures),"evidence_confidence":dict(q.evidence_confidence),"evidence_set_checksum":package.evidence_set_checksum,"sandbox_fingerprint":package.sandbox_fingerprint,"baseline_sandbox_id":baseline.sandbox_path,"source_snapshot_id":baseline.snapshot_id,"execution_profile_id":profile.selected_profile_id if profile else None,"execution_profile_checksum":package.execution_profile_checksum,"package_checksum":package.package_checksum,"installation_status":installation.status if installation else "NOT_RUN","build_status":validation_statuses.get("build", "NOT_CONFIGURED"),"test_status":validation_statuses.get("test", "NOT_CONFIGURED"),"lint_status":validation_statuses.get("lint", "NOT_CONFIGURED"),"workspace_fingerprint_before_commands":installation.start_fingerprint if installation else None,"workspace_fingerprint_after_commands":installation.end_fingerprint if installation else None,"package_json_mutation_status":"CHANGED" if installation and "PACKAGE_JSON_CHANGED_AFTER_INSTALL" in (installation.blockers or []) else "UNCHANGED","lockfile_mutation_status":"CHANGED" if installation and "PACKAGE_LOCK_CHANGED_AFTER_INSTALL" in (installation.blockers or []) else "UNCHANGED","command_ids":[command.command_id for command in commands],"execution_artifact_ids":list(dict.fromkeys(item for command in commands for item in (command.artifact_ids or []))),"generated_output_inventory_artifact_ids":generated_output_ids,"evidence_artifact_ids":list(evidence_ids),"overall_baseline_decision":q.status.value}
            ids=[]; checksums={}
            store=LocalFilesystemArtifactStore(Path(run.artifact_root),fixed_run_root=Path(run.artifact_root))
            evidence_index = {"run_id":run_id,"generated_at":self.now().isoformat(),"source_snapshot_id":baseline.snapshot_id,"baseline_sandbox_id":baseline.sandbox_path,"execution_profile_id":profile.selected_profile_id if profile else None,"evidence_set_checksum":package.evidence_set_checksum,"artifacts":[{"artifact_id":item["artifact_id"],"checksum":item["checksum"]} for item in evidence_artifacts]}
            data["evidence_artifacts"] = evidence_index["artifacts"]
            for name,payload in (("baseline_summary.json",data),("baseline_qualification.json",data),("baseline_assurance_status.json",{"status":q.status.value}),("g03_evidence_index.json",evidence_index),("sprint1_evidence_manifest.json",data)):
                a=store.write_text_artifact(run_id,"01_baseline/"+name,json.dumps(payload,sort_keys=True),ArtifactType.JSON,created_by="baseline-g03",policy_version=q.policy_version)
                ids.append(a.ref.artifact_id); checksums[a.ref.artifact_id]=a.ref.checksum
                s.add(ArtifactMetadataModel(id="metadata-"+a.ref.artifact_id,run_id=run_id,stage_id=None,artifact_type=a.ref.artifact_type.value,relative_path=a.ref.relative_path,checksum=a.ref.checksum,schema_version=1,created_at=a.ref.created_at))
            event=StateTransitionService(s).apply_transition(TransitionRequest(run_id=run_id,idempotency_key=request.idempotency_key+":qualification",expected_state_version=run.state_version,event_type=WorkflowEventType.BASELINE_QUALIFIED if not q.blockers else WorkflowEventType.BASELINE_BLOCKED,next_run_status=RunStatus.BASELINE_QUALIFIED if not q.blockers else None,actor=request.actor,reason="baseline qualification recorded",occurred_at=self.now(),payload={"qualification_status":q.status.value,"package_checksum":package.package_checksum}))
            package_event=StateTransitionService(s).apply_transition(TransitionRequest(run_id=run_id,idempotency_key=request.idempotency_key+":g03-created",expected_state_version=event.next_state_version,event_type=WorkflowEventType.G03_CREATED,actor=request.actor,reason="G03 approval package created",occurred_at=self.now(),payload={"package_checksum":package.package_checksum,"evidence_set_checksum":package.evidence_set_checksum}))
            row=BaselineAssessmentModel(id="assessment-"+uuid4().hex[:12],run_id=run_id,idempotency_key=request.idempotency_key,actor=request.actor,status=q.status.value,policy=q.policy.value,policy_version=q.policy_version,blockers=list(q.blockers),warnings=list(q.warnings),known_failures=list(q.known_failures),evidence_confidence=dict(q.evidence_confidence),evidence_set_checksum=package.evidence_set_checksum,sandbox_fingerprint=package.sandbox_fingerprint,execution_profile_checksum=package.execution_profile_checksum,source_artifact_ids=[],artifact_ids=ids,artifact_checksums=checksums,package_checksum=package.package_checksum,state_version=package_event.next_state_version,event_sequence=package_event.event_sequence,created_at=self.now(),updated_at=self.now())
            s.add(row); s.flush(); return self.dto(row)
    def decide(self,run_id,request):
        with self.scope() as s:
            run=s.get(MigrationRunModel,run_id); row=s.scalar(select(BaselineAssessmentModel).where(BaselineAssessmentModel.run_id==run_id).order_by(BaselineAssessmentModel.created_at.desc()))
            if not run: raise BaselineG03ApplicationError("RUN_NOT_FOUND","Migration run does not exist.",404)
            if not row: raise BaselineG03ApplicationError("G03_PACKAGE_REQUIRED","Qualify the baseline before deciding G03.",409)
            existing = s.scalar(select(G03ApprovalModel).where(G03ApprovalModel.run_id == run_id, G03ApprovalModel.idempotency_key == request.idempotency_key))
            if existing:
                return self.dto(row, True, existing.decision)
            self.version(run,request.expected_state_version)
            if request.decision==G03Decision.APPROVED.value and row.status not in {"qualified","qualified_with_known_failures"}: raise BaselineG03ApplicationError("BASELINE_BLOCKED","A blocked baseline cannot be approved.",409)
            event=StateTransitionService(s).apply_transition(TransitionRequest(run_id=run_id,idempotency_key=request.idempotency_key,expected_state_version=run.state_version,event_type=WorkflowEventType.G03_APPROVED if request.decision=="approved" else WorkflowEventType.G03_REJECTED,next_run_status=RunStatus.BASELINE_QUALIFIED if request.decision=="approved" else None,actor=request.actor,reason=request.comment or "G03 decision recorded",occurred_at=self.now(),payload={"package_checksum":row.package_checksum,"decision":request.decision}))
            s.add(G03ApprovalModel(id="g03-"+uuid4().hex[:12],run_id=run_id,gate_id="G03",gate_version="g03-v1",idempotency_key=request.idempotency_key,actor=request.actor,status=request.decision,decision=request.decision,package_checksum=row.package_checksum,evidence_set_checksum=row.evidence_set_checksum,qualification_status=row.status,policy_version=row.policy_version,state_version=event.next_state_version,event_sequence=event.event_sequence,sandbox_fingerprint=row.sandbox_fingerprint,execution_profile_checksum=row.execution_profile_checksum,package={"package_checksum":row.package_checksum},artifact_ids=row.artifact_ids,comment=request.comment,created_at=self.now(),updated_at=self.now()))
            row.state_version = event.next_state_version
            row.event_sequence = event.event_sequence
            row.updated_at = self.now()
            s.flush(); return self.dto(row, g03_decision=request.decision)
    def version(self,run,v):
        if run.state_version!=v: raise BaselineG03ApplicationError("STALE_STATE_VERSION","The run state version is stale.",409)
    def validation_status(self,v):
        statuses = [r.get("status") for r in (v.results or [])]
        if statuses and all(status in {"skipped_not_configured", "skipped_not_applicable"} for status in statuses):
            return "not_configured"
        return "passed" if statuses and all(status in {"passed","skipped_not_configured","skipped_not_applicable"} for status in statuses) else v.status
    def installation_status(self, installation):
        if installation is None:
            return "not_run"
        return "passed" if installation.status == "succeeded" else installation.status
    def dto(self,row,replay=False,g03_decision=None):
        return BaselineAssessmentResponse(run_id=row.run_id,assessment_id=row.id,status=row.status,policy=row.policy,policy_version=row.policy_version,blockers=row.blockers or [],warnings=row.warnings or [],known_failures=row.known_failures or [],evidence_confidence=row.evidence_confidence or {},evidence_set_checksum=row.evidence_set_checksum,sandbox_fingerprint=row.sandbox_fingerprint,execution_profile_checksum=row.execution_profile_checksum,package_checksum=row.package_checksum,artifact_ids=row.artifact_ids or [],state_version=row.state_version,event_sequence=row.event_sequence,g03_decision=g03_decision,idempotent_replay=replay)
