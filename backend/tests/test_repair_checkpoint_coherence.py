"""T02: pre-repair checkpoint, workspace binding, and attempt coherence.

Proves the apply/recovery path treats the attempt-referenced pre-repair
checkpoint, the active workspace binding, and the attempt's pre-fingerprint as
one authoritative unit.  Every test here is RED against the base SHA and GREEN
after the checkpoint-binding fix.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType
from app.orchestration.transformer_graph import TransformerOrchestrator
from app.repositories.models import (
    ArtifactMetadataModel,
    G06ApprovalModel,
    MigrationPlanModel,
    MigrationRunModel,
    RepairAttemptModel,
    StageCheckpointModel,
    StageExecutionPlanModel,
    StageGateDecisionModel,
    StageGatePackageModel,
    StageReconstructionRecordModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
    WorkflowEventModel,
)
from app.repositories.models.base import Base
from app.services.patch_apply_service import PatchApplyService
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.stage_execution_application_service import StageExecutionApplicationService
from app.services.transformer_stage_service import TransformerStageError, TransformerStageService
from app.services.workspace_fingerprint import STAGE_FINGERPRINT_PROFILE

NOW = datetime(2026, 8, 1, tzinfo=UTC)


def _database(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'state.db'}")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _scope(factory):
    @contextmanager
    def scope():
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return scope


def _checksum(value: object) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _proposal_payload(app_ts: Path) -> dict[str, object]:
    return {
        "proposal_format": "operations",
        "operations": [
            {
                "operation": "replace_text",
                "path": "src/app.ts",
                "old_text": "old",
                "new_text": "new",
                "preimage_sha256": "sha256:" + hashlib.sha256(app_ts.read_bytes()).hexdigest(),
            }
        ],
        "unified_diff": None,
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
        "touched_files": ["src/app.ts"],
        "rationale": ["Fix the compiler error."],
        "risk_level": "low",
        "validation_targets": ["build"],
        "limitations": [],
    }


def _orchestrator(factory, *, patch_service=None, repair_service=None):
    return TransformerOrchestrator(
        scope=_scope(factory),
        stage_service=TransformerStageService(scope=_scope(factory), now_provider=lambda: NOW),
        gate_service=SimpleNamespace(_validate_repair_lineage=lambda *args, **kwargs: None),
        transformation_evidence=MagicMock(),
        prompt_explainer=MagicMock(),
        validation_runner=MagicMock(),
        failure_evidence=MagicMock(),
        repair_service=repair_service or MagicMock(),
        patch_service=patch_service or PatchApplyService(now_provider=lambda: NOW),
        sealing_flow=MagicMock(),
    )


def _seed_apply_authority(
    factory,
    tmp_path: Path,
    *,
    attempt_checkpoint_id: str = "ckpt-pre",
    attempt_pre_fingerprint: str | None = None,
    checkpoint_fingerprint: str | None = None,
    attempt_status: str = "waiting_g10",
    files: dict[str, str] | None = None,
):
    """Seed a fully authorized apply path: G10-approved repair on a live workspace.

    The pre-repair checkpoint snapshot is a real copy of the pre-repair
    workspace so reconstruct/recovery can be exercised truthfully.
    """
    files = files or {"src/app.ts": "old"}
    artifacts = tmp_path / "artifacts"
    stages = tmp_path / "stages"
    workspace = stages / "workspace"
    checkpoint_dir = stages / "ckpt-pre"
    workspace.mkdir(parents=True)
    checkpoint_dir.mkdir(parents=True)
    for relative, content in files.items():
        (workspace / relative).parent.mkdir(parents=True, exist_ok=True)
        (checkpoint_dir / relative).parent.mkdir(parents=True, exist_ok=True)
        (workspace / relative).write_text(content, encoding="utf-8")
        (checkpoint_dir / relative).write_text(content, encoding="utf-8")
    fingerprint = STAGE_FINGERPRINT_PROFILE.fingerprint(workspace)
    store = LocalFilesystemArtifactStore(artifacts.parent, fixed_run_root=artifacts)
    attempt_id = "repair-1"
    proposal = store.write_text_artifact(
        "run-1",
        f"05_repairs/attempt-{attempt_id}/proposal.json",
        json.dumps(_proposal_payload(workspace / "src" / "app.ts"), sort_keys=True),
        ArtifactType.JSON,
        stage_id="stage-1",
        attempt_id=attempt_id,
        created_by="repair-proposal",
        created_at=NOW,
    )
    session = factory()
    run = MigrationRunModel(
        id="run-1",
        status="STAGE_CREATED",
        run_phase="FEASIBILITY_PLANNING",
        phase_status="completed",
        state_version=7,
        run_root=str(tmp_path),
        artifact_root=str(artifacts),
        workspace_aliases={"STAGE_SANDBOX": str(stages)},
        created_at=NOW,
        updated_at=NOW,
    )
    plan = StageExecutionPlanModel(
        id="stage-plan-1",
        run_id="run-1",
        migration_plan_id="plan-1",
        stage_id="stage-1",
        idempotency_key="plan",
        request_checksum="sha256:plan",
        actor="operator",
        correlation_id="corr-1",
        status="approved",
        version=1,
        stage_plan={"repair_policy": {"max_attempts": 3}, "forbidden_change_policy": {}},
        checksum="sha256:stage-plan",
        artifact_ids=[],
        artifact_checksums={},
        state_version=1,
        event_sequence=1,
        created_at=NOW,
        updated_at=NOW,
    )
    binding = StageWorkspaceBindingModel(
        id="binding-1",
        run_id="run-1",
        stage_id="stage-1",
        alias="STAGE_WORKSPACE_1",
        workspace_path=str(workspace),
        workspace_fingerprint=fingerprint,
        active=True,
        created_at=NOW,
    )
    continuation = TransformationContinuationModel(
        id="cont-1",
        run_id="run-1",
        current_stage_id="stage-1",
        thread_id="thread-1",
        status="running",
        current_node="apply_repair",
        worker_id="worker-1",
        lease_expires_at=NOW + timedelta(seconds=120),
        g06_approval_id="g06-1",
        plan_id="plan-1",
        plan_checksum="sha256:plan",
        stage_plan_id="stage-plan-1",
        stage_plan_checksum="sha256:stage-plan",
        idempotency_key="continuation",
        request_checksum="sha256:continuation",
        state_version=3,
        attempt=1,
        max_attempts=3,
        created_at=NOW,
        updated_at=NOW,
    )
    attempt = RepairAttemptModel(
        id=attempt_id,
        run_id="run-1",
        stage_id="stage-1",
        attempt_number=1,
        status=attempt_status,
        risk_level="low",
        diagnosis="repairable_source; checkpoint=ckpt-pre",
        checkpoint_id=attempt_checkpoint_id,
        g10_gate_package_id="gate-10",
        failure_evidence_artifact_id="artifact-failure",
        failure_evidence_checksum="sha256:failure",
        failure_route_artifact_id="artifact-route",
        failure_route_checksum="sha256:route",
        context_pack_artifact_id="artifact-context",
        context_pack_checksum="sha256:context",
        proposal_artifact_id=proposal.ref.artifact_id,
        proposal_checksum=proposal.ref.checksum,
        proposer_invocation_id="repair-1:proposer",
        reviewer_invocation_id="repair-1:reviewer",
        pre_fingerprint=attempt_pre_fingerprint or fingerprint,
        failure_fingerprint="fingerprint-failure",
        created_at=NOW,
        updated_at=NOW,
    )
    checkpoint = StageCheckpointModel(
        id="ckpt-pre",
        run_id="run-1",
        stage_id="stage-1",
        kind="pre_repair",
        sequence=1,
        workspace_alias="STAGE_WORKSPACE_1",
        workspace_path=str(checkpoint_dir),
        workspace_fingerprint=checkpoint_fingerprint or fingerprint,
        safe_for_resume=True,
        sealed=False,
        state_version=3,
        created_at=NOW,
    )
    gate = StageGatePackageModel(
        id="gate-10",
        run_id="run-1",
        stage_id="stage-1",
        gate_id="G10",
        gate_version=1,
        status="approved",
        package_artifact_id="artifact-g10",
        package_checksum="sha256:g10",
        artifact_set_checksum="sha256:g10-set",
        plan_id="plan-1",
        plan_version=1,
        stage_plan_id="stage-plan-1",
        stage_plan_checksum="sha256:stage-plan",
        workspace_fingerprint=fingerprint,
        expected_state_version=3,
        created_at=NOW,
    )
    decision = StageGateDecisionModel(
        id="decision-10",
        gate_package_id="gate-10",
        run_id="run-1",
        stage_id="stage-1",
        gate_id="G10",
        decision="approve",
        actor="operator",
        idempotency_key="approve-g10",
        request_checksum="sha256:approve",
        expected_state_version=3,
        package_checksum="sha256:g10",
        workspace_fingerprint=fingerprint,
        accepted=True,
        created_at=NOW,
    )
    session.add_all(
        [run, plan, binding, continuation, attempt, checkpoint, gate, decision]
    )
    session.add(
        ArtifactMetadataModel(
            id="metadata-" + proposal.ref.artifact_id,
            run_id="run-1",
            stage_id="stage-1",
            artifact_type=proposal.ref.artifact_type.value,
            relative_path=proposal.ref.relative_path,
            checksum=proposal.ref.checksum,
            created_at=NOW,
            finalized_at=NOW,
            immutable=True,
        )
    )
    session.commit()
    session.close()
    return store, attempt_id, workspace, artifacts, stages


def test_apply_refuses_workspace_that_matches_binding_but_not_referenced_checkpoint(
    tmp_path: Path,
):
    engine, factory = _database(tmp_path)
    _store, attempt_id, workspace, _artifacts, _stages = _seed_apply_authority(factory, tmp_path)
    session = factory()
    checkpoint = session.get(StageCheckpointModel, "ckpt-pre")
    checkpoint.workspace_fingerprint = "sha256:" + "0" * 64
    session.commit()
    session.close()

    with pytest.raises(TransformerStageError) as raised:
        _orchestrator(factory)._apply_repair_locked("cont-1", "worker-1")

    assert raised.value.code == "REPAIR_PROPOSAL_STALE"
    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.status == "waiting_g10"
    assert (workspace / "src" / "app.ts").read_text(encoding="utf-8") == "old"
    session.close()
    engine.dispose()


def test_apply_refuses_when_attempt_pre_fingerprint_disagrees_with_live_workspace(
    tmp_path: Path,
):
    engine, factory = _database(tmp_path)
    _store, attempt_id, workspace, _artifacts, _stages = _seed_apply_authority(
        factory, tmp_path, attempt_pre_fingerprint="sha256:" + "1" * 64
    )

    with pytest.raises(TransformerStageError) as raised:
        _orchestrator(factory)._apply_repair_locked("cont-1", "worker-1")

    assert raised.value.code == "REPAIR_PROPOSAL_STALE"
    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.status == "waiting_g10"
    assert (workspace / "src" / "app.ts").read_text(encoding="utf-8") == "old"
    session.close()
    engine.dispose()


def test_apply_refuses_when_attempt_references_no_pre_repair_checkpoint(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, workspace, _artifacts, _stages = _seed_apply_authority(
        factory, tmp_path, attempt_checkpoint_id=None
    )

    with pytest.raises(TransformerStageError) as raised:
        _orchestrator(factory)._apply_repair_locked("cont-1", "worker-1")

    assert raised.value.code == "CHECKPOINT_MISSING"
    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.status == "waiting_g10"
    assert (workspace / "src" / "app.ts").read_text(encoding="utf-8") == "old"
    session.close()
    engine.dispose()


def test_mixed_case_tree_apply_succeeds_when_all_fingerprints_agree(tmp_path: Path):
    engine, factory = _database(tmp_path)
    files = {
        "README.md": "readme",
        "package.json": "{}",
        "angular.json": "{}",
        "src/main.ts": "main",
        "src/app/App.component.ts": "component",
        "src/assets/Logo.PNG": "logo",
        "tsconfig.json": "{}",
        "src/app.ts": "old",
    }
    _store, attempt_id, workspace, _artifacts, _stages = _seed_apply_authority(
        factory, tmp_path, files=files
    )
    manifest_digest = __import__(
        "app.services.patch_apply_service", fromlist=["_fingerprint_manifest"]
    )._fingerprint_manifest
    tree_digest = STAGE_FINGERPRINT_PROFILE.fingerprint(workspace)
    assert manifest_digest(dict(_manifest(workspace))) == tree_digest

    _orchestrator(factory)._apply_repair_locked("cont-1", "worker-1")

    session = factory()
    assert (workspace / "src" / "app.ts").read_text(encoding="utf-8") == "new"
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.status == "applied"
    binding = session.get(StageWorkspaceBindingModel, "binding-1")
    assert binding.workspace_fingerprint == attempt.post_fingerprint
    assert binding.workspace_fingerprint == STAGE_FINGERPRINT_PROFILE.fingerprint(workspace)
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "queued"
    assert continuation.current_node == "repair_revalidate"
    session.close()
    engine.dispose()


def _manifest(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_recovery_uses_attempt_referenced_checkpoint_not_latest_stage_checkpoint(
    tmp_path: Path,
):
    engine, factory = _database(tmp_path)
    _store, attempt_id, workspace, _artifacts, stages = _seed_apply_authority(factory, tmp_path)
    session = factory()
    checkpoint_old = session.get(StageCheckpointModel, "ckpt-pre")
    mutated = workspace / "src" / "app.ts"
    mutated.write_text("mutated", encoding="utf-8")
    newer = stages / "ckpt-new"
    newer.mkdir(parents=True)
    (newer / "src").mkdir(parents=True)
    (newer / "src" / "app.ts").write_text("newer-state", encoding="utf-8")
    session.add(
        StageCheckpointModel(
            id="ckpt-new",
            run_id="run-1",
            stage_id="stage-1",
            kind="pre_repair",
            sequence=2,
            workspace_alias="STAGE_WORKSPACE_1",
            workspace_path=str(newer),
            workspace_fingerprint=STAGE_FINGERPRINT_PROFILE.fingerprint(newer),
            safe_for_resume=True,
            sealed=False,
            state_version=3,
            created_at=NOW,
        )
    )
    assert checkpoint_old.sequence < 2
    session.commit()
    session.close()

    orchestrator = _orchestrator(factory)
    orchestrator._recover_failed_apply(
        "cont-1",
        str(workspace),
        mutation_started=True,
        apply_claimed=True,
    )

    session = factory()
    assert (workspace / "src" / "app.ts").read_text(encoding="utf-8") == "old"
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.status == "apply_recovery_required"
    assert attempt.post_fingerprint == STAGE_FINGERPRINT_PROFILE.fingerprint(workspace)
    binding = session.get(StageWorkspaceBindingModel, "binding-1")
    assert binding.workspace_fingerprint == attempt.post_fingerprint
    assert binding.last_verified_fingerprint == attempt.post_fingerprint
    assert binding.last_verified_at is not None
    records = session.query(StageReconstructionRecordModel).all()
    assert len(records) == 1
    assert records[0].checkpoint_id == "ckpt-pre"
    assert records[0].attempt_id == attempt_id
    assert records[0].source_workspace_fingerprint == attempt.pre_fingerprint
    assert records[0].restored_workspace_fingerprint == binding.workspace_fingerprint
    event_types = {
        event.event_type
        for event in session.query(WorkflowEventModel).filter(WorkflowEventModel.run_id == "run-1")
    }
    assert "STAGE_WORKSPACE_RECONSTRUCTION_STARTED" in event_types
    assert "STAGE_WORKSPACE_RECONSTRUCTED" in event_types
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "blocked"
    assert continuation.last_error_code == "REPAIR_APPLY_RECOVERY_REQUIRED"
    session.close()
    engine.dispose()


def test_recovery_by_id_reload_rejects_cross_stage_attempt(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, _attempt_id, _workspace, _artifacts, _stages = _seed_apply_authority(factory, tmp_path)
    session = factory()
    session.add(
        RepairAttemptModel(
            id="repair-other-stage",
            run_id="run-1",
            stage_id="stage-2",
            attempt_number=1,
            status="applying",
            risk_level="unknown",
            diagnosis="repairable_source; checkpoint=ckpt-pre",
            checkpoint_id="ckpt-pre",
            created_at=NOW,
            updated_at=NOW,
        )
    )
    session.commit()
    session.close()

    with pytest.raises(TransformerStageError) as raised:
        _orchestrator(factory)._mark_apply_recovery_required(
            "cont-1", "sha256:" + "2" * 64, "repair-other-stage"
        )

    assert raised.value.code == "REPAIR_PROPOSAL_STALE"
    session = factory()
    attempt = session.get(RepairAttemptModel, "repair-other-stage")
    assert attempt.status == "applying"
    session.close()
    engine.dispose()


class _RequestChangesReviewer:
    def review(self, attempt_id: str):
        return {
            "decision": "request_changes",
            "findings": [],
            "policy_checks": ["paths"],
            "risk_assessment": "low",
            "required_validation_targets": ["build"],
            "limitations": [],
        }


def _seed_review(factory, tmp_path: Path, *, attempt_status: str, checkpoint_id: str | None = "ckpt-pre"):
    artifacts = tmp_path / "artifacts"
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "app.ts").write_text("old", encoding="utf-8")
    store = LocalFilesystemArtifactStore(artifacts.parent, fixed_run_root=artifacts)
    failure = store.write_text_artifact(
        "run-1",
        "05_repairs/attempt-repair-1/failure-evidence.json",
        json.dumps({"attempt_id": "repair-1"}),
        ArtifactType.JSON,
        stage_id="stage-1",
        attempt_id="repair-1",
        created_by="repair-failure-evidence",
        created_at=NOW,
    )
    review = store.write_text_artifact(
        "run-1",
        "05_repairs/attempt-repair-1/review.json",
        json.dumps(
            {
                "decision": {
                    "request_changes": "request_changes",
                    "rejected": "reject",
                    "review_accepted": "accept",
                }.get(attempt_status, "request_changes"),
                "findings": [],
                "policy_checks": ["paths"],
                "risk_assessment": "low",
                "required_validation_targets": ["build"],
                "limitations": [],
                "proposal_checksum": "sha256:proposal",
            },
            sort_keys=True,
        ),
        ArtifactType.JSON,
        stage_id="stage-1",
        attempt_id="repair-1",
        created_by="repair-review",
        created_at=NOW,
    )
    session = factory()
    run = MigrationRunModel(
        id="run-1",
        status="STAGE_CREATED",
        run_phase="FEASIBILITY_PLANNING",
        phase_status="completed",
        state_version=7,
        run_root=str(tmp_path),
        artifact_root=str(artifacts),
        workspace_aliases={"STAGE_SANDBOX": str(tmp_path)},
        created_at=NOW,
        updated_at=NOW,
    )
    plan = StageExecutionPlanModel(
        id="stage-plan-1",
        run_id="run-1",
        migration_plan_id="plan-1",
        stage_id="stage-1",
        idempotency_key="plan",
        request_checksum="sha256:plan",
        actor="operator",
        correlation_id="corr-1",
        status="approved",
        version=1,
        stage_plan={"repair_policy": {"max_attempts": 3}, "forbidden_change_policy": {}},
        checksum="sha256:stage-plan",
        artifact_ids=[],
        artifact_checksums={},
        state_version=1,
        event_sequence=1,
        created_at=NOW,
        updated_at=NOW,
    )
    binding = StageWorkspaceBindingModel(
        id="binding-1",
        run_id="run-1",
        stage_id="stage-1",
        alias="STAGE_WORKSPACE_1",
        workspace_path=str(workspace),
        workspace_fingerprint=StageSandboxCopier.fingerprint(workspace),
        active=True,
        created_at=NOW,
    )
    continuation = TransformationContinuationModel(
        id="cont-1",
        run_id="run-1",
        current_stage_id="stage-1",
        thread_id="thread-1",
        status="running",
        current_node="review_repair",
        worker_id="worker-1",
        lease_expires_at=NOW + timedelta(seconds=120),
        g06_approval_id="g06-1",
        plan_id="plan-1",
        plan_checksum="sha256:plan",
        stage_plan_id="stage-plan-1",
        stage_plan_checksum="sha256:stage-plan",
        idempotency_key="continuation",
        request_checksum="sha256:continuation",
        state_version=3,
        attempt=1,
        max_attempts=3,
        created_at=NOW,
        updated_at=NOW,
    )
    attempt = RepairAttemptModel(
        id="repair-1",
        run_id="run-1",
        stage_id="stage-1",
        attempt_number=1,
        status=attempt_status,
        risk_level="low",
        diagnosis="repairable_source; checkpoint=ckpt-pre",
        checkpoint_id=checkpoint_id,
        failure_evidence_artifact_id=failure.ref.artifact_id,
        failure_evidence_checksum=failure.ref.checksum,
        failure_route_artifact_id="artifact-route",
        failure_route_checksum="sha256:route",
        context_pack_artifact_id="artifact-context",
        context_pack_checksum="sha256:context",
        proposal_artifact_id="artifact-proposal",
        proposal_checksum="sha256:proposal",
        proposer_invocation_id="repair-1:proposer",
        reviewer_invocation_id="repair-1:reviewer",
        review_artifact_id=review.ref.artifact_id,
        review_checksum=review.ref.checksum,
        pre_fingerprint=StageSandboxCopier.fingerprint(workspace),
        failure_fingerprint="fingerprint-failure",
        created_at=NOW,
        updated_at=NOW,
    )
    session.add_all([run, plan, binding, continuation, attempt])
    session.add(
        ArtifactMetadataModel(
            id="metadata-" + failure.ref.artifact_id,
            run_id="run-1",
            stage_id="stage-1",
            artifact_type=failure.ref.artifact_type.value,
            relative_path=failure.ref.relative_path,
            checksum=failure.ref.checksum,
            created_at=NOW,
            finalized_at=NOW,
            immutable=True,
        )
    )
    session.add(
        ArtifactMetadataModel(
            id="metadata-" + review.ref.artifact_id,
            run_id="run-1",
            stage_id="stage-1",
            artifact_type=review.ref.artifact_type.value,
            relative_path=review.ref.relative_path,
            checksum=review.ref.checksum,
            created_at=NOW,
            finalized_at=NOW,
            immutable=True,
        )
    )
    session.commit()
    session.close()
    return store


def test_child_attempt_requires_valid_request_changes_parent(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _seed_review(factory, tmp_path, attempt_status="request_changes")

    _orchestrator(factory, repair_service=_RequestChangesReviewer()).advance(
        "cont-1", "worker-1"
    )

    session = factory()
    attempts = session.query(RepairAttemptModel).order_by(
        RepairAttemptModel.attempt_number
    ).all()
    assert [attempt.attempt_number for attempt in attempts] == [1, 2]
    parent = attempts[0]
    child = attempts[1]
    assert child.id == "repair-stage-1-2"
    assert child.parent_attempt_id == "repair-1"
    assert child.checkpoint_id == "ckpt-pre"
    assert child.status == "evidence_frozen"
    assert child.parent_review_artifact_id == parent.review_artifact_id
    assert child.parent_review_checksum == parent.review_checksum
    assert child.diagnosis != parent.diagnosis
    assert "checkpoint=ckpt-pre" not in (child.diagnosis or "")
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "queued"
    assert continuation.current_node == "propose_repair"
    session.close()
    engine.dispose()


def test_child_attempt_rejects_non_request_changes_parent(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _seed_review(factory, tmp_path, attempt_status="rejected")

    _orchestrator(factory, repair_service=_RequestChangesReviewer()).advance(
        "cont-1", "worker-1"
    )

    session = factory()
    attempts = session.query(RepairAttemptModel).all()
    assert len(attempts) == 1
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "blocked"
    assert continuation.last_error_code == "REPAIR_PARENT_LINEAGE_INVALID"
    session.close()
    engine.dispose()


def test_child_attempt_rejects_tampered_parent_review_artifact(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _seed_review(factory, tmp_path, attempt_status="request_changes")
    session = factory()
    attempt = session.get(RepairAttemptModel, "repair-1")
    metadata = session.get(ArtifactMetadataModel, "metadata-" + attempt.review_artifact_id)
    artifact_file = (tmp_path / "artifacts" / metadata.relative_path).resolve()
    sidecar_file = artifact_file.with_name(artifact_file.name + ".meta.json")
    tampered = json.loads(artifact_file.read_text(encoding="utf-8"))
    tampered["decision"] = "accept"
    new_bytes = json.dumps(tampered, sort_keys=True).encode("utf-8")
    new_checksum = "sha256:" + hashlib.sha256(new_bytes).hexdigest()
    artifact_file.write_bytes(new_bytes)
    sidecar = json.loads(sidecar_file.read_text(encoding="utf-8"))
    sidecar["content_hash"] = new_checksum
    sidecar["checksum"] = new_checksum
    sidecar_file.write_text(json.dumps(sidecar, indent=2, sort_keys=True), encoding="utf-8")
    session.commit()
    session.close()

    _orchestrator(factory, repair_service=_RequestChangesReviewer()).advance(
        "cont-1", "worker-1"
    )

    session = factory()
    attempts = session.query(RepairAttemptModel).all()
    assert len(attempts) == 1
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "blocked"
    assert continuation.last_error_code == "REPAIR_PARENT_LINEAGE_INVALID"
    session.close()
    engine.dispose()


def test_binding_input_fingerprint_is_written_and_readable_from_stage_input_checkpoint(
    tmp_path: Path,
):
    engine, factory = _database(tmp_path)
    baseline = tmp_path / "baseline"
    stages = tmp_path / "stages"
    artifacts = tmp_path / "artifacts" / "run-1"
    baseline.mkdir()
    stages.mkdir()
    artifacts.mkdir(parents=True)
    (baseline / "package.json").write_text('{"name":"stage-input"}', encoding="utf-8")
    session = factory()
    run = MigrationRunModel(
        id="run-1",
        status="WAITING_STAGE_PREPARATION",
        run_phase="STAGED_MIGRATION",
        state_version=7,
        actor="operator",
        run_root=str(tmp_path),
        artifact_root=str(artifacts),
        workspace_aliases={
            "BASELINE_SANDBOX": str(baseline),
            "STAGE_SANDBOX": str(stages),
        },
        created_at=NOW,
        updated_at=NOW,
    )
    plan = MigrationPlanModel(
        id="plan-1",
        run_id="run-1",
        idempotency_key="plan",
        request_checksum="sha256:plan",
        actor="planner",
        status="approved",
        version=1,
        plan={},
        checksum="sha256:plan",
        artifact_ids=[],
        artifact_checksums={},
        state_version=5,
        event_sequence=1,
        created_at=NOW,
        updated_at=NOW,
    )
    stage_plan = StageExecutionPlanModel(
        id="stage-plan-1",
        run_id="run-1",
        migration_plan_id="plan-1",
        stage_id="stage-1",
        idempotency_key="stage-plan",
        request_checksum="sha256:stage-plan-request",
        actor="planner",
        status="approved",
        version=1,
        stage_plan={},
        checksum="sha256:stage-plan",
        artifact_ids=[],
        artifact_checksums={},
        state_version=5,
        event_sequence=2,
        created_at=NOW,
        updated_at=NOW,
    )
    gate = G06ApprovalModel(
        id="g06-1",
        run_id="run-1",
        gate_id="G06",
        gate_version="g06-v1",
        idempotency_key="g06",
        actor="operator",
        status="approved",
        decision="approve",
        package_checksum="sha256:g06-package",
        artifact_set_checksum="sha256:g06-set",
        plan_checksum="sha256:plan",
        stage_plan_checksum="sha256:stage-plan",
        plan_version=1,
        artifact_ids=[],
        state_version=7,
        event_sequence=3,
        created_at=NOW,
        updated_at=NOW,
    )
    from app.repositories.models import ActivePlanVersionModel

    session.add_all(
        [
            run,
            plan,
            stage_plan,
            gate,
            ActivePlanVersionModel(
                id="active-stage",
                run_id="run-1",
                scope="stage-1",
                migration_plan_id="plan-1",
                stage_plan_id="stage-plan-1",
                version=1,
                state_version=7,
                updated_at=NOW,
            ),
        ]
    )
    continuation = TransformationContinuationModel(
        id="cont-1",
        run_id="run-1",
        current_stage_id="stage-1",
        thread_id="thread-1",
        status="running",
        current_node="prepare_workspace",
        worker_id="worker-1",
        lease_expires_at=NOW + timedelta(seconds=120),
        g06_approval_id="g06-1",
        plan_id="plan-1",
        plan_checksum="sha256:plan",
        stage_plan_id="stage-plan-1",
        stage_plan_checksum="sha256:stage-plan",
        idempotency_key="continuation",
        request_checksum="sha256:continuation",
        state_version=3,
        attempt=1,
        max_attempts=3,
        created_at=NOW,
        updated_at=NOW,
    )
    session.add(continuation)
    session.commit()
    session.close()

    orchestrator = TransformerOrchestrator(
        scope=_scope(factory),
        stage_service=TransformerStageService(scope=_scope(factory), now_provider=lambda: NOW),
        gate_service=MagicMock(),
        transformation_evidence=MagicMock(),
        prompt_explainer=MagicMock(),
        validation_runner=MagicMock(),
        failure_evidence=MagicMock(),
        repair_service=MagicMock(),
        patch_service=MagicMock(),
        sealing_flow=MagicMock(),
    )
    orchestrator.advance("cont-1", "worker-1")

    session = factory()
    binding = session.get(StageWorkspaceBindingModel, "binding-1") or session.query(
        StageWorkspaceBindingModel
    ).one()
    assert binding.input_fingerprint is not None
    assert binding.input_fingerprint == binding.workspace_fingerprint
    checkpoint = session.query(StageCheckpointModel).filter_by(kind="pre_bootstrap").one()
    assert binding.source_checkpoint_id == checkpoint.id
    assert checkpoint.workspace_fingerprint == binding.input_fingerprint
    session.close()
    engine.dispose()


def test_patch_apply_manifest_digest_matches_tree_digest_on_mixed_case_workspace(tmp_path: Path):
    workspace = tmp_path / "workspace"
    for relative, content in {
        "README.md": "readme",
        "package.json": "{}",
        "angular.json": "{}",
        "src/main.ts": "main",
        "src/app/App.component.ts": "component",
        "src/assets/Logo.PNG": "logo",
        "tsconfig.json": "{}",
    }.items():
        path = workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    manifest_module = __import__(
        "app.services.patch_apply_service", fromlist=["_fingerprint_manifest"]
    )
    from app.services.patch_apply_service import _workspace_manifest

    assert manifest_module._fingerprint_manifest(_workspace_manifest(workspace)) == (
        STAGE_FINGERPRINT_PROFILE.fingerprint(workspace)
    )
