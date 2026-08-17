"""Generic, durable transformation replan/recovery authority (V2.1 Section 10)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.repositories.models import (
    CommandExecutionModel,
    CompatibilityCatalogueModel,
    CompatibilityResolutionModel,
    FailureIntelligenceModel,
    G06ApprovalModel,
    MigrationPlanModel,
    MigrationRunModel,
    StageCheckpointModel,
    StageExecutionPlanModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
    TransformationReplanRecoveryModel,
)
from app.repositories.session import session_scope
from app.domain.planning import PlanGenerationRequest
from app.services.planning_application_service import PlanningApplicationService
from app.services.project_capability_service import ProjectCapabilityService
from app.services.stage_preparation_primitives import StageSandboxCopier


class TransformationReplanRecoveryError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class TransformationReplanRecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1, max_length=128)
    stage_id: str = Field(min_length=1, max_length=128)
    failed_execution_id: str = Field(min_length=1, max_length=128)
    failed_execution_result_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    failure_group_key: str = Field(min_length=1, max_length=128)
    root_cause_code: str = Field(min_length=1, max_length=128)
    continuation_state_version: int = Field(ge=1)
    current_plan_id: str = Field(min_length=1, max_length=128)
    current_plan_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    current_stage_plan_id: str = Field(min_length=1, max_length=128)
    current_stage_plan_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    safe_checkpoint_id: str = Field(min_length=1, max_length=128)
    safe_checkpoint_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    safe_checkpoint_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    workspace_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    catalogue_version: str = Field(min_length=1, max_length=128)
    catalogue_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    compatibility_resolution_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=128)


class TransformationReplanRecoveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["pending_approval"]
    run_id: str
    stage_id: str
    recovery_id: str
    new_plan_id: str
    new_plan_checksum: str
    new_stage_plan_id: str
    new_stage_plan_checksum: str
    new_g06_id: str
    old_plan_stale: bool = True
    old_g06_stale: bool = True
    human_approval_required: bool = True
    idempotent_replay: bool = False


class TransformationReplanRecoveryService:
    """Replan only from durable evidence and exact current bindings."""

    def __init__(self, *, session_scope_factory=None, now_provider=None) -> None:
        self._session_scope = session_scope_factory or session_scope
        self._now = now_provider or (lambda: datetime.now(UTC))

    @staticmethod
    def execution_result_checksum(execution: CommandExecutionModel) -> str:
        return _checksum({
            "id": execution.id, "run_id": execution.run_id, "stage_id": execution.stage_id,
            "status": execution.status, "exit_code": execution.exit_code,
            "failure_code": execution.failure_code, "failure_message": execution.failure_message,
            "result_artifact_id": execution.result_artifact_id, "end_fingerprint": execution.end_fingerprint,
        })

    @staticmethod
    def checkpoint_checksum(checkpoint: StageCheckpointModel) -> str:
        return _checksum({
            "id": checkpoint.id, "run_id": checkpoint.run_id, "stage_id": checkpoint.stage_id,
            "kind": checkpoint.kind, "sequence": checkpoint.sequence,
            "workspace_fingerprint": checkpoint.workspace_fingerprint,
            "manifest_checksum": checkpoint.manifest_checksum,
            "safe_for_resume": checkpoint.safe_for_resume, "sealed": checkpoint.sealed,
        })

    @staticmethod
    def compatibility_resolution_checksum(resolution: CompatibilityResolutionModel) -> str:
        return _checksum({
            "id": resolution.id, "run_id": resolution.run_id,
            "catalogue_version": resolution.catalogue_version,
            "catalogue_checksum": resolution.catalogue_checksum,
            "package_checksum": resolution.package_checksum,
            "route": resolution.route, "selected_profile": resolution.selected_profile,
        })

    def recover(self, request: TransformationReplanRecoveryRequest) -> TransformationReplanRecoveryResult:
        request_checksum = _checksum(request.model_dump(mode="json"))
        with self._session_scope() as session:
            existing = session.scalar(select(TransformationReplanRecoveryModel).where(
                TransformationReplanRecoveryModel.run_id == request.run_id,
                TransformationReplanRecoveryModel.idempotency_key == request.idempotency_key,
            ))
            if existing is not None:
                if existing.request_checksum != request_checksum:
                    raise TransformationReplanRecoveryError("IDEMPOTENCY_PAYLOAD_MISMATCH", "Recovery key is bound to a different request")
                replay_payload = dict(existing.result_payload)
                replay_payload["idempotent_replay"] = True
                return TransformationReplanRecoveryResult(**replay_payload)

            run, continuation, plan, stage_plan = self._validate_bindings(session, request)
            self._validate_failure(session, request)
            self._validate_evidence(session, request)
            now = self._now()
            new_version = plan.version + 1
            recovery_hash = hashlib.sha256(f"{request.run_id}:{request.idempotency_key}".encode()).hexdigest()[:20]
            new_plan_id = f"plan-{request.run_id}-replan-{recovery_hash}"
            new_stage_plan_id = f"stage-plan-{request.run_id}-replan-{recovery_hash}"
            new_plan, new_stage_plan = self._deterministic_replan(
                run_id=request.run_id,
                plan=plan,
                stage_plan=stage_plan,
                request=request,
                version=new_version,
                plan_id=new_plan_id,
                stage_plan_id=new_stage_plan_id,
            )
            state_version = run.state_version + 1
            new_g06_id = f"g06-replan-{recovery_hash}"
            artifact_ids = list(plan.artifact_ids or [])
            artifact_checksums = dict(plan.artifact_checksums or {})
            package_checksum = _checksum({
                "plan": new_plan["checksum"], "stage_plan": new_stage_plan["checksum"],
                "artifacts": artifact_checksums,
            })
            artifact_set_checksum = _checksum({"ids": sorted(artifact_ids), "checksums": dict(sorted(artifact_checksums.items()))})

            plan.status = "stale"
            stage_plan.status = "stale"
            old_gate = session.get(G06ApprovalModel, continuation.g06_approval_id)
            if old_gate is not None:
                old_gate.status = "stale"
                old_gate.stale_reason = "superseded by deterministic transformation replan"
                old_gate.updated_at = now
            session.add(MigrationPlanModel(
                id=new_plan_id, run_id=request.run_id, idempotency_key=f"replan:{request.idempotency_key}",
                request_checksum=request_checksum, actor="transformation-recovery", correlation_id=None,
                status="pending_approval", version=new_version, plan=new_plan, checksum=new_plan["checksum"],
                artifact_ids=artifact_ids, artifact_checksums=artifact_checksums, state_version=state_version,
                event_sequence=plan.event_sequence + 1, created_at=now, updated_at=now,
            ))
            session.add(StageExecutionPlanModel(
                id=new_stage_plan_id, run_id=request.run_id, migration_plan_id=new_plan_id,
                stage_id=request.stage_id, idempotency_key=f"replan:{request.idempotency_key}:stage",
                request_checksum=request_checksum, actor="transformation-recovery", correlation_id=None,
                status="pending_approval", version=new_version, stage_plan=new_stage_plan,
                checksum=new_stage_plan["checksum"], artifact_ids=artifact_ids,
                artifact_checksums=artifact_checksums, state_version=state_version,
                event_sequence=stage_plan.event_sequence + 1, created_at=now, updated_at=now,
            ))
            session.add(G06ApprovalModel(
                id=new_g06_id, run_id=request.run_id, gate_id="G06", gate_version="g06-v1",
                idempotency_key=f"gate:replan:{request.idempotency_key}", actor="transformation-recovery",
                status="pending", decision=None, package_checksum=package_checksum,
                artifact_set_checksum=artifact_set_checksum, plan_checksum=new_plan["checksum"],
                stage_plan_checksum=new_stage_plan["checksum"], plan_version=new_version,
                workspace_fingerprint=request.workspace_fingerprint, artifact_ids=artifact_ids,
                comment=None, stale_reason=None, state_version=state_version,
                event_sequence=stage_plan.event_sequence + 1, created_at=now, updated_at=now,
            ))
            continuation.status = "waiting_gate"
            continuation.current_node = "wait_g06"
            continuation.worker_id = None
            continuation.lease_expires_at = None
            continuation.plan_id = new_plan_id
            continuation.plan_checksum = new_plan["checksum"]
            continuation.stage_plan_id = new_stage_plan_id
            continuation.stage_plan_checksum = new_stage_plan["checksum"]
            continuation.g06_approval_id = new_g06_id
            continuation.state_version = state_version
            continuation.updated_at = now
            run.state_version = state_version
            run.updated_at = now
            result = TransformationReplanRecoveryResult(
                status="pending_approval", run_id=request.run_id, stage_id=request.stage_id,
                recovery_id=f"recovery-{recovery_hash}", new_plan_id=new_plan_id,
                new_plan_checksum=new_plan["checksum"], new_stage_plan_id=new_stage_plan_id,
                new_stage_plan_checksum=new_stage_plan["checksum"], new_g06_id=new_g06_id,
            )
            session.add(TransformationReplanRecoveryModel(
                id=result.recovery_id, run_id=request.run_id, stage_id=request.stage_id,
                idempotency_key=request.idempotency_key, request_checksum=request_checksum,
                status=result.status, request_payload=request.model_dump(mode="json"),
                result_payload=result.model_dump(mode="json"), new_plan_id=result.new_plan_id,
                new_plan_checksum=result.new_plan_checksum, new_stage_plan_id=result.new_stage_plan_id,
                new_stage_plan_checksum=result.new_stage_plan_checksum, new_g06_id=result.new_g06_id,
                failure_group_key=request.failure_group_key, root_cause_code=request.root_cause_code,
                safe_checkpoint_id=request.safe_checkpoint_id, workspace_fingerprint=request.workspace_fingerprint,
                created_at=now,
            ))
            session.flush()
            return result

    def _deterministic_replan(
        self,
        *,
        run_id: str,
        plan: MigrationPlanModel,
        stage_plan: StageExecutionPlanModel,
        request: TransformationReplanRecoveryRequest,
        version: int,
        plan_id: str,
        stage_plan_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Rebuild semantic plan content through the normal planner authority."""
        current = stage_plan.stage_plan
        required = (
            "source_family", "source_exact", "target_family", "target_exact",
            "target_cli_exact", "execution_profile_id", "builder",
        )
        if any(not current.get(key) for key in required):
            raise TransformationReplanRecoveryError(
                "REPLAN_INPUT_UNAVAILABLE",
                "The durable stage plan lacks the context required for deterministic replanning",
            )
        capabilities: tuple[dict[str, str], ...] = ()
        snapshot_id = current.get("capability_snapshot_id")
        if snapshot_id:
            snapshot = ProjectCapabilityService().get_snapshot(run_id, snapshot_id)
            capabilities = tuple(item.model_dump(mode="json") for item in snapshot.capabilities)
        capabilities = (*capabilities, {"key": "policy:installed-migration-fallback", "value": "approved"})
        request_payload = PlanGenerationRequest(
            run_id=run_id,
            expected_state_version=1,
            idempotency_key=f"replan:{request.idempotency_key}",
            actor="transformation-recovery",
            source_exact=current["source_exact"],
            source_family=current["source_family"],
            target_family=current["target_family"],
            catalogue_version=plan.plan.get("catalogue_version", request.catalogue_version),
            input_fingerprint=current.get("input_fingerprint", request.safe_checkpoint_fingerprint),
            input_workspace_fingerprint=request.workspace_fingerprint,
            execution_profile_id=current["execution_profile_id"],
            execution_profile_checksum=current.get("execution_profile_checksum", "sha256:" + "0" * 64),
            resolved_scripts=current.get("resolved_scripts") or {"build": "build", "test": "test"},
            project_targets=current.get("project_targets") or {},
            stage_route=(
                (
                    current["source_family"], current["target_family"], request.stage_id,
                    current["target_exact"], current["target_cli_exact"],
                ),
            ),
            target_cli_exact=current["target_cli_exact"],
            builder=current["builder"],
            prerequisite_artifacts=(),
            capability_facts=capabilities,
            capability_snapshot_id=snapshot_id,
            capability_snapshot_checksum=current.get("capability_snapshot_checksum"),
            installed_migration_fallback=True,
        )
        generated = PlanningApplicationService().generate(request_payload)
        new_plan = generated.plan.model_dump(mode="json")
        new_stage_plan = generated.first_stage_plan.model_dump(mode="json")
        new_plan.update({"plan_id": plan_id, "version": version})
        new_stage_plan.update({"stage_plan_id": stage_plan_id, "stage_id": request.stage_id, "plan_version": version})
        new_plan["checksum"] = _checksum({key: value for key, value in new_plan.items() if key != "checksum"})
        new_stage_plan["checksum"] = _checksum({key: value for key, value in new_stage_plan.items() if key != "checksum"})
        return new_plan, new_stage_plan

    def _validate_bindings(self, session, request):
        run = session.get(MigrationRunModel, request.run_id)
        continuation = session.scalar(select(TransformationContinuationModel).where(TransformationContinuationModel.run_id == request.run_id))
        plan = session.get(MigrationPlanModel, request.current_plan_id)
        stage_plan = session.get(StageExecutionPlanModel, request.current_stage_plan_id)
        failed = session.get(CommandExecutionModel, request.failed_execution_id)
        checkpoint = session.get(StageCheckpointModel, request.safe_checkpoint_id)
        binding = session.scalar(select(StageWorkspaceBindingModel).where(
            StageWorkspaceBindingModel.run_id == request.run_id,
            StageWorkspaceBindingModel.stage_id == request.stage_id,
            StageWorkspaceBindingModel.active.is_(True),
        ))
        if run is None or continuation is None:
            raise TransformationReplanRecoveryError("CONTINUATION_NOT_FOUND", "Durable transformation continuation is unavailable")
        if continuation.current_stage_id != request.stage_id or continuation.state_version != request.continuation_state_version:
            raise TransformationReplanRecoveryError("STALE_CONTINUATION", "Transformation continuation state is stale")
        if plan is None or plan.run_id != request.run_id or plan.id != continuation.plan_id or plan.checksum != request.current_plan_checksum or plan.checksum != continuation.plan_checksum:
            raise TransformationReplanRecoveryError("STALE_PLAN", "Current migration plan binding is stale")
        if stage_plan is None or stage_plan.run_id != request.run_id or stage_plan.stage_id != request.stage_id or stage_plan.id != continuation.stage_plan_id or stage_plan.checksum != request.current_stage_plan_checksum or stage_plan.checksum != continuation.stage_plan_checksum:
            raise TransformationReplanRecoveryError("STALE_STAGE_PLAN", "Current stage plan binding is stale")
        if failed is None or failed.run_id != request.run_id or failed.stage_id != request.stage_id or failed.status not in {"failed", "timed_out", "interrupted"} or self.execution_result_checksum(failed) != request.failed_execution_result_checksum:
            raise TransformationReplanRecoveryError("STALE_FAILED_EXECUTION", "Failed execution evidence is stale")
        if checkpoint is None or checkpoint.run_id != request.run_id or checkpoint.stage_id != request.stage_id or not checkpoint.safe_for_resume or checkpoint.workspace_fingerprint != request.safe_checkpoint_fingerprint or self.checkpoint_checksum(checkpoint) != request.safe_checkpoint_checksum:
            raise TransformationReplanRecoveryError("STALE_CHECKPOINT", "Safe checkpoint evidence is stale")
        try:
            checkpoint_current_fingerprint = StageSandboxCopier.fingerprint(Path(checkpoint.workspace_path))
        except (OSError, ValueError):
            raise TransformationReplanRecoveryError("STALE_CHECKPOINT", "Safe checkpoint cannot be fingerprinted")
        if checkpoint_current_fingerprint != checkpoint.workspace_fingerprint:
            raise TransformationReplanRecoveryError("STALE_CHECKPOINT", "Safe checkpoint tree changed")
        if binding is None or binding.workspace_fingerprint != request.workspace_fingerprint:
            raise TransformationReplanRecoveryError("STALE_WORKSPACE", "Active workspace fingerprint is stale")
        try:
            current_fingerprint = StageSandboxCopier.fingerprint(Path(binding.workspace_path))
        except (OSError, ValueError):
            raise TransformationReplanRecoveryError("WORKSPACE_UNAVAILABLE", "Active workspace cannot be fingerprinted")
        if current_fingerprint != request.workspace_fingerprint:
            raise TransformationReplanRecoveryError("STALE_WORKSPACE", "Active workspace changed after failure")
        return run, continuation, plan, stage_plan

    @staticmethod
    def _validate_evidence(session, request) -> None:
        catalogue = session.scalar(select(CompatibilityCatalogueModel).where(CompatibilityCatalogueModel.version == request.catalogue_version))
        if catalogue is None or catalogue.checksum != request.catalogue_checksum:
            raise TransformationReplanRecoveryError("STALE_CATALOGUE", "Compatibility catalogue binding is stale")
        resolution = session.scalar(select(CompatibilityResolutionModel).where(
            CompatibilityResolutionModel.run_id == request.run_id,
            CompatibilityResolutionModel.catalogue_version == request.catalogue_version,
        ).order_by(CompatibilityResolutionModel.created_at.desc()).limit(1))
        if resolution is None or TransformationReplanRecoveryService.compatibility_resolution_checksum(resolution) != request.compatibility_resolution_checksum:
            raise TransformationReplanRecoveryError("STALE_COMPATIBILITY", "Compatibility resolution binding is stale")

    @staticmethod
    def _validate_failure(session, request) -> None:
        intelligence = session.scalar(select(FailureIntelligenceModel).where(FailureIntelligenceModel.run_id == request.run_id).order_by(FailureIntelligenceModel.created_at.desc()).limit(1))
        if intelligence is None:
            raise TransformationReplanRecoveryError("NORMAL_REPAIR_REQUIRED", "Failure intelligence is unavailable")
        group = next((item for item in intelligence.groups if item.get("group_key") == request.failure_group_key), None)
        root = (intelligence.root_causes or {}).get(request.failure_group_key)
        if group is None or root is None or root.get("root_cause_code") != request.root_cause_code or root.get("taxonomy") != "dependency":
            raise TransformationReplanRecoveryError("NORMAL_REPAIR_REQUIRED", "Failure is not a generic deterministic dependency replan")


def _checksum(value: object) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
