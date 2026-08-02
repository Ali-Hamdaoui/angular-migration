from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.orchestration.transformer_graph import TransformerOrchestrator
from app.repositories.models import (
    ArtifactMetadataModel,
    CommandExecutionModel,
    MigrationRunModel,
    RepairAttemptModel,
    StageCheckpointModel,
    StageExecutionPlanModel,
    StageStepModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
)
from app.repositories.models.base import Base
from app.services.failure_evidence_service import FailureEvidenceService
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.transformation_continuation_service import TransformationContinuationService
from app.services.transformer_stage_service import TransformerStageService

NOW = datetime(2026, 7, 31, tzinfo=UTC)


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


def _seed(
    factory,
    tmp_path: Path,
    *,
    stage_id: str = "stage-1",
    run_id: str = "run-1",
    angular: bool = True,
    failure_code: str | None = None,
):
    artifacts = tmp_path / "artifacts"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "package.json").write_text('{"name":"fixture"}', encoding="utf-8")
    (workspace / "package-lock.json").write_text("{}", encoding="utf-8")
    step_name = "angular_update-0" if angular else "bootstrap_install-0"
    error_code = failure_code or ("COMMAND_EXIT_NONZERO" if angular else "COMMAND_TIMEOUT")
    session = factory()
    run = MigrationRunModel(
        id=run_id,
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
        id=f"stage-plan-{stage_id}",
        run_id=run_id,
        migration_plan_id="plan-1",
        stage_id=stage_id,
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
    execution = CommandExecutionModel(
        id="exec-1",
        run_id=run_id,
        stage_id=stage_id,
        command_id="angular-update-exact",
        status="failed",
        failure_code=error_code,
        failure_message="ng update failed",
        executable="npx",
        arguments=[],
        requested_at=NOW,
        state_version=1,
        attempt_number=1,
        operation_kind="mutating",
        checkpoint_id="ckpt-pre",
    )
    step = StageStepModel(
        id="step-1",
        run_id=run_id,
        stage_id=stage_id,
        name=step_name,
        status="FAILED",
        component_type="command",
        execution_id=execution.id,
        state_version=1,
        updated_at=NOW,
    )
    binding = StageWorkspaceBindingModel(
        id="binding-1",
        run_id=run_id,
        stage_id=stage_id,
        alias=f"STAGE_WORKSPACE_{stage_id.upper()}",
        workspace_path=str(workspace),
        workspace_fingerprint="fingerprint-1",
        active=True,
        created_at=NOW,
    )
    continuation = TransformationContinuationModel(
        id="cont-1",
        run_id=run_id,
        current_stage_id=stage_id,
        thread_id="thread-1",
        status="running",
        current_node="classify_failure",
        worker_id="worker-1",
        lease_expires_at=NOW + timedelta(seconds=120),
        g06_approval_id="g06-1",
        plan_id="plan-1",
        plan_checksum="sha256:plan",
        stage_plan_id=f"stage-plan-{stage_id}",
        stage_plan_checksum="sha256:stage-plan",
        idempotency_key="continuation",
        request_checksum="sha256:continuation",
        state_version=3,
        attempt=1,
        max_attempts=3,
        last_error_code=error_code,
        last_error_message="ng update failed",
        created_at=NOW,
        updated_at=NOW,
    )
    session.add_all([run, plan, execution, step, binding, continuation])
    session.commit()
    session.close()
    return workspace, artifacts


def _orchestrator(factory, *, stage_service=None, failure_service=None):
    scope = _scope(factory)
    return TransformerOrchestrator(
        scope=scope,
        stage_service=stage_service or TransformerStageService(scope=scope),
        gate_service=MagicMock(),
        transformation_evidence=MagicMock(),
        prompt_explainer=MagicMock(),
        validation_runner=MagicMock(),
        failure_evidence=failure_service or FailureEvidenceService(),
        repair_service=MagicMock(),
        patch_service=MagicMock(),
        sealing_flow=MagicMock(),
    )


def _file_inventory(artifacts: Path) -> list[str]:
    return sorted(
        str(path.relative_to(artifacts)).replace("\\", "/") for path in artifacts.rglob("*") if path.is_file()
    )


class _DuplicatingStageService(TransformerStageService):
    """Simulates a legacy/foreign writer inserting the same metadata id twice.

    The pending-aware dedup in register_artifact already absorbs repeated calls
    through the service, so the duplicate is injected as two raw rows with the
    same deterministic id -- the exact historical defect shape that reaches the
    UNIQUE constraint in one executemany.
    """

    def register_artifact(self, session, stored, continuation):
        metadata_id = "metadata-" + stored.ref.artifact_id
        for _ in range(2):
            session.add(
                ArtifactMetadataModel(
                    id=metadata_id,
                    run_id=continuation.run_id,
                    stage_id=continuation.current_stage_id,
                    artifact_type=stored.ref.artifact_type.value,
                    relative_path=stored.ref.relative_path,
                    checksum=stored.ref.checksum,
                    schema_version=stored.envelope.schema_version,
                    created_at=stored.ref.created_at,
                    finalized_at=stored.ref.created_at,
                    immutable=True,
                    size_bytes=len(stored.content.encode("utf-8")),
                )
            )


class _FlakyStageService(TransformerStageService):
    def register_artifact(self, session, stored, continuation):
        raise RuntimeError("transient persistence hiccup")


class _RecordingFailureEvidence(FailureEvidenceService):
    def __init__(self, inner: FailureEvidenceService | None = None) -> None:
        super().__init__()
        self._inner = inner or FailureEvidenceService()
        self._recorded: tuple | None = None
        self._replay = False

    def enable_replay(self) -> None:
        self._replay = True

    def collect(self, session, continuation, *, prior_fingerprints=None):
        return self._inner.collect(session, continuation, prior_fingerprints=prior_fingerprints or [])

    def classify(self, evidence):
        return self._inner.classify(evidence)

    def write(self, evidence, route):
        if self._replay:
            raise AssertionError("fresh write on replay path")
        failure, route_artifact = self._inner.write(evidence, route)
        self._recorded = (failure, route_artifact, None)
        return failure, route_artifact

    def write_context_pack(self, evidence, failure_checksum):
        context = self._inner.write_context_pack(evidence, failure_checksum)
        if self._recorded is not None:
            self._recorded = (self._recorded[0], self._recorded[1], context)
        return context

    def committed_evidence(self, session, continuation, failure_fingerprint):
        if not self._replay:
            return None
        return self._recorded


def test_classify_failure_repairable_commits_exactly_three_metadata_rows_once(
    tmp_path: Path,
):
    engine, factory = _database(tmp_path)
    _workspace, artifacts = _seed(factory, tmp_path)

    _orchestrator(factory)._classify_failure("cont-1", "worker-1")

    session = factory()
    rows = session.query(ArtifactMetadataModel).filter_by(run_id="run-1").all()
    assert len(rows) == 3
    assert len({row.relative_path for row in rows}) == 3
    assert all(row.artifact_type == "json" for row in rows)
    attempts = session.query(RepairAttemptModel).filter_by(run_id="run-1").all()
    assert len(attempts) == 1
    cont = session.get(TransformationContinuationModel, "cont-1")
    assert cont.status == "queued"
    assert cont.current_node == "propose_repair"
    session.close()
    inventory = _file_inventory(artifacts)
    route_files = [name for name in inventory if name.endswith("-route.json")]
    assert len(route_files) == 1
    route = json.loads((artifacts / route_files[0]).read_text(encoding="utf-8"))
    assert route["route"] == "repairable_source"
    engine.dispose()


def test_classify_failure_environment_transient_registers_once_and_waits_retry(
    tmp_path: Path,
):
    engine, factory = _database(tmp_path)
    _seed(factory, tmp_path, angular=False)

    _orchestrator(factory)._classify_failure("cont-1", "worker-1")

    session = factory()
    rows = session.query(ArtifactMetadataModel).filter_by(run_id="run-1").all()
    assert len(rows) == 2
    assert len({row.relative_path for row in rows}) == 2
    cont = session.get(TransformationContinuationModel, "cont-1")
    assert cont.status == "waiting_retry"
    assert cont.current_node == "final_install"
    assert cont.next_attempt_at is not None
    assert session.query(RepairAttemptModel).count() == 0
    session.close()
    engine.dispose()


def test_classify_failure_replay_creates_no_new_rows_or_versioned_files(
    tmp_path: Path,
):
    engine, factory = _database(tmp_path)
    _seed(factory, tmp_path)
    service = _RecordingFailureEvidence()
    _orchestrator(factory, failure_service=service)._classify_failure("cont-1", "worker-1")

    session = factory()
    rows_before = session.query(ArtifactMetadataModel).count()
    cont = session.get(TransformationContinuationModel, "cont-1")
    cont.status = "running"
    cont.worker_id = "worker-2"
    cont.current_node = "classify_failure"
    cont.lease_expires_at = NOW + timedelta(seconds=120)
    cont.state_version += 1
    session.commit()
    session.close()
    inventory_before = _file_inventory(tmp_path / "artifacts")

    service.enable_replay()
    _orchestrator(factory, failure_service=service)._classify_failure("cont-1", "worker-2")

    session = factory()
    assert session.query(ArtifactMetadataModel).count() == rows_before
    cont = session.get(TransformationContinuationModel, "cont-1")
    assert cont.status == "blocked"
    assert cont.last_error_code == "ANGULAR_UPDATE_NO_PROGRESS"
    session.close()
    assert _file_inventory(tmp_path / "artifacts") == inventory_before
    engine.dispose()


def test_forced_duplicate_registration_blocks_continuation_durably(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _workspace, artifacts = _seed(factory, tmp_path)

    _orchestrator(factory, stage_service=_DuplicatingStageService(scope=_scope(factory)))._classify_failure(
        "cont-1", "worker-1"
    )

    session = factory()
    cont = session.get(TransformationContinuationModel, "cont-1")
    assert cont.status == "blocked"
    assert cont.last_error_code == "ARTIFACT_METADATA_DUPLICATE"
    assert "artifact-" in cont.last_error_message
    assert "04_workflow_state" in cont.last_error_message
    assert cont.worker_id is None
    assert cont.lease_expires_at is None
    assert cont.state_version == 4
    assert session.query(ArtifactMetadataModel).count() == 0
    assert session.query(RepairAttemptModel).count() == 0
    session.close()

    session = factory()
    claimed = TransformationContinuationService().claim_next(session, "worker-2", now=NOW + timedelta(seconds=300))
    assert claimed is None
    session.close()
    assert _file_inventory(artifacts) == []
    engine.dispose()


def test_transient_error_propagates_and_continuation_stays_retryable(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _seed(factory, tmp_path)

    with pytest.raises(RuntimeError, match="transient persistence hiccup"):
        _orchestrator(factory, stage_service=_FlakyStageService(scope=_scope(factory)))._classify_failure(
            "cont-1", "worker-1"
        )

    session = factory()
    cont = session.get(TransformationContinuationModel, "cont-1")
    assert cont.status == "running"
    assert cont.worker_id == "worker-1"
    assert cont.lease_expires_at is not None
    assert session.query(ArtifactMetadataModel).count() == 0
    prior_attempt = cont.attempt
    claimed = TransformationContinuationService().claim_next(
        session, "worker-2", now=cont.lease_expires_at + timedelta(seconds=1)
    )
    assert claimed is not None
    assert claimed.id == "cont-1"
    assert claimed.attempt == prior_attempt + 1
    session.close()
    engine.dispose()


def test_blocked_cleanup_removes_only_this_attempts_uncommitted_files(
    tmp_path: Path,
):
    engine, factory = _database(tmp_path)
    workspace, artifacts = _seed(factory, tmp_path)
    session = factory()
    session.add(
        ArtifactMetadataModel(
            id="metadata-artifact-committed",
            run_id="run-1",
            stage_id="stage-1",
            artifact_type="json",
            relative_path="04_workflow_state/committed.json",
            checksum="sha256:decoy",
            schema_version=1,
            created_at=NOW,
            finalized_at=NOW,
            immutable=True,
        )
    )
    session.commit()
    session.close()
    committed_file = artifacts / "04_workflow_state" / "committed.json"
    committed_file.parent.mkdir(parents=True, exist_ok=True)
    committed_file.write_text("{}", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("keep", encoding="utf-8")

    _orchestrator(factory, stage_service=_DuplicatingStageService(scope=_scope(factory)))._classify_failure(
        "cont-1", "worker-1"
    )

    assert committed_file.is_file()
    assert outside.is_file()
    assert (workspace / "package.json").is_file()
    inventory = _file_inventory(artifacts)
    assert inventory == ["04_workflow_state/committed.json"]
    assert list((tmp_path / ".checkpoints").iterdir()) != []
    session = factory()
    cont = session.get(TransformationContinuationModel, "cont-1")
    assert cont.status == "blocked"
    assert cont.last_error_code == "ARTIFACT_METADATA_DUPLICATE"
    session.close()
    engine.dispose()


def test_classify_failure_angular_transient_restores_checkpoint_and_requeues(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _seed(factory, tmp_path, failure_code="COMMAND_TIMEOUT")
    session = factory()
    session.add(
        StageCheckpointModel(
            id="ckpt-pre",
            run_id="run-1",
            stage_id="stage-1",
            kind="pre_angular_update",
            sequence=1,
            workspace_alias="STAGE_SANDBOX",
            workspace_path=str(tmp_path / "workspace"),
            workspace_fingerprint="fingerprint-1",
            safe_for_resume=True,
            sealed=True,
            state_version=1,
            created_at=NOW,
        )
    )
    session.commit()
    session.close()

    stage_service = MagicMock(spec=TransformerStageService)
    stage_service.register_artifact.return_value = None
    stage_service._binding.return_value = MagicMock(workspace_path=str(tmp_path / "workspace"))
    stage_service.reconstruct_workspace.return_value = StageSandboxCopier.fingerprint(
        tmp_path / "workspace"
    )
    _orchestrator(factory, stage_service=stage_service)._classify_failure("cont-1", "worker-1")

    session = factory()
    cont = session.get(TransformationContinuationModel, "cont-1")
    assert cont.status == "queued"
    assert cont.current_node == "angular_update"
    assert cont.attempt == 2
    assert cont.worker_id is None
    assert cont.lease_expires_at is None
    session.close()
    engine.dispose()


def test_classify_failure_failure_route_blocks_durably(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _seed(factory, tmp_path, angular=False, failure_code="EXECUTION_PROFILE_NOT_FOUND")

    _orchestrator(factory)._classify_failure("cont-1", "worker-1")

    session = factory()
    cont = session.get(TransformationContinuationModel, "cont-1")
    assert cont.status == "blocked"
    assert cont.last_error_code == "FAILURE_ROUTE_ENVIRONMENT_PERMANENT"
    assert cont.worker_id is None
    assert cont.lease_expires_at is None
    rows = session.query(ArtifactMetadataModel).filter_by(run_id="run-1").all()
    assert len(rows) == 2
    session.close()
    engine.dispose()


def test_classify_failure_repair_attempt_limit_blocks(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _seed(factory, tmp_path)
    session = factory()
    for number in (1, 2, 3):
        session.add(
            RepairAttemptModel(
                id=f"repair-stage-1-{number}",
                run_id="run-1",
                stage_id="stage-1",
                attempt_number=number,
                status="evidence_frozen",
                risk_level="unknown",
                diagnosis="prior attempt",
                created_at=NOW,
                updated_at=NOW,
            )
        )
    session.commit()
    session.close()

    _orchestrator(factory)._classify_failure("cont-1", "worker-1")

    session = factory()
    cont = session.get(TransformationContinuationModel, "cont-1")
    assert cont.status == "blocked"
    assert cont.last_error_code == "REPAIR_ATTEMPT_LIMIT"
    assert session.query(RepairAttemptModel).count() == 3
    session.close()
    engine.dispose()


def test_original_angular_execution_remains_immutable(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _seed(factory, tmp_path)
    session = factory()
    execution = session.get(CommandExecutionModel, "exec-1")
    before = {
        "status": execution.status,
        "failure_code": execution.failure_code,
        "failure_message": execution.failure_message,
        "arguments": list(execution.arguments or []),
        "state_version": execution.state_version,
    }
    session.close()

    _orchestrator(factory)._classify_failure("cont-1", "worker-1")

    session = factory()
    execution = session.get(CommandExecutionModel, "exec-1")
    assert {
        "status": execution.status,
        "failure_code": execution.failure_code,
        "failure_message": execution.failure_message,
        "arguments": list(execution.arguments or []),
        "state_version": execution.state_version,
    } == before
    session.close()
    engine.dispose()


def test_second_worker_replay_registers_no_duplicate_rows(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _seed(factory, tmp_path)
    _orchestrator(factory)._classify_failure("cont-1", "worker-1")

    session = factory()
    rows_after_first = session.query(ArtifactMetadataModel).count()
    assert rows_after_first == 3
    cont = session.get(TransformationContinuationModel, "cont-1")
    cont.status = "running"
    cont.worker_id = "worker-2"
    cont.current_node = "classify_failure"
    cont.lease_expires_at = NOW + timedelta(seconds=120)
    cont.state_version += 1
    session.commit()
    session.close()
    inventory_before = _file_inventory(tmp_path / "artifacts")

    _orchestrator(factory)._classify_failure("cont-1", "worker-2")

    session = factory()
    assert session.query(ArtifactMetadataModel).count() == rows_after_first
    cont = session.get(TransformationContinuationModel, "cont-1")
    assert cont.status == "blocked"
    assert cont.last_error_code == "ANGULAR_UPDATE_NO_PROGRESS"
    session.close()
    assert _file_inventory(tmp_path / "artifacts") == inventory_before
    engine.dispose()


def test_crash_before_commit_retry_commits_versioned_evidence_and_replays(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _seed(factory, tmp_path)

    with pytest.raises(RuntimeError, match="transient persistence hiccup"):
        _orchestrator(
            factory, stage_service=_FlakyStageService(scope=_scope(factory))
        )._classify_failure("cont-1", "worker-1")
    session = factory()
    assert session.query(ArtifactMetadataModel).count() == 0
    session.close()
    assert not any("__v" in name for name in _file_inventory(tmp_path / "artifacts"))

    _orchestrator(factory)._classify_failure("cont-1", "worker-1")

    session = factory()
    rows = session.query(ArtifactMetadataModel).filter_by(run_id="run-1").all()
    assert len(rows) == 3
    assert all("__v2" in row.relative_path for row in rows)
    cont = session.get(TransformationContinuationModel, "cont-1")
    assert cont.status == "queued"
    assert cont.current_node == "propose_repair"
    cont.status = "running"
    cont.current_node = "classify_failure"
    cont.worker_id = "worker-1"
    cont.lease_expires_at = NOW + timedelta(seconds=120)
    cont.state_version += 1
    session.commit()
    session.close()
    inventory_before = _file_inventory(tmp_path / "artifacts")

    _orchestrator(factory)._classify_failure("cont-1", "worker-1")

    session = factory()
    assert session.query(ArtifactMetadataModel).count() == 3
    cont = session.get(TransformationContinuationModel, "cont-1")
    assert cont.status == "blocked"
    assert cont.last_error_code == "ANGULAR_UPDATE_NO_PROGRESS"
    session.close()
    assert _file_inventory(tmp_path / "artifacts") == inventory_before
    engine.dispose()
