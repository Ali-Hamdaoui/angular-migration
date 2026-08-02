"""T03: governed durable reconstruction ledger.

Every workspace reconstruction must be durably recorded: the reconstruction
source (immutable checkpoint) is verified by id + kind + fingerprint, the
restored fingerprint is persisted to the binding AND to a durable ledger row in
the same transaction as the authoritative state change, and the declared
reconstruction events (STARTED / RECONSTRUCTED / FINGERPRINT_MISMATCH) are
emitted.  Every test here is RED against the base SHA and GREEN after the
governed reconstruction ledger fix.
"""

from __future__ import annotations

import hashlib
import json
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType, WorkflowEventType
from app.orchestration.transformer_graph import TransformerOrchestrator
from app.orchestration.transformer_sealing_flow import TransformerSealingFlow
from app.repositories.models import (
    ActivePlanVersionModel,
    ArtifactMetadataModel,
    CommandExecutionModel,
    G06ApprovalModel,
    MigrationPlanModel,
    MigrationRunModel,
    MigrationStageModel,
    RepairAttemptModel,
    StageCheckpointModel,
    StageExecutionPlanModel,
    StageGateDecisionModel,
    StageGatePackageModel,
    StagePromptRequestModel,
    StageStepModel,
    StageWorkspaceBindingModel,
    StageReconstructionRecordModel,
    TransformationContinuationModel,
    WorkflowEventModel,
)
from app.repositories.models.base import Base
from app.services.patch_apply_service import PatchApplyService
from app.services.stage_execution_application_service import StageExecutionApplicationService
from app.services.stage_preparation_application_service import (
    StagePreparationApplicationService,
    StagePreparationError,
)
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.transformer_stage_service import TransformerStageError, TransformerStageService
from app.services.workspace_fingerprint import STAGE_FINGERPRINT_PROFILE

NOW = datetime(2026, 8, 1, tzinfo=UTC)


