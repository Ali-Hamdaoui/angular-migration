"""CR-05: successor-stage reconstruction from the immutable sealed input.

A lightweight stage checkpoint (``snapshot_workspace``) persists only a
fingerprint and keeps ``workspace_path`` pointing at the mutable live stage
workspace.  Once the stage has legitimately changed, that tree can no longer
reproduce the checkpoint's persisted fingerprint, so recovery must materialize
the immutable stage-start source (the previous stage's sealed output,
``BASELINE_SANDBOX``) instead of treating the mutated live workspace as its
own authority.

These tests prove:
- a mutated successor workspace is reconstructed from the immutable baseline;
- a tampered or missing baseline fails closed;
- reconstruction is idempotent (no second ledger row on replay);
- the npm EBUSY/EPERM + native-binary ENOENT signature is a bounded
  environment/install transient.
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
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app.domain.transformation import FailureRoute
from app.orchestration.transformer_graph import TransformerOrchestrator
from app.repositories.models import (
    CommandExecutionModel,
    CommandLogChunkModel,
    MigrationRunModel,
    StageCheckpointModel,
    StageReconstructionRecordModel,
    StageStepModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
)
from app.repositories.models.base import Base
from app.services.failure_evidence_service import FailureEvidenceService
from app.services.patch_apply_service import PatchApplyService
from app.services.transformer_stage_service import TransformerStageError, TransformerStageService
from app.services.workspace_fingerprint import STAGE_FINGERPRINT_PROFILE

NOW = datetime(2026, 8, 1, tzinfo=UTC)


def _database(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'state.db'}", connect_args={"check_same_thread": False})

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


def _tree(root: Path, files: dict[str, str]) -> None:
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _orchestrator(factory, *, scope=None, stage_service=None):
    scope = scope or _scope(factory)
    return TransformerOrchestrator(
        scope=scope,
        stage_service=stage_service or TransformerStageService(scope=scope, now_provider=lambda: NOW),
        gate_service=SimpleNamespace(_validate_repair_lineage=lambda *args, **kwargs: None),
        transformation_evidence=MagicMock(),
        prompt_explainer=MagicMock(),
        validation_runner=MagicMock(),
        failure_evidence=FailureEvidenceService(now_provider=lambda: NOW),
        repair_service=MagicMock(),
        patch_service=PatchApplyService(now_provider=lambda: NOW),
        sealing_flow=MagicMock(),
    )


_STAGE_START_FILES = {"package.json": '{"name": "app"}'}


def _seed_successor(
    factory,
    tmp_path: Path,
    *,
    baseline_files: dict[str, str] | None = None,
    workspace_files: dict[str, str] | None = None,
    provide_baseline: bool = True,
):
    """Seed a successor stage with a lightweight pre_angular_update checkpoint.

    The checkpoint's ``workspace_path`` is the mutable live workspace; the
    immutable stage-start source is ``BASELINE_SANDBOX`` (previous sealed
    output).  The live workspace is seeded MUTATED so it diverges from the
    persisted checkpoint fingerprint.
    """
    baseline_files = baseline_files if baseline_files is not None else _STAGE_START_FILES
    workspace_files = workspace_files if workspace_files is not None else {"package.json": '{"name": "mutated"}'}
    stages = tmp_path / "stages"
    artifacts = tmp_path / "artifacts"
    baseline = stages / ".sealed" / "prev-stage"
    workspace = stages / "stage-2"
    _tree(baseline, baseline_files)
    _tree(workspace, workspace_files)
    baseline_fingerprint = STAGE_FINGERPRINT_PROFILE.fingerprint(baseline)
    workspace_fingerprint = STAGE_FINGERPRINT_PROFILE.fingerprint(workspace)
    assert baseline_fingerprint != workspace_fingerprint

    session = factory()
    run = MigrationRunModel(
        id="run-1",
        status="STAGE_CREATED",
        run_phase="STAGED_MIGRATION",
        phase_status="running",
        state_version=7,
        run_root=str(tmp_path),
        artifact_root=str(artifacts),
        workspace_aliases={
            "BASELINE_SANDBOX": str(baseline) if provide_baseline else str(stages / "missing"),
            "STAGE_SANDBOX": str(stages),
        },
        created_at=NOW,
        updated_at=NOW,
    )
    binding = StageWorkspaceBindingModel(
        id="binding-1",
        run_id="run-1",
        stage_id="stage-2",
        alias="STAGE_WORKSPACE_2",
        workspace_path=str(workspace),
        workspace_fingerprint=baseline_fingerprint,
        input_fingerprint=baseline_fingerprint,
        fingerprint_profile_id=STAGE_FINGERPRINT_PROFILE.profile_id,
        active=True,
        created_at=NOW,
    )
    continuation = TransformationContinuationModel(
        id="cont-1",
        run_id="run-1",
        current_stage_id="stage-2",
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
        attempt=0,
        max_attempts=3,
        created_at=NOW,
        updated_at=NOW,
    )
    execution = CommandExecutionModel(
        id="exec-1",
        run_id="run-1",
        stage_id="stage-2",
        command_id="npm-ci-final",
        status="failed",
        failure_code="COMMAND_EXIT_NONZERO",
        failure_message="npm install failed",
        executable="npm",
        arguments=["ci"],
        requested_at=NOW,
        state_version=1,
        attempt_number=1,
        operation_kind="mutating",
        checkpoint_id="ckpt-lightweight",
    )
    step = StageStepModel(
        id="step-1",
        run_id="run-1",
        stage_id="stage-2",
        name="angular_update-23",
        status="FAILED",
        component_type="command",
        execution_id=execution.id,
        state_version=1,
        updated_at=NOW,
    )
    checkpoint = StageCheckpointModel(
        id="ckpt-lightweight",
        run_id="run-1",
        stage_id="stage-2",
        kind="pre_angular_update",
        sequence=3,
        workspace_alias="STAGE_WORKSPACE_2",
        workspace_path=str(workspace),
        workspace_fingerprint=baseline_fingerprint,
        safe_for_resume=True,
        sealed=False,
        state_version=3,
        created_at=NOW,
    )
    session.add_all([run, binding, continuation, execution, step, checkpoint])
    session.commit()
    session.close()
    return workspace, baseline, baseline_fingerprint


def test_baseline_reconstruction_source_returns_sealed_source_when_authoritative(tmp_path: Path):
    engine, factory = _database(tmp_path)
    workspace, baseline, fingerprint = _seed_successor(factory, tmp_path)
    with _scope(factory)() as session:
        continuation = session.get(TransformationContinuationModel, "cont-1")
        checkpoint = session.get(StageCheckpointModel, "ckpt-lightweight")
        source = TransformerStageService().baseline_reconstruction_source(
            session, continuation, checkpoint
        )
    assert source == str(baseline)
    engine.dispose()


def test_baseline_reconstruction_source_none_when_baseline_tampered(tmp_path: Path):
    engine, factory = _database(tmp_path)
    workspace, baseline, _fingerprint = _seed_successor(factory, tmp_path)
    (baseline / "package.json").write_text('{"name": "tampered"}', encoding="utf-8")
    with _scope(factory)() as session:
        continuation = session.get(TransformationContinuationModel, "cont-1")
        checkpoint = session.get(StageCheckpointModel, "ckpt-lightweight")
        source = TransformerStageService().baseline_reconstruction_source(
            session, continuation, checkpoint
        )
    assert source is None
    engine.dispose()


def test_baseline_reconstruction_source_none_when_baseline_missing(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _workspace, _baseline, _fingerprint = _seed_successor(factory, tmp_path, provide_baseline=False)
    with _scope(factory)() as session:
        continuation = session.get(TransformationContinuationModel, "cont-1")
        checkpoint = session.get(StageCheckpointModel, "ckpt-lightweight")
        source = TransformerStageService().baseline_reconstruction_source(
            session, continuation, checkpoint
        )
    assert source is None
    engine.dispose()


def test_restore_angular_update_checkpoint_reconstructs_from_baseline(tmp_path: Path):
    engine, factory = _database(tmp_path)
    workspace, _baseline, fingerprint = _seed_successor(factory, tmp_path)
    orchestrator = _orchestrator(factory)
    with _scope(factory)() as session:
        continuation = session.get(TransformationContinuationModel, "cont-1")
        checkpoint_id, restored = orchestrator._restore_angular_update_checkpoint(
            session, continuation
        )
    assert checkpoint_id == "ckpt-lightweight"
    assert restored == fingerprint
    assert (workspace / "package.json").read_text(encoding="utf-8") == '{"name": "app"}'
    session = factory()
    records = session.query(StageReconstructionRecordModel).all()
    assert len(records) == 1
    assert records[0].checkpoint_id == "ckpt-lightweight"
    assert records[0].reason == "angular_update_recovery"
    assert records[0].source_workspace_fingerprint == fingerprint
    binding = session.get(StageWorkspaceBindingModel, "binding-1")
    assert binding.workspace_fingerprint == fingerprint
    session.close()
    engine.dispose()


def test_restore_angular_update_checkpoint_tampered_baseline_fails_closed(tmp_path: Path):
    engine, factory = _database(tmp_path)
    workspace, baseline, _fingerprint = _seed_successor(factory, tmp_path)
    (baseline / "package.json").write_text('{"name": "tampered"}', encoding="utf-8")
    orchestrator = _orchestrator(factory)
    with _scope(factory)() as session:
        continuation = session.get(TransformationContinuationModel, "cont-1")
        with pytest.raises(TransformerStageError) as raised:
            orchestrator._restore_angular_update_checkpoint(session, continuation)
    assert raised.value.code == "CHECKPOINT_INTEGRITY_FAILED"
    assert (workspace / "package.json").read_text(encoding="utf-8") == '{"name": "mutated"}'
    session = factory()
    assert session.query(StageReconstructionRecordModel).count() == 0
    session.close()
    engine.dispose()


def test_restore_angular_update_checkpoint_missing_baseline_fails_closed(tmp_path: Path):
    engine, factory = _database(tmp_path)
    workspace, _baseline, _fingerprint = _seed_successor(factory, tmp_path, provide_baseline=False)
    orchestrator = _orchestrator(factory)
    with _scope(factory)() as session:
        continuation = session.get(TransformationContinuationModel, "cont-1")
        with pytest.raises(TransformerStageError) as raised:
            orchestrator._restore_angular_update_checkpoint(session, continuation)
    assert raised.value.code == "CHECKPOINT_INTEGRITY_FAILED"
    assert (workspace / "package.json").read_text(encoding="utf-8") == '{"name": "mutated"}'
    session = factory()
    assert session.query(StageReconstructionRecordModel).count() == 0
    session.close()
    engine.dispose()


def test_restore_angular_update_checkpoint_is_idempotent(tmp_path: Path):
    engine, factory = _database(tmp_path)
    workspace, _baseline, fingerprint = _seed_successor(factory, tmp_path)
    orchestrator = _orchestrator(factory)
    with _scope(factory)() as session:
        continuation = session.get(TransformationContinuationModel, "cont-1")
        orchestrator._restore_angular_update_checkpoint(session, continuation)
    with _scope(factory)() as session:
        continuation = session.get(TransformationContinuationModel, "cont-1")
        checkpoint_id, restored = orchestrator._restore_angular_update_checkpoint(
            session, continuation
        )
    assert checkpoint_id == "ckpt-lightweight"
    assert restored == fingerprint
    assert (workspace / "package.json").read_text(encoding="utf-8") == '{"name": "app"}'
    session = factory()
    assert session.query(StageReconstructionRecordModel).count() == 1
    session.close()
    engine.dispose()


def test_is_npm_install_transient_matches_lock_and_missing_binary():
    normalized = {"command_id": "npm-ci-final"}
    stderr = (
        "npm WARN cleanup Failed to remove some directories [\n"
        "npm WARN cleanup [Error: EBUSY: resource busy or locked, rmdir 'node_modules\\\\esbuild']\n"
        "npm ERR! Error: spawnSync C:\\...\\node_modules\\@esbuild\\win32-x64\\esbuild.exe ENOENT\n"
    )
    assert FailureEvidenceService.is_npm_install_transient(normalized, stderr) is True


def test_is_npm_install_transient_ignores_non_install_and_application_errors():
    assert (
        FailureEvidenceService.is_npm_install_transient({"command_id": "angular-update-exact"}, "EBUSY ENOENT")
        is False
    )
    assert (
        FailureEvidenceService.is_npm_install_transient(
            {"command_id": "npm-ci-final"}, "TypeError: Cannot read properties of undefined"
        )
        is False
    )


def _seed_classify_transient(factory, tmp_path: Path):
    """Seed a successor stage ready for _classify_failure of a transient npm install."""
    from app.repositories.models import StageExecutionPlanModel

    stages = tmp_path / "stages"
    artifacts = tmp_path / "artifacts"
    baseline = stages / ".sealed" / "prev-stage"
    workspace = stages / "stage-2"
    _tree(baseline, _STAGE_START_FILES)
    _tree(workspace, {"package.json": '{"name": "mutated"}'})
    baseline_fingerprint = STAGE_FINGERPRINT_PROFILE.fingerprint(baseline)

    session = factory()
    run = MigrationRunModel(
        id="run-1",
        status="STAGE_CREATED",
        run_phase="STAGED_MIGRATION",
        phase_status="running",
        state_version=7,
        run_root=str(tmp_path),
        artifact_root=str(artifacts),
        workspace_aliases={"BASELINE_SANDBOX": str(baseline), "STAGE_SANDBOX": str(stages)},
        created_at=NOW,
        updated_at=NOW,
    )
    stage_plan = StageExecutionPlanModel(
        id="stage-plan-1",
        run_id="run-1",
        migration_plan_id="plan-1",
        stage_id="stage-2",
        idempotency_key="stage-plan",
        request_checksum="sha256:stage-plan",
        actor="operator",
        correlation_id="corr-1",
        status="approved",
        version=1,
        stage_plan={"repair_policy": {"max_attempts": 3}},
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
        stage_id="stage-2",
        alias="STAGE_WORKSPACE_2",
        workspace_path=str(workspace),
        workspace_fingerprint=baseline_fingerprint,
        input_fingerprint=baseline_fingerprint,
        fingerprint_profile_id=STAGE_FINGERPRINT_PROFILE.profile_id,
        active=True,
        created_at=NOW,
    )
    continuation = TransformationContinuationModel(
        id="cont-1",
        run_id="run-1",
        current_stage_id="stage-2",
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
        last_error_code="COMMAND_EXIT_NONZERO",
        state_version=3,
        attempt=0,
        max_attempts=3,
        created_at=NOW,
        updated_at=NOW,
    )
    execution = CommandExecutionModel(
        id="exec-1",
        run_id="run-1",
        stage_id="stage-2",
        command_id="npm-ci-final",
        status="failed",
        failure_code="COMMAND_EXIT_NONZERO",
        failure_message="npm install failed",
        executable="npm",
        arguments=["ci"],
        requested_at=NOW,
        state_version=1,
        attempt_number=1,
        operation_kind="mutating",
        checkpoint_id="ckpt-lightweight",
    )
    step = StageStepModel(
        id="step-1",
        run_id="run-1",
        stage_id="stage-2",
        name="angular_update-23",
        status="FAILED",
        component_type="command",
        execution_id=execution.id,
        state_version=1,
        updated_at=NOW,
    )
    checkpoint = StageCheckpointModel(
        id="ckpt-lightweight",
        run_id="run-1",
        stage_id="stage-2",
        kind="pre_angular_update",
        sequence=3,
        workspace_alias="STAGE_WORKSPACE_2",
        workspace_path=str(workspace),
        workspace_fingerprint=baseline_fingerprint,
        safe_for_resume=True,
        sealed=False,
        state_version=3,
        created_at=NOW,
    )
    session.add_all([run, stage_plan, binding, continuation, execution, step, checkpoint])
    session.add(
        CommandLogChunkModel(
            id="logchunk-1",
            execution_id=execution.id,
            run_id="run-1",
            sequence=1,
            stream="stderr",
            text=(
                "npm WARN cleanup Failed to remove some directories [\n"
                "npm WARN cleanup [Error: EBUSY: resource busy or locked, "
                "rmdir 'node_modules\\\\esbuild']\n"
                "npm ERR! Error: spawnSync C:\\...\\node_modules\\@esbuild\\win32-x64\\esbuild.exe ENOENT\n"
            ),
            redacted=False,
            truncated=False,
            byte_count=0,
            character_count=0,
            created_at=NOW,
        )
    )
    session.commit()
    session.close()
    return workspace, baseline_fingerprint


def test_classify_failure_transient_reconstructs_and_retries_angular_update(tmp_path: Path):
    engine, factory = _database(tmp_path)
    workspace, fingerprint = _seed_classify_transient(factory, tmp_path)
    orchestrator = _orchestrator(factory)

    orchestrator._classify_failure("cont-1", "worker-1")

    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "queued"
    assert continuation.current_node == "angular_update"
    assert continuation.attempt == 1
    binding = session.get(StageWorkspaceBindingModel, "binding-1")
    assert binding.workspace_fingerprint == fingerprint
    assert (workspace / "package.json").read_text(encoding="utf-8") == '{"name": "app"}'
    failed = session.get(CommandExecutionModel, "exec-1")
    assert failed.status == "failed"
    assert failed.attempt_number == 1
    records = session.query(StageReconstructionRecordModel).all()
    assert len(records) == 1
    assert records[0].reason == "angular_update_recovery"
    assert records[0].source_workspace_fingerprint == fingerprint
    session.close()
    engine.dispose()


def test_classify_routes_npm_install_transient_to_environment_transient():
    evidence = {
        "failure_fingerprint": "sha256:abc",
        "prior_fingerprints": [],
        "normalized_failure": {"command_id": "npm-ci-final", "error_code": "COMMAND_EXIT_NONZERO"},
        "stderr_tail": (
            "npm WARN cleanup Failed to remove some directories\n"
            "npm WARN cleanup [Error: EPERM: operation not permitted, unlink 'node_modules']\n"
            "npm ERR! spawnSync node_modules\\esbuild.exe ENOENT\n"
        ),
    }
    assert FailureEvidenceService().classify(evidence) is FailureRoute.ENVIRONMENT_TRANSIENT


def test_classify_does_not_overmatch_install_enoent_without_cleanup_lock():
    evidence = {
        "failure_fingerprint": "sha256:abc",
        "prior_fingerprints": [],
        "normalized_failure": {"command_id": "npm-ci-final", "error_code": "COMMAND_EXIT_NONZERO"},
        "stderr_tail": "spawnSync some-tool.exe ENOENT",
    }
    assert FailureEvidenceService().classify(evidence) is FailureRoute.REPAIRABLE_SOURCE
