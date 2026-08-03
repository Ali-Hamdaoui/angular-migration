import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType
from app.repositories.models import (
    ArtifactMetadataModel,
    CommandExecutionModel,
    MigrationRunModel,
    RepairAttemptModel,
    StageExecutionPlanModel,
    StageStepModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
)
from app.repositories.models.base import Base
from app.services.lockfile_generation_runner import (
    LockfileGenerationError,
    LockfileGenerationRunner,
    workspace_excluding_root_lockfile_fingerprint,
)
from app.services.workspace_fingerprint import STAGE_FINGERPRINT_PROFILE


NOW = datetime(2026, 8, 3, tzinfo=UTC)
ARGV = ["install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund"]


class _FakeStageService:
    def queue_lockfile_generation(self, session, continuation, *, attempt_key):
        execution = CommandExecutionModel(
            id="exec-lock",
            run_id=continuation.run_id,
            stage_id=continuation.current_stage_id,
            authorization_id="auth-lock",
            template_id="tpl-npm-lockfile-generate",
            template_version=1,
            plan_id=continuation.plan_id,
            plan_version=1,
            idempotency_key=f"{continuation.id}:command:{attempt_key}:lockfile_generation",
            request_payload_hash="sha256:request",
            correlation_id="corr-lock",
            requested_by="transformer",
            executable="npm",
            arguments=ARGV,
            working_directory_alias="STAGE_WORKSPACE_1",
            safe_relative_working_directory="STAGE_WORKSPACE_1",
            runtime_profile_id="profile-1",
            status="queued",
            requested_at=NOW,
            command_id="npm-lockfile-generate",
            shell=False,
            timeout_seconds=3600,
            network_profile="approved-registries-only",
            cancellation_policy="terminate_process_tree",
            operation_kind="mutating",
            state_version=1,
            event_sequence=1,
        )
        session.add(execution)
        session.flush()
        step = session.scalar(
            __import__("sqlalchemy").select(StageStepModel).where(
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "lockfile_generation-0",
            )
        )
        step.execution_id = execution.id
        step.status = "RUNNING"
        continuation.status = "waiting_command"
        continuation.current_node = "lockfile_generation"
        continuation.worker_id = None
        continuation.waiting_execution_id = execution.id
        continuation.state_version += 1
        return SimpleNamespace(execution_id=execution.id)

    @staticmethod
    def _wait_for_command(_session, continuation, execution_id):
        continuation.status = "waiting_command"
        continuation.worker_id = None
        continuation.waiting_execution_id = execution_id
        continuation.state_version += 1