def _database(tmp_path: Path, *, threaded: bool = False):
    connect_args = {"check_same_thread": False} if threaded else {}
    engine = create_engine(f"sqlite:///{tmp_path / 'state.db'}", connect_args=connect_args)
    if threaded:

        @event.listens_for(engine, "connect")
        def _configure_sqlite(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA busy_timeout = 10000")
            cursor.close()

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


def _crash_scope(factory, *, crash_on_commit: int = 2):
    state = {"commits": 0}

    @contextmanager
    def scope():
        session = factory()
        try:
            yield session
            state["commits"] += 1
            if state["commits"] >= crash_on_commit:
                raise RuntimeError("simulated crash between filesystem swap and ledger commit")
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return scope, state


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


def _orchestrator(factory, *, scope=None, stage_service=None, patch_service=None):
    scope = scope or _scope(factory)
    return TransformerOrchestrator(
        scope=scope,
        stage_service=stage_service or TransformerStageService(scope=scope, now_provider=lambda: NOW),
        gate_service=SimpleNamespace(_validate_repair_lineage=lambda *args, **kwargs: None),
        transformation_evidence=MagicMock(),
        prompt_explainer=MagicMock(),
        validation_runner=MagicMock(),
        failure_evidence=MagicMock(),
        repair_service=MagicMock(),
        patch_service=patch_service or PatchApplyService(now_provider=lambda: NOW),
        sealing_flow=MagicMock(),
    )


def _tree(root: Path, files: dict[str, str]) -> None:
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _seed_prompt_stage(
    factory,
    tmp_path: Path,
    *,
    checkpoint_fingerprint: str | None = None,
    execution_checkpoint_id: str = "ckpt-pre",
    prompt_checkpoint_id: str = "ckpt-pre",
    workspace_files: dict[str, str] | None = None,
):
    """Seed a governed prompt reconstruction: pre_angular_update checkpoint,
    failed angular update execution, detected prompt, active binding."""
    workspace_files = workspace_files or {"src/app.ts": "old"}
    artifacts = tmp_path / "artifacts"
    stages = tmp_path / "stages"
    workspace = stages / "workspace"
    checkpoint_dir = stages / "ckpt-pre"
    _tree(workspace, workspace_files)
    _tree(checkpoint_dir, workspace_files)
    fingerprint = STAGE_FINGERPRINT_PROFILE.fingerprint(workspace)
    session = factory()
    run = MigrationRunModel(
        id="run-1",
        status="STAGE_CREATED",
        run_phase="STAGED_MIGRATION",
        phase_status="running",
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
        stage_plan={},
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
        current_node="handle_prompt",
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
    execution = CommandExecutionModel(
        id="exec-1",
        run_id="run-1",
        stage_id="stage-1",
        command_id="angular-update-exact",
        status="failed",
        failure_code="COMMAND_EXIT_NONZERO",
        failure_message="ng update failed",
        executable="npx",
        arguments=[],
        requested_at=NOW,
        state_version=1,
        attempt_number=1,
        operation_kind="mutating",
        checkpoint_id=execution_checkpoint_id,
        prompt_request_id="prompt-1",
    )
    step = StageStepModel(
        id="step-1",
        run_id="run-1",
        stage_id="stage-1",
        name="angular_update-0",
        status="FAILED",
        component_type="command",
        execution_id=execution.id,
        state_version=1,
        updated_at=NOW,
    )
    prompt = StagePromptRequestModel(
        id="prompt-1",
        run_id="run-1",
        stage_id="stage-1",
        execution_id=execution.id,
        kind="boolean",
        detector_version="v1",
        normalized_prompt="Continue?",
        options_json=[],
        context_artifact_ids=[],
        prompt_checksum="sha256:prompt",
        pre_command_fingerprint=fingerprint,
        status="detected",
        reconstruction_checkpoint_id=prompt_checkpoint_id,
        created_at=NOW,
    )
    checkpoint = StageCheckpointModel(
        id="ckpt-pre",
        run_id="run-1",
        stage_id="stage-1",
        kind="pre_angular_update",
        sequence=1,
        workspace_alias="STAGE_WORKSPACE_1",
        workspace_path=str(checkpoint_dir),
        workspace_fingerprint=checkpoint_fingerprint or fingerprint,
        safe_for_resume=True,
        sealed=False,
        state_version=3,
        created_at=NOW,
    )
    session.add_all([run, plan, binding, continuation, execution, step, prompt, checkpoint])
    session.commit()
    session.close()
    return workspace, checkpoint_dir, fingerprint


def test_prompt_reconstruction_writes_ledger_and_binding_in_one_transaction(tmp_path: Path):
    engine, factory = _database(tmp_path)
    workspace, checkpoint_dir, fingerprint = _seed_prompt_stage(factory, tmp_path)

    _orchestrator(factory)._handle_prompt("cont-1", "worker-1")

    session = factory()
    records = session.query(StageReconstructionRecordModel).all()
    assert len(records) == 1
    record = records[0]
    assert record.reason == "prompt_reconstruction"
    assert record.checkpoint_id == "ckpt-pre"
    assert record.source_workspace_fingerprint == fingerprint
    assert record.created_from_execution_id == "exec-1"
    assert record.attempt_id is None
    binding = session.get(StageWorkspaceBindingModel, "binding-1")
    assert record.restored_workspace_fingerprint == binding.workspace_fingerprint
    assert binding.workspace_fingerprint == STAGE_FINGERPRINT_PROFILE.fingerprint(workspace)
    assert binding.last_verified_fingerprint == binding.workspace_fingerprint
    assert binding.last_verified_at is not None
    prompt = session.get(StagePromptRequestModel, "prompt-1")
    assert prompt.observed_fingerprint == binding.workspace_fingerprint
    events = {
        event.event_type: event
        for event in session.query(WorkflowEventModel)
        .filter(WorkflowEventModel.run_id == "run-1")
        .order_by(WorkflowEventModel.sequence)
    }
    assert WorkflowEventType.STAGE_WORKSPACE_RECONSTRUCTION_STARTED.value in events
    reconstructed = events[WorkflowEventType.STAGE_WORKSPACE_RECONSTRUCTED.value]
    assert reconstructed.payload["restored_workspace_fingerprint"] == binding.workspace_fingerprint
    assert reconstructed.payload["checkpoint_id"] == "ckpt-pre"
    assert (
        events[WorkflowEventType.STAGE_WORKSPACE_RECONSTRUCTION_STARTED.value].sequence
        < reconstructed.sequence
    )
    session.close()
    engine.dispose()


def test_prompt_reconstruction_crash_between_swap_and_commit_has_no_window(tmp_path: Path):
    engine, factory = _database(tmp_path)
    workspace, _checkpoint_dir, fingerprint = _seed_prompt_stage(factory, tmp_path)
    scope, state = _crash_scope(factory, crash_on_commit=2)

    with pytest.raises(RuntimeError, match="simulated crash"):
        _orchestrator(factory, scope=scope)._handle_prompt("cont-1", "worker-1")

    assert state["commits"] == 2
    session = factory()
    assert session.query(StageReconstructionRecordModel).count() == 0
    binding = session.get(StageWorkspaceBindingModel, "binding-1")
    assert binding.workspace_fingerprint == fingerprint
    assert binding.last_verified_fingerprint is None
    events = list(session.query(WorkflowEventModel).order_by(WorkflowEventModel.sequence))
    assert [event.event_type for event in events] == [
        WorkflowEventType.STAGE_WORKSPACE_RECONSTRUCTION_STARTED.value
    ]
    assert (workspace / "src" / "app.ts").read_text(encoding="utf-8") == "old"
    session.close()
    engine.dispose()


def test_prompt_reconstruction_fingerprint_mismatch_emits_event_and_refuses(tmp_path: Path):
    engine, factory = _database(tmp_path)
    workspace, _checkpoint_dir, _fingerprint = _seed_prompt_stage(
        factory, tmp_path, checkpoint_fingerprint="sha256:" + "0" * 64
    )
    original = (workspace / "src" / "app.ts").read_text(encoding="utf-8")

    with pytest.raises(TransformerStageError) as raised:
        _orchestrator(factory)._handle_prompt("cont-1", "worker-1")

    assert raised.value.code == "WORKSPACE_FINGERPRINT_MISMATCH"
    session = factory()
    assert session.query(StageReconstructionRecordModel).count() == 0
    events = {
        event.event_type
        for event in session.query(WorkflowEventModel).filter(WorkflowEventModel.run_id == "run-1")
    }
    assert WorkflowEventType.STAGE_WORKSPACE_FINGERPRINT_MISMATCH.value in events
    assert WorkflowEventType.STAGE_WORKSPACE_RECONSTRUCTION_STARTED.value not in events
    assert (workspace / "src" / "app.ts").read_text(encoding="utf-8") == original
    session.close()
    engine.dispose()


def _seed_apply_authority(
    factory,
    tmp_path: Path,
    *,
    attempt_status: str = "waiting_g10",
    files: dict[str, str] | None = None,
):
    files = files or {"src/app.ts": "old"}
    artifacts = tmp_path / "artifacts"
    stages = tmp_path / "stages"
    workspace = stages / "workspace"
    checkpoint_dir = stages / "ckpt-pre"
    _tree(workspace, files)
    _tree(checkpoint_dir, files)
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
        g10_gate_package_id="gate-10",
        risk_level="low",
        diagnosis="repairable_source; checkpoint=ckpt-pre",
        checkpoint_id="ckpt-pre",
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
        pre_fingerprint=fingerprint,
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
        workspace_fingerprint=fingerprint,
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
    session.add_all([run, plan, binding, continuation, attempt, checkpoint, gate, decision])
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


def test_apply_recovery_writes_ledger_with_attempt_reference(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, workspace, _artifacts, _stages = _seed_apply_authority(factory, tmp_path)
    mutated = workspace / "src" / "app.ts"
    mutated.write_text("mutated", encoding="utf-8")

    _orchestrator(factory)._recover_failed_apply(
        "cont-1",
        str(workspace),
        mutation_started=True,
        apply_claimed=True,
    )

    session = factory()
    assert mutated.read_text(encoding="utf-8") == "old"
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.status == "apply_recovery_required"
    binding = session.get(StageWorkspaceBindingModel, "binding-1")
    records = session.query(StageReconstructionRecordModel).all()
    assert len(records) == 1
    record = records[0]
    assert record.reason == "apply_recovery"
    assert record.checkpoint_id == "ckpt-pre"
    assert record.attempt_id == attempt_id
    assert record.source_workspace_fingerprint == attempt.pre_fingerprint
    assert record.restored_workspace_fingerprint == binding.workspace_fingerprint
    assert binding.workspace_fingerprint == attempt.post_fingerprint
    events = {
        event.event_type
        for event in session.query(WorkflowEventModel).filter(WorkflowEventModel.run_id == "run-1")
    }
    assert WorkflowEventType.STAGE_WORKSPACE_RECONSTRUCTION_STARTED.value in events
    assert WorkflowEventType.STAGE_WORKSPACE_RECONSTRUCTED.value in events
    session.close()
    engine.dispose()


def test_apply_repair_locked_recovery_writes_ledger_and_emits_events(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, workspace, _artifacts, _stages = _seed_apply_authority(
        factory, tmp_path, attempt_status="applying"
    )

    _orchestrator(factory)._apply_repair_locked("cont-1", "worker-1")

    session = factory()
    assert (workspace / "src" / "app.ts").read_text(encoding="utf-8") == "new"
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.status == "applied"
    records = session.query(StageReconstructionRecordModel).all()
    assert len(records) == 1
    record = records[0]
    assert record.reason == "apply_recovery"
    assert record.checkpoint_id == "ckpt-pre"
    assert record.attempt_id == attempt_id
    assert record.restored_workspace_fingerprint == STAGE_FINGERPRINT_PROFILE.fingerprint(
        _stages / "ckpt-pre"
    )
    events = {
        event.event_type: event
        for event in session.query(WorkflowEventModel)
        .filter(WorkflowEventModel.run_id == "run-1")
        .order_by(WorkflowEventModel.sequence)
    }
    assert WorkflowEventType.STAGE_WORKSPACE_RECONSTRUCTION_STARTED.value in events
    reconstructed = events[WorkflowEventType.STAGE_WORKSPACE_RECONSTRUCTED.value]
    assert reconstructed.payload["restored_workspace_fingerprint"] == record.restored_workspace_fingerprint
    session.close()
    engine.dispose()


def _seed_angular_restore(
    factory,
    tmp_path: Path,
    *,
    execution_checkpoint_id: str | None = "ckpt-ref",
):
    artifacts = tmp_path / "artifacts"
    stages = tmp_path / "stages"
    workspace = stages / "workspace"
    referenced = stages / "ckpt-ref"
    newer = stages / "ckpt-new"
    _tree(workspace, {"src/app.ts": "mutated"})
    _tree(referenced, {"src/app.ts": "A"})
    _tree(newer, {"src/app.ts": "B"})
    fingerprint = STAGE_FINGERPRINT_PROFILE.fingerprint(referenced)
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
        current_node="classify_failure",
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
    execution = CommandExecutionModel(
        id="exec-1",
        run_id="run-1",
        stage_id="stage-1",
        command_id="angular-update-exact",
        status="failed",
        failure_code="COMMAND_EXIT_NONZERO",
        failure_message="ng update failed",
        executable="npx",
        arguments=[],
        requested_at=NOW,
        state_version=1,
        attempt_number=1,
        operation_kind="mutating",
        checkpoint_id=execution_checkpoint_id,
    )
    step = StageStepModel(
        id="step-1",
        run_id="run-1",
        stage_id="stage-1",
        name="angular_update-0",
        status="FAILED",
        component_type="command",
        execution_id=execution.id,
        state_version=1,
        updated_at=NOW,
    )
    session.add_all([run, binding, continuation, execution, step])
    session.add_all(
        [
            StageCheckpointModel(
                id="ckpt-ref",
                run_id="run-1",
                stage_id="stage-1",
                kind="pre_angular_update",
                sequence=1,
                workspace_alias="STAGE_WORKSPACE_1",
                workspace_path=str(referenced),
                workspace_fingerprint=fingerprint,
                safe_for_resume=True,
                sealed=False,
                state_version=3,
                created_at=NOW,
            ),
            StageCheckpointModel(
                id="ckpt-new",
                run_id="run-1",
                stage_id="stage-1",
                kind="pre_angular_update",
                sequence=2,
                workspace_alias="STAGE_WORKSPACE_1",
                workspace_path=str(newer),
                workspace_fingerprint=STAGE_FINGERPRINT_PROFILE.fingerprint(newer),
                safe_for_resume=True,
                sealed=False,
                state_version=3,
                created_at=NOW,
            ),
        ]
    )
    session.commit()
    session.close()
    return workspace, referenced, newer, fingerprint


def test_restore_angular_update_checkpoint_uses_referenced_checkpoint_not_newest(tmp_path: Path):
    engine, factory = _database(tmp_path)
    workspace, _referenced, newer, fingerprint = _seed_angular_restore(factory, tmp_path)

    orchestrator = _orchestrator(factory)
    with _scope(factory)() as session:
        continuation = session.get(TransformationContinuationModel, "cont-1")
        checkpoint_id, restored = orchestrator._restore_angular_update_checkpoint(
            session, continuation
        )

    assert checkpoint_id == "ckpt-ref"
    assert restored == fingerprint
    assert (workspace / "src" / "app.ts").read_text(encoding="utf-8") == "A"
    session = factory()
    records = session.query(StageReconstructionRecordModel).all()
    assert len(records) == 1
    assert records[0].checkpoint_id == "ckpt-ref"
    assert records[0].reason == "angular_update_recovery"
    assert records[0].restored_workspace_fingerprint == fingerprint
    binding = session.get(StageWorkspaceBindingModel, "binding-1")
    assert binding.workspace_fingerprint == fingerprint
    events = {
        event.event_type
        for event in session.query(WorkflowEventModel).filter(WorkflowEventModel.run_id == "run-1")
    }
    assert WorkflowEventType.STAGE_WORKSPACE_RECONSTRUCTION_STARTED.value in events
    assert WorkflowEventType.STAGE_WORKSPACE_RECONSTRUCTED.value in events
    session.close()
    engine.dispose()


def test_restore_angular_update_checkpoint_missing_reference_blocks_explicitly(tmp_path: Path):
    engine, factory = _database(tmp_path)
    workspace, _referenced, newer, _fingerprint = _seed_angular_restore(
        factory, tmp_path, execution_checkpoint_id=None
    )

    orchestrator = _orchestrator(factory)
    with _scope(factory)() as session:
        continuation = session.get(TransformationContinuationModel, "cont-1")
        with pytest.raises(TransformerStageError) as raised:
            orchestrator._restore_angular_update_checkpoint(session, continuation)

    assert raised.value.code == "CHECKPOINT_MISSING"
    assert (workspace / "src" / "app.ts").read_text(encoding="utf-8") == "mutated"
    session = factory()
    assert session.query(StageReconstructionRecordModel).count() == 0
    session.close()
    engine.dispose()


def test_prepare_rejects_existing_workspace_mismatching_durable_binding(tmp_path: Path):
    baseline = tmp_path / "baseline"
    stages = tmp_path / "stages"
    _tree(baseline, {"package.json": "{}"})
    target = stages / "stage-1"
    _tree(target, {"package.json": '{"name":"mutated"}'})
    durable = STAGE_FINGERPRINT_PROFILE.fingerprint(baseline)
    assert durable != STAGE_FINGERPRINT_PROFILE.fingerprint(target)

    with pytest.raises(StagePreparationError) as raised:
        StagePreparationApplicationService().prepare(
            {"BASELINE_SANDBOX": str(baseline), "STAGE_SANDBOX": str(stages)},
            "stage-1",
            expected_fingerprint=durable,
        )

    assert raised.value.code == "STAGE_WORKSPACE_FINGERPRINT_MISMATCH"
    validated = SimpleNamespace(
        aliases={"BASELINE_SANDBOX": str(baseline), "STAGE_SANDBOX": str(stages)},
        stage_id="stage-1",
    )
    from app.services.stage_execution_application_service import StageExecutionError

    with pytest.raises(StageExecutionError) as wired:
        StageExecutionApplicationService()._prepare_workspace(validated, expected_fingerprint=durable)
    assert wired.value.code == "STAGE_WORKSPACE_FINGERPRINT_MISMATCH"

    replay = StagePreparationApplicationService().prepare(
        {"BASELINE_SANDBOX": str(baseline), "STAGE_SANDBOX": str(stages)},
        "stage-1",
        expected_fingerprint=STAGE_FINGERPRINT_PROFILE.fingerprint(target),
    )
    assert replay.created is False


def _seed_prepare(factory, tmp_path: Path, *, target_files: dict[str, str], binding_fingerprint: str):
    baseline = tmp_path / "baseline"
    stages = tmp_path / "stages"
    artifacts = tmp_path / "artifacts" / "run-1"
    _tree(baseline, {"package.json": '{"name":"baseline"}'})
    _tree(stages / "stage-1", target_files)
    artifacts.mkdir(parents=True)
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
    binding = StageWorkspaceBindingModel(
        id="binding-1",
        run_id="run-1",
        stage_id="stage-1",
        alias="STAGE_WORKSPACE_1",
        workspace_path=str(stages / "stage-1"),
        workspace_fingerprint=binding_fingerprint,
        active=True,
        created_at=NOW,
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
    session.add_all(
        [
            run,
            plan,
            stage_plan,
            gate,
            binding,
            continuation,
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
    session.commit()
    session.close()
    return stages / "stage-1"


def test_transformer_prepare_rejects_existing_workspace_mismatching_durable_binding(tmp_path: Path):
    engine, factory = _database(tmp_path)
    baseline = tmp_path / "baseline"
    _tree(baseline, {"package.json": '{"name":"baseline"}'})
    binding_fingerprint = STAGE_FINGERPRINT_PROFILE.fingerprint(baseline)
    target = _seed_prepare(
        factory,
        tmp_path,
        target_files={"package.json": '{"name":"mutated"}'},
        binding_fingerprint=binding_fingerprint,
    )
    original = (target / "package.json").read_text(encoding="utf-8")

    with pytest.raises(TransformerStageError) as raised:
        _orchestrator(factory).advance("cont-1", "worker-1")

    assert raised.value.code == "STAGE_WORKSPACE_FINGERPRINT_MISMATCH"
    assert (target / "package.json").read_text(encoding="utf-8") == original
    session = factory()
    binding = session.get(StageWorkspaceBindingModel, "binding-1")
    assert binding.active is True
    session.close()
    engine.dispose()


def test_only_one_sealed_checkpoint_per_stage_at_db_level(tmp_path: Path):
    engine, factory = _database(tmp_path)
    session = factory()
    session.add(MigrationRunModel(
        id="run-1",
        status="STAGE_CREATED",
        run_phase="STAGED_MIGRATION",
        state_version=7,
        created_at=NOW,
        updated_at=NOW,
    ))
    session.add(MigrationStageModel(
        id="stage-1",
        run_id="run-1",
        stage_order=1,
        status="running",
        created_at=NOW,
    ))
    session.commit()
    session.close()

    with pytest.raises(IntegrityError):
        session = factory()
        session.add_all(
            [
                StageCheckpointModel(
                    id="seal-a",
                    run_id="run-1",
                    stage_id="stage-1",
                    kind="sealed_output",
                    sequence=1,
                    workspace_alias="SEALED",
                    workspace_path=str(tmp_path / "a"),
                    workspace_fingerprint="sha256:1",
                    safe_for_resume=True,
                    sealed=True,
                    state_version=7,
                    created_at=NOW,
                ),
                StageCheckpointModel(
                    id="seal-b",
                    run_id="run-1",
                    stage_id="stage-1",
                    kind="sealed_output",
                    sequence=2,
                    workspace_alias="SEALED",
                    workspace_path=str(tmp_path / "b"),
                    workspace_fingerprint="sha256:2",
                    safe_for_resume=True,
                    sealed=True,
                    state_version=7,
                    created_at=NOW,
                ),
            ]
        )
        session.commit()
    engine.dispose()


def _fake_artifact(artifact_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        ref=SimpleNamespace(
            artifact_id=artifact_id,
            artifact_type=ArtifactType.JSON,
            relative_path=f"04_workflow_state/{artifact_id}.json",
            checksum="sha256:" + artifact_id,
            created_at=NOW,
        ),
        envelope=SimpleNamespace(schema_version=1),
        content="{}",
    )


def _seed_seal(factory, tmp_path: Path):
    artifacts = tmp_path / "artifacts"
    session = factory()
    run = MigrationRunModel(
        id="run-1",
        status="STAGE_CREATED",
        run_phase="STAGED_MIGRATION",
        state_version=7,
        run_root=str(tmp_path),
        artifact_root=str(artifacts),
        workspace_aliases={"STAGE_SANDBOX": str(tmp_path / "stages")},
        created_at=NOW,
        updated_at=NOW,
    )
    stage = MigrationStageModel(
        id="stage-1",
        run_id="run-1",
        stage_order=1,
        status="running",
        created_at=NOW,
    )
    continuation = TransformationContinuationModel(
        id="cont-1",
        run_id="run-1",
        current_stage_id="stage-1",
        thread_id="thread-1",
        status="running",
        current_node="seal_stage",
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
    gate = StageGatePackageModel(
        id="gate-12",
        run_id="run-1",
        stage_id="stage-1",
        gate_id="G12",
        gate_version=1,
        status="approved",
        package_artifact_id="artifact-g12",
        package_checksum="sha256:g12",
        artifact_set_checksum="sha256:g12-set",
        plan_id="plan-1",
        plan_version=1,
        stage_plan_id="stage-plan-1",
        stage_plan_checksum="sha256:stage-plan",
        workspace_fingerprint="sha256:workspace",
        expected_state_version=3,
        created_at=NOW,
    )
    session.add_all([run, stage, continuation, gate])
    session.commit()
    session.close()


def test_seal_flow_reuses_existing_seal_when_concurrent_insert_loses(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _seed_seal(factory, tmp_path)
    scope = _scope(factory)
    sealing = MagicMock()
    sealing.context.return_value = {
        "run_id": "run-1",
        "stage_id": "stage-1",
        "stage_plan_checksum": "sha256:stage-plan",
        "workspace_path": str(tmp_path / "stages" / "workspace"),
        "workspace_fingerprint": "sha256:workspace",
        "artifact_root": str(tmp_path / "artifacts"),
        "stage_root": str(tmp_path / "stages"),
        "g09_package_checksum": "sha256:g09",
        "g09_workspace_fingerprint": "sha256:workspace",
        "previous_chain_hash": "genesis",
        "validation_summary_checksum": "sha256:validation",
        "evidence_index": [],
    }
    sealing.seal.return_value = (
        str(tmp_path / "stages" / "sealed"),
        "sha256:sealed",
        "sha256:chain",
        _fake_artifact("seal-output"),
        _fake_artifact("seal-seal"),
    )
    flow = TransformerSealingFlow(
        scope=scope,
        stage_service=TransformerStageService(scope=scope, now_provider=lambda: NOW),
        gate_service=MagicMock(),
        sealing_service=sealing,
    )
    flow.seal("cont-1", "worker-1")

    with scope() as session:
        continuation = session.get(TransformationContinuationModel, "cont-1")
        continuation.status = "running"
        continuation.worker_id = "worker-1"
        continuation.current_node = "seal_stage"
        assert session.query(StageCheckpointModel).filter(StageCheckpointModel.sealed.is_(True)).count() == 1

    stale = {"hits": 0}

    @contextmanager
    def stale_scope():
        session = factory()
        real_scalar = session.scalar

        def scalar(query, *a, **k):
            if stale["hits"] < 2 and "stage_checkpoints" in str(query):
                stale["hits"] += 1
                return None
            return real_scalar(query, *a, **k)

        session.scalar = scalar  # type: ignore[method-assign]
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    flow.seal("cont-1", "worker-1")

    with scope() as session:
        sealed = session.query(StageCheckpointModel).filter(StageCheckpointModel.sealed.is_(True)).all()
        assert len(sealed) == 1
        continuation = session.get(TransformationContinuationModel, "cont-1")
        assert continuation.status == "queued"
        assert continuation.current_node == "materialize_next_stage"
    engine.dispose()


def test_checkpoint_sequence_allocation_survives_concurrent_creation(tmp_path: Path):
    engine, factory = _database(tmp_path, threaded=True)
    session = factory()
    session.add(MigrationRunModel(
        id="run-1",
        status="STAGE_CREATED",
        run_phase="STAGED_MIGRATION",
        state_version=7,
        created_at=NOW,
        updated_at=NOW,
    ))
    session.add(
        StageCheckpointModel(
            id="ckpt-5",
            run_id="run-1",
            stage_id="stage-1",
            kind="pre_bootstrap",
            sequence=5,
            workspace_alias="STAGE_WORKSPACE_1",
            workspace_path=str(tmp_path / "workspace"),
            workspace_fingerprint="sha256:1",
            safe_for_resume=True,
            sealed=False,
            state_version=3,
            created_at=NOW,
        )
    )
    session.commit()
    session.close()

    service = TransformerStageService(now_provider=lambda: NOW)
    continuation = SimpleNamespace(run_id="run-1", current_stage_id="stage-1", state_version=3)
    preparation = SimpleNamespace(
        workspace_alias="STAGE_WORKSPACE_1",
        workspace_path=str(tmp_path / "workspace"),
        fingerprint="sha256:workspace",
    )
    barrier = threading.Barrier(2)
    states: dict[str, dict[str, bool]] = {name: {"patched": False} for name in ("a", "b")}
    originals: dict[str, object] = {}

    def run(name: str) -> None:
        thread_session = factory()
        originals[name] = thread_session.scalar
        real_scalar = originals[name]

        def scalar(query, *a, **k):
            if not states[name]["patched"] and "stage_checkpoints" in str(query):
                states[name]["patched"] = True
                barrier.wait(timeout=30)
            return real_scalar(query, *a, **k)

        thread_session.scalar = scalar  # type: ignore[method-assign]
        try:
            checkpoint = service._checkpoint(
                thread_session, continuation, preparation, "pre_repair", "manifest-1", "checksum-1"
            )
            thread_session.commit()
            states[name]["sequence"] = checkpoint.sequence
        finally:
            thread_session.close()

    threads = [threading.Thread(target=run, args=(name,)) for name in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    sequences = sorted(states[name]["sequence"] for name in ("a", "b"))
    assert sequences == [6, 7]
    session = factory()
    rows = session.query(StageCheckpointModel).filter(
        StageCheckpointModel.stage_id == "stage-1"
    ).order_by(StageCheckpointModel.sequence).all()
    assert [row.sequence for row in rows] == [5, 6, 7]
    session.close()
    engine.dispose()
