"""Synthetic tests for generic transformation replan recovery."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.repositories.models import (
    CommandExecutionModel,
    CompatibilityCatalogueModel,
    CompatibilityResolutionModel,
    FailureIntelligenceModel,
    G06ApprovalModel,
    MigrationPlanModel,
    MigrationRunModel,
    MigrationStageModel,
    StageCheckpointModel,
    StageExecutionPlanModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
    TransformationReplanRecoveryModel,
)
from app.repositories.session import session_scope
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.transformation_replan_recovery_service import (
    TransformationReplanRecoveryError,
    TransformationReplanRecoveryRequest,
    TransformationReplanRecoveryService,
)


NOW = datetime.now(UTC)


def _checksum(value: object) -> str:
    import hashlib
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _seed(tmp_path: Path, *, taxonomy: str = "dependency") -> TransformationReplanRecoveryRequest:
    run_id = f"run-replan-{uuid4().hex[:8]}"
    stage_id = f"stage-replan-{uuid4().hex[:8]}"
    tmp_path.mkdir(parents=True, exist_ok=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "package.json").write_text("{}")
    checkpoint_root = tmp_path / "checkpoint"
    checkpoint_root.mkdir()
    (checkpoint_root / "package.json").write_text("{}")
    fingerprint = StageSandboxCopier.fingerprint(workspace)
    checkpoint_fingerprint = StageSandboxCopier.fingerprint(checkpoint_root)
    catalogue_version = "catalog-v1"
    catalogue_checksum = "sha256:" + "1" * 64
    plan_id = f"plan-current-{run_id}"
    stage_plan_id = f"stage-plan-current-{run_id}"
    plan_payload = {
        "plan_id": plan_id, "version": 1, "source_family": "angular-18.x",
        "source_exact": "18.2.13", "target_family": "angular-19.x",
        "catalogue_version": catalogue_version, "route": [stage_id],
        "repair_policy": {"policy_id": "repair"},
    }
    plan_payload["checksum"] = _checksum(plan_payload)
    stage_payload = {
        "stage_plan_id": stage_plan_id, "plan_version": 1, "stage_id": stage_id,
        "input_fingerprint": fingerprint, "source_family": "angular-18.x",
        "source_exact": "18.2.13", "target_family": "angular-19.x",
        "target_exact": "19.2.0", "target_cli_exact": "19.2.0",
        "execution_profile_id": "profile-replan", "execution_profile_checksum": "sha256:" + "e" * 64,
        "builder": "@angular-devkit/build-angular:application",
        "resolved_scripts": {"build": "build", "test": "test"},
    }
    stage_payload["checksum"] = _checksum(stage_payload)
    execution = CommandExecutionModel(
        id=f"exec-{run_id}", run_id=run_id, stage_id=stage_id, executable="npx",
        arguments=["ng", "update"], status="failed", requested_at=NOW,
        failure_code="DEPENDENCY_PLAN_FAILED", failure_message="synthetic dependency failure",
        result_artifact_id="result-1", end_fingerprint={"workspace": fingerprint},
    )
    checkpoint = StageCheckpointModel(
        id=f"checkpoint-{run_id}", run_id=run_id, stage_id=stage_id, kind="safe_replan",
        sequence=1, workspace_alias="STAGE_WORKSPACE", workspace_path=str(checkpoint_root),
        workspace_fingerprint=checkpoint_fingerprint, manifest_artifact_id="manifest-1",
        manifest_checksum="sha256:" + "2" * 64, safe_for_resume=True, sealed=True,
        state_version=3, created_at=NOW,
    )
    resolution = CompatibilityResolutionModel(
        id=f"resolution-{run_id}", run_id=run_id, idempotency_key=f"resolution-{run_id}",
        request_checksum="sha256:" + "3" * 64, actor="test", status="resolved",
        catalogue_version=catalogue_version, catalogue_checksum=catalogue_checksum,
        registry_snapshot_id="registry-1", registry_snapshot_checksum="sha256:" + "4" * 64,
        registry_snapshot={}, runtime_candidates=[], source_exact="18.2.13",
        source_family="angular-18.x", target_family="angular-19.x", support_level="supported",
        route=[{"source": "angular-18.x", "target": "angular-19.x"}], selected_profile=None,
        source_execution_profile_checksum=None, stage1_profile_checksum=None, blockers=[], warnings=[],
        package={}, package_checksum="sha256:" + "5" * 64, artifact_set_checksum="sha256:" + "6" * 64,
        artifact_ids=[], artifact_checksums={}, workspace_fingerprint=fingerprint,
        state_version=3, event_sequence=1, created_at=NOW, updated_at=NOW,
    )
    group_key = f"fg-{run_id}"
    with session_scope() as session:
        existing_catalogue = session.query(CompatibilityCatalogueModel).filter_by(version=catalogue_version).first()
        if existing_catalogue is not None:
            catalogue_checksum = existing_catalogue.checksum
        session.add(MigrationRunModel(
            id=run_id, status="FAILED", run_phase="transforming", state_version=5,
            created_at=NOW, updated_at=NOW,
        ))
        session.add(MigrationStageModel(
            id=stage_id, run_id=run_id, stage_order=1, status="failed",
            source_version_family="angular-18.x", target_version_family="angular-19.x", created_at=NOW,
        ))
        session.add(execution)
        session.add(checkpoint)
        session.add(StageWorkspaceBindingModel(
            id=f"binding-{run_id}", run_id=run_id, stage_id=stage_id, alias="STAGE_WORKSPACE",
            workspace_path=str(workspace), workspace_fingerprint=fingerprint, active=True,
            source_checkpoint_id=checkpoint.id, created_at=NOW,
        ))
        session.add(MigrationPlanModel(
            id=plan_id, run_id=run_id, idempotency_key=f"plan-{run_id}", request_checksum="sha256:" + "7" * 64,
            actor="test", status="approved", version=1, plan=plan_payload, checksum=plan_payload["checksum"],
            artifact_ids=[], artifact_checksums={}, state_version=3, event_sequence=1,
            created_at=NOW, updated_at=NOW,
        ))
        session.add(StageExecutionPlanModel(
            id=stage_plan_id, run_id=run_id, migration_plan_id=plan_id, stage_id=stage_id,
            idempotency_key=f"stage-plan-{run_id}", request_checksum="sha256:" + "8" * 64,
            actor="test", status="approved", version=1, stage_plan=stage_payload,
            checksum=stage_payload["checksum"], artifact_ids=[], artifact_checksums={}, state_version=3,
            event_sequence=1, created_at=NOW, updated_at=NOW,
        ))
        old_g06 = G06ApprovalModel(
            id=f"g06-current-{run_id}", run_id=run_id, gate_id="G06", gate_version="g06-v1",
            idempotency_key=f"g06-{run_id}", actor="test", status="approved", decision="approve",
            package_checksum="sha256:" + "9" * 64, artifact_set_checksum="sha256:" + "a" * 64,
            plan_checksum=plan_payload["checksum"], stage_plan_checksum=stage_payload["checksum"],
            plan_version=1, workspace_fingerprint=fingerprint, artifact_ids=[], state_version=3,
            event_sequence=1, created_at=NOW, updated_at=NOW,
        )
        session.add(old_g06)
        session.add(TransformationContinuationModel(
            id=f"continuation-{run_id}", run_id=run_id, current_stage_id=stage_id,
            thread_id=f"thread-{run_id}", status="waiting_retry", current_node="retry_migration",
            g06_approval_id=old_g06.id, plan_id=plan_id, plan_checksum=plan_payload["checksum"],
            stage_plan_id=stage_plan_id, stage_plan_checksum=stage_payload["checksum"],
            attempt=1, max_attempts=3, claim_count=1, wake_sequence=1,
            idempotency_key=f"cont-{run_id}", request_checksum="sha256:" + "b" * 64,
            state_version=3, created_at=NOW, updated_at=NOW,
        ))
        if existing_catalogue is None:
            session.add(CompatibilityCatalogueModel(
                id=f"catalogue-{run_id}", version=catalogue_version, checksum=catalogue_checksum,
                metadata_json={}, created_at=NOW,
            ))
        session.add(resolution)
        session.add(FailureIntelligenceModel(
            id=f"fi-{run_id}", run_id=run_id,
            groups=[{"group_key": group_key, "taxonomy": taxonomy, "fault_codes": ["DEPENDENCY_PLAN_FAILED"]}],
            root_causes={group_key: {"group_key": group_key, "root_cause_code": "DEPENDENCY_PLAN_FAILED", "taxonomy": taxonomy}},
            graph={"nodes": [], "edges": []}, checksum="sha256:" + "c" * 64, created_at=NOW,
        ))
        session.flush()
        request = TransformationReplanRecoveryRequest(
            run_id=run_id, stage_id=stage_id, failed_execution_id=execution.id,
            failed_execution_result_checksum=TransformationReplanRecoveryService.execution_result_checksum(execution),
            failure_group_key=group_key, root_cause_code="DEPENDENCY_PLAN_FAILED", continuation_state_version=3,
            current_plan_id=plan_id, current_plan_checksum=plan_payload["checksum"],
            current_stage_plan_id=stage_plan_id, current_stage_plan_checksum=stage_payload["checksum"],
            safe_checkpoint_id=checkpoint.id,
            safe_checkpoint_checksum=TransformationReplanRecoveryService.checkpoint_checksum(checkpoint),
            safe_checkpoint_fingerprint=checkpoint_fingerprint, workspace_fingerprint=fingerprint,
            catalogue_version=catalogue_version, catalogue_checksum=catalogue_checksum,
            compatibility_resolution_checksum=TransformationReplanRecoveryService.compatibility_resolution_checksum(resolution),
            idempotency_key=f"recover-{run_id}",
        )
    return request


def test_generic_replan_creates_new_pending_plan_and_g06(tmp_path: Path):
    request = _seed(tmp_path)
    result = TransformationReplanRecoveryService().recover(request)
    assert result.status == "pending_approval"
    assert result.human_approval_required is True
    with session_scope() as session:
        continuation = session.query(TransformationContinuationModel).filter_by(run_id=request.run_id).one()
        old_plan = session.get(MigrationPlanModel, request.current_plan_id)
        old_gate = session.query(G06ApprovalModel).filter_by(run_id=request.run_id, gate_id="G06").order_by(G06ApprovalModel.created_at).first()
        new_gate = session.get(G06ApprovalModel, result.new_g06_id)
        assert continuation.plan_id == result.new_plan_id
        assert old_plan.status == "stale"
        assert old_gate.status == "stale"
        assert new_gate.status == "pending"
        replanned_stage = session.get(StageExecutionPlanModel, result.new_stage_plan_id)
        assert replanned_stage.stage_plan["commands"].get("installed_migration_fallback")
        assert replanned_stage.checksum != request.current_stage_plan_checksum


def test_replan_replay_is_durable_and_idempotent(tmp_path: Path):
    request = _seed(tmp_path)
    first = TransformationReplanRecoveryService().recover(request)
    replay = TransformationReplanRecoveryService().recover(request)
    assert replay.idempotent_replay is True
    assert replay.recovery_id == first.recovery_id
    with session_scope() as session:
        assert session.query(TransformationReplanRecoveryModel).filter_by(run_id=request.run_id).count() == 1


def test_replan_rejects_stale_evidence_and_unknown_failure(tmp_path: Path):
    request = _seed(tmp_path)
    with pytest.raises(TransformationReplanRecoveryError) as wrong_execution:
        TransformationReplanRecoveryService().recover(request.model_copy(update={"failed_execution_result_checksum": "sha256:" + "d" * 64}))
    assert wrong_execution.value.code == "STALE_FAILED_EXECUTION"

    with pytest.raises(TransformationReplanRecoveryError) as wrong_checkpoint:
        TransformationReplanRecoveryService().recover(request.model_copy(update={"safe_checkpoint_checksum": "sha256:" + "e" * 64}))
    assert wrong_checkpoint.value.code == "STALE_CHECKPOINT"

    with pytest.raises(TransformationReplanRecoveryError) as wrong_catalogue:
        TransformationReplanRecoveryService().recover(request.model_copy(update={"catalogue_checksum": "sha256:" + "f" * 64}))
    assert wrong_catalogue.value.code == "STALE_CATALOGUE"

    with pytest.raises(TransformationReplanRecoveryError) as wrong_plan:
        TransformationReplanRecoveryService().recover(request.model_copy(update={"current_plan_checksum": "sha256:" + "0" * 64}))
    assert wrong_plan.value.code == "STALE_PLAN"

    unknown = _seed(tmp_path / "unknown", taxonomy="command")
    with pytest.raises(TransformationReplanRecoveryError) as normal_repair:
        TransformationReplanRecoveryService().recover(unknown)
    assert normal_repair.value.code == "NORMAL_REPAIR_REQUIRED"


def test_replan_rejects_mutated_workspace_and_advanced_continuation(tmp_path: Path):
    request = _seed(tmp_path)
    with session_scope() as session:
        binding = session.query(StageWorkspaceBindingModel).filter_by(run_id=request.run_id).one()
        Path(binding.workspace_path, "package.json").write_text('{"changed":true}')
    with pytest.raises(TransformationReplanRecoveryError) as stale_workspace:
        TransformationReplanRecoveryService().recover(request)
    assert stale_workspace.value.code == "STALE_WORKSPACE"

    request = _seed(tmp_path / "advanced")
    with session_scope() as session:
        continuation = session.query(TransformationContinuationModel).filter_by(run_id=request.run_id).one()
        continuation.state_version = 4
    with pytest.raises(TransformationReplanRecoveryError) as stale_continuation:
        TransformationReplanRecoveryService().recover(request)
    assert stale_continuation.value.code == "STALE_CONTINUATION"