def _seed(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'runner.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    workspace = tmp_path / "run" / "workspace"
    artifacts = tmp_path / "run" / "artifacts"
    workspace.mkdir(parents=True)
    artifacts.mkdir()
    package = workspace / "package.json"
    package.write_text(
        '{"name":"fixture","dependencies":{"x":"2.0.0"}}', encoding="utf-8"
    )
    (workspace / "package-lock.json").write_text(
        '{"lockfileVersion":3,"packages":{"":{"dependencies":{"x":"1.0.0"}}}}',
        encoding="utf-8",
    )
    proposal = {
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
        "proposal_format": "operations",
        "operations": [
            {
                "operation": "dependency_change",
                "path": "package.json",
                "preimage_sha256": "sha256:preimage",
                "old_text": '"x":"1.0.0"',
                "new_text": '"x":"2.0.0"',
                "content": None,
            }
        ],
        "unified_diff": None,
        "touched_files": ["package.json"],
        "rationale": ["Update dependency"],
        "risk_level": "low",
        "validation_targets": ["build"],
        "limitations": [],
    }
    store = LocalFilesystemArtifactStore(artifacts.parent, fixed_run_root=artifacts)
    stored = store.write_text_artifact(
        "run-1",
        "05_repairs/attempt-repair-1/proposal.json",
        json.dumps(proposal),
        ArtifactType.JSON,
        stage_id="stage-1",
        attempt_id="repair-1",
        created_at=NOW,
    )
    session = factory()
    session.add_all(
        [
            MigrationRunModel(
                id="run-1",
                status="STAGE_CREATED",
                run_phase="TRANSFORMATION",
                phase_status="running",
                state_version=7,
                run_root=str(tmp_path / "run"),
                artifact_root=str(artifacts),
                workspace_aliases={"STAGE_WORKSPACE_1": str(workspace)},
                actor="operator",
                created_at=NOW,
                updated_at=NOW,
            ),
            StageWorkspaceBindingModel(
                id="binding-1",
                run_id="run-1",
                stage_id="stage-1",
                alias="STAGE_WORKSPACE_1",
                workspace_path=str(workspace),
                workspace_fingerprint=STAGE_FINGERPRINT_PROFILE.fingerprint(workspace),
                fingerprint_profile_id=STAGE_FINGERPRINT_PROFILE.profile_id,
                active=True,
                created_at=NOW,
            ),
            StageExecutionPlanModel(
                id="stage-plan-1",
                run_id="run-1",
                migration_plan_id="plan-1",
                stage_id="stage-1",
                idempotency_key="stage-plan-key",
                request_checksum="sha256:stage-plan-request",
                actor="operator",
                status="approved",
                version=1,
                stage_plan={
                    "commands": {
                        "lockfile_generation": [
                            {
                                "command_id": "npm-lockfile-generate",
                                "executable": "npm",
                                "arguments": ARGV,
                                "runtime_profile_checksum": "sha256:" + "4" * 64,
                            }
                        ]
                    }
                },
                checksum="sha256:stage-plan",
                artifact_ids=[],
                artifact_checksums={},
                state_version=1,
                event_sequence=1,
                created_at=NOW,
                updated_at=NOW,
            ),
            StageStepModel(
                id="step-lock",
                run_id="run-1",
                stage_id="stage-1",
                name="lockfile_generation-0",
                status="PENDING",
                component_type="command",
                idempotency_key="run-1:stage-1:lockfile_generation:0",
                artifact_ids=[],
                state_version=1,
            ),
            TransformationContinuationModel(
                id="cont-1",
                run_id="run-1",
                current_stage_id="stage-1",
                thread_id="thread-1",
                status="running",
                current_node="lockfile_generation",
                g06_approval_id="g06-1",
                plan_id="plan-1",
                plan_checksum="sha256:plan",
                stage_plan_id="stage-plan-1",
                stage_plan_checksum="sha256:stage-plan",
                worker_id="worker-1",
                attempt=1,
                max_attempts=3,
                idempotency_key="cont-key",
                request_checksum="sha256:cont",
                state_version=3,
                created_at=NOW,
                updated_at=NOW,
            ),
            RepairAttemptModel(
                id="repair-1",
                run_id="run-1",
                stage_id="stage-1",
                attempt_number=1,
                status="applied",
                risk_level="low",
                proposal_artifact_id=stored.ref.artifact_id,
                proposal_checksum=stored.ref.checksum,
                post_fingerprint=STAGE_FINGERPRINT_PROFILE.fingerprint(workspace),
                state_version=1,
                created_at=NOW,
                updated_at=NOW,
            ),
            ArtifactMetadataModel(
                id="metadata-" + stored.ref.artifact_id,
                run_id="run-1",
                stage_id="stage-1",
                artifact_type="json",
                relative_path=stored.ref.relative_path,
                checksum=stored.ref.checksum,
                created_at=NOW,
                finalized_at=NOW,
                immutable=True,
            ),
        ]
    )
    session.commit()
    return engine, factory, workspace


def _complete_execution(session, workspace: Path):
    (workspace / "package-lock.json").write_text(
        '{"lockfileVersion":3,"packages":{"":{"dependencies":{"x":"2.0.0"}},'
        '"node_modules/x":{"version":"2.0.0"}}}',
        encoding="utf-8",
    )
    execution = session.get(CommandExecutionModel, "exec-lock")
    execution.status = "succeeded"
    execution.exit_code = 0
    execution.runtime_checksum = "sha256:" + "4" * 64
    artifact_ids = ["stdout", "stderr", "command-log", "result", "manifest"]
    (
        execution.stdout_artifact_id,
        execution.stderr_artifact_id,
        execution.command_log_artifact_id,
        execution.result_artifact_id,
        execution.manifest_artifact_id,
    ) = artifact_ids
    execution.artifact_ids = artifact_ids
    for artifact_id in artifact_ids:
        session.add(
            ArtifactMetadataModel(
                id="metadata-" + artifact_id,
                run_id="run-1",
                stage_id="stage-1",
                artifact_type="json",
                relative_path=f"04_workflow_state/{artifact_id}.json",
                checksum="sha256:" + hashlib.sha256(artifact_id.encode()).hexdigest(),
                created_at=NOW,
                execution_id=execution.id,
                finalized_at=NOW,
                immutable=True,
                correlation_id=execution.correlation_id,
            )
        )
    continuation = session.get(TransformationContinuationModel, "cont-1")
    continuation.status = "running"
    continuation.worker_id = "worker-2"


def _runner():
    return LockfileGenerationRunner(stage_service=_FakeStageService(), now_provider=lambda: NOW)


def test_workspace_fingerprint_excludes_only_root_lockfile(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"name":"fixture"}', encoding="utf-8")
    (tmp_path / "package-lock.json").write_text("first", encoding="utf-8")
    nested = tmp_path / "nested" / "package-lock.json"
    nested.parent.mkdir()
    nested.write_text("nested-first", encoding="utf-8")

    initial = workspace_excluding_root_lockfile_fingerprint(tmp_path)
    (tmp_path / "package-lock.json").write_text("second", encoding="utf-8")
    assert workspace_excluding_root_lockfile_fingerprint(tmp_path) == initial

    nested.write_text("nested-second", encoding="utf-8")
    assert workspace_excluding_root_lockfile_fingerprint(tmp_path) != initial


def test_queue_is_single_and_records_explicit_pre_command_checksums(tmp_path: Path):
    engine, factory, _workspace = _seed(tmp_path)
    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-1")

    assert _runner().advance(session, continuation, next_node="repair_revalidate") == "queued"
    session.commit()

    execution = session.get(CommandExecutionModel, "exec-lock")
    assert execution.arguments == ARGV
    assert set(execution.start_fingerprint) == {
        "post_apply_pre_command_package_json_sha256",
        "post_apply_pre_command_package_lock_sha256",
        "post_apply_pre_command_workspace_excluding_root_lockfile_fingerprint",
        "post_apply_pre_command_binding_fingerprint",
    }
    continuation.status = "running"
    continuation.worker_id = "worker-replay"
    assert _runner().advance(session, continuation, next_node="repair_revalidate") == "waiting"
    assert session.query(CommandExecutionModel).count() == 1
    session.close()
    engine.dispose()


def test_shrinkwrap_blocks_before_queueing(tmp_path: Path):
    engine, factory, workspace = _seed(tmp_path)
    (workspace / "npm-shrinkwrap.json").write_text("{}", encoding="utf-8")
    session = factory()

    with pytest.raises(LockfileGenerationError) as error:
        _runner().advance(
            session,
            session.get(TransformationContinuationModel, "cont-1"),
            next_node="repair_revalidate",
        )

    assert error.value.code == "LOCKFILE_GENERATION_SHRINKWRAP_PRESENT"
    assert session.query(CommandExecutionModel).count() == 0
    session.close()
    engine.dispose()


def test_success_verifies_cas_links_artifact_and_replays_idempotently(tmp_path: Path):
    engine, factory, workspace = _seed(tmp_path)
    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert _runner().advance(session, continuation, next_node="repair_revalidate") == "queued"
    session.commit()
    _complete_execution(session, workspace)

    assert _runner().advance(session, continuation, next_node="repair_revalidate") == "passed"
    session.commit()

    execution = session.get(CommandExecutionModel, "exec-lock")
    step = session.get(StageStepModel, "step-lock")
    binding = session.get(StageWorkspaceBindingModel, "binding-1")
    verification = session.scalar(
        __import__("sqlalchemy").select(ArtifactMetadataModel).where(
            ArtifactMetadataModel.owner_reference
            == "exec-lock:lockfile-generation-verification"
        )
    )
    assert step.status == "PASSED"
    assert verification.execution_id == execution.id
    assert verification.correlation_id == execution.correlation_id
    assert verification.id.removeprefix("metadata-") in step.artifact_ids
    assert verification.id.removeprefix("metadata-") in execution.artifact_ids
    assert execution.end_fingerprint["post_command_binding_fingerprint"] == (
        binding.workspace_fingerprint
    )
    assert continuation.current_node == "repair_revalidate"

    artifact_count = session.query(ArtifactMetadataModel).count()
    continuation.status = "running"
    continuation.worker_id = "worker-replay"
    continuation.current_node = "lockfile_generation"
    assert _runner().advance(session, continuation, next_node="repair_revalidate") == "passed"
    assert session.query(ArtifactMetadataModel).count() == artifact_count
    session.close()
    engine.dispose()


def test_unexpected_workspace_mutation_is_rejected(tmp_path: Path):
    engine, factory, workspace = _seed(tmp_path)
    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert _runner().advance(session, continuation, next_node="repair_revalidate") == "queued"
    session.commit()
    _complete_execution(session, workspace)
    (workspace / "source.ts").write_text("unexpected", encoding="utf-8")

    with pytest.raises(LockfileGenerationError) as error:
        _runner().advance(session, continuation, next_node="repair_revalidate")

    assert error.value.code == "LOCKFILE_GENERATION_UNEXPECTED_MUTATION"
    session.close()
    engine.dispose()


def test_package_json_mutation_is_rejected(tmp_path: Path):
    engine, factory, workspace = _seed(tmp_path)
    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert _runner().advance(session, continuation, next_node="repair_revalidate") == "queued"
    session.commit()
    _complete_execution(session, workspace)
    (workspace / "package.json").write_text('{"name":"tampered"}', encoding="utf-8")

    with pytest.raises(LockfileGenerationError) as error:
        _runner().advance(session, continuation, next_node="repair_revalidate")

    assert error.value.code == "LOCKFILE_GENERATION_PACKAGE_JSON_MUTATED"
    session.close()
    engine.dispose()


def test_incomplete_command_artifacts_are_rejected(tmp_path: Path):
    engine, factory, workspace = _seed(tmp_path)
    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert _runner().advance(session, continuation, next_node="repair_revalidate") == "queued"
    session.commit()
    _complete_execution(session, workspace)
    session.delete(session.get(ArtifactMetadataModel, "metadata-stdout"))

    with pytest.raises(LockfileGenerationError) as error:
        _runner().advance(session, continuation, next_node="repair_revalidate")

    assert error.value.code == "LOCKFILE_GENERATION_EVIDENCE_INCOMPLETE"
    session.close()
    engine.dispose()


def test_binding_cas_miss_is_rejected(tmp_path: Path):
    engine, factory, workspace = _seed(tmp_path)
    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert _runner().advance(session, continuation, next_node="repair_revalidate") == "queued"
    session.commit()
    _complete_execution(session, workspace)
    session.get(StageWorkspaceBindingModel, "binding-1").workspace_fingerprint = (
        "sha256:" + "9" * 64
    )

    with pytest.raises(LockfileGenerationError) as error:
        _runner().advance(session, continuation, next_node="repair_revalidate")

    assert error.value.code == "LOCKFILE_GENERATION_BINDING_STALE"
    session.close()
    engine.dispose()


@pytest.mark.parametrize(
    ("lockfile", "expected_code"),
    [
        (None, "LOCKFILE_GENERATION_LOCKFILE_MISSING"),
        ("not-json", "LOCKFILE_GENERATION_LOCKFILE_INVALID"),
        (
            '{"lockfileVersion":3,"packages":{"":{"dependencies":{}}}}',
            "LOCKFILE_GENERATION_LOCKFILE_UNSYNCHRONIZED",
        ),
    ],
)
def test_missing_invalid_or_unsynchronized_lockfile_is_rejected(
    tmp_path: Path, lockfile: str | None, expected_code: str
):
    engine, factory, workspace = _seed(tmp_path)
    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert _runner().advance(session, continuation, next_node="repair_revalidate") == "queued"
    session.commit()
    _complete_execution(session, workspace)
    path = workspace / "package-lock.json"
    if lockfile is None:
        path.unlink()
    else:
        path.write_text(lockfile, encoding="utf-8")

    with pytest.raises(LockfileGenerationError) as error:
        _runner().advance(session, continuation, next_node="repair_revalidate")

    assert error.value.code == expected_code
    session.close()
    engine.dispose()
