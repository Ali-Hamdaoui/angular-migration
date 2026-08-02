"""T11: the authoritative validation-target union and its affected-check consumer.

Proves there is exactly ONE shared definition of supported validation targets
and their command groups, one deterministic union computation (proposal
targets + reviewer-required targets, intersected with the plan's executable
groups), and that ``_start_revalidation`` executes ALL affected targets in
order with a real (recording) ValidationRunner seam - never stubbing the
runner with MagicMock.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType
from app.domain.planning import (
    SUPPORTED_VALIDATION_TARGETS,
    VALIDATION_TARGET_GROUPS,
    ValidationTargetUnionError,
    executable_groups,
    validation_target_union,
)
from app.orchestration.transformer_graph import TransformerOrchestrator
from app.repositories.models import (
    ArtifactMetadataModel,
    MigrationRunModel,
    RepairAttemptModel,
    StageExecutionPlanModel,
    StageGatePackageModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
)
from app.repositories.models.base import Base
from app.services.transformer_stage_service import TransformerStageService

NOW = datetime(2026, 8, 2, tzinfo=UTC)


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


def _commands(*, lint: bool = True) -> dict[str, object]:
    commands = {
        "builds": ({"command_id": "build"},),
        "tests": ({"command_id": "test"},),
    }
    if lint:
        commands["lint"] = ({"command_id": "lint"},)
    return commands


def test_all_consumers_resolve_through_the_shared_registry():
    import app.orchestration.transformer_graph as graph_module
    import app.services.repair_application_service as repair_module
    import app.services.stage_gate_service as gate_module
    import app.services.validation_runner as runner_module

    assert repair_module.RepairApplicationService.supported_validation_targets is SUPPORTED_VALIDATION_TARGETS
    assert runner_module.VALIDATION_TARGET_GROUPS is VALIDATION_TARGET_GROUPS
    assert graph_module.VALIDATION_TARGET_GROUPS is VALIDATION_TARGET_GROUPS
    assert gate_module.SUPPORTED_VALIDATION_TARGETS is SUPPORTED_VALIDATION_TARGETS
    assert dict(VALIDATION_TARGET_GROUPS) == {
        "build": "builds",
        "test": "tests",
        "lint": "lint",
    }
    assert SUPPORTED_VALIDATION_TARGETS == frozenset({"build", "test", "lint"})


def test_registry_is_frozen():
    with pytest.raises(TypeError):
        VALIDATION_TARGET_GROUPS["deploy"] = "deploys"  # type: ignore[index]
    with pytest.raises(AttributeError):
        SUPPORTED_VALIDATION_TARGETS.add("deploy")  # type: ignore[attr-defined]


def test_executable_groups_follow_policy_order_and_skip_empty_commands():
    assert executable_groups(("build", "test"), _commands()) == ("builds", "tests")
    assert executable_groups(("test", "build"), _commands()) == ("tests", "builds")
    assert executable_groups(("build", "test"), _commands(lint=False)) == ("builds", "tests")
    assert executable_groups(("build", "test", "lint"), _commands(lint=True)) == (
        "builds",
        "tests",
        "lint",
    )
    assert executable_groups(("build", "test", "lint"), _commands(lint=False)) == (
        "builds",
        "tests",
    )
    with pytest.raises(ValidationTargetUnionError, match="Unsupported"):
        executable_groups(("build", "deploy"), _commands())


def test_union_merges_proposal_and_review_dedupes_order_preserving():
    union = validation_target_union(
        ["build", "test"],
        ["test", "lint"],
        ("build", "test", "lint"),
        _commands(lint=True),
    )
    assert union == ("build", "test", "lint")


def test_union_excludes_lint_when_the_plan_omits_lint_commands():
    union = validation_target_union(
        ["build", "test", "lint"],
        ["test"],
        ("build", "test"),
        _commands(lint=False),
    )
    assert union == ("build", "test")


def test_union_blocks_when_nothing_executable_remains():
    with pytest.raises(ValidationTargetUnionError) as raised:
        validation_target_union(
            ["lint"], [], ("build", "test"), {"final_install": ({"command_id": "fi"},)}
        )
    assert raised.value.code == "REPAIR_VALIDATION_TARGET_INVALID"
    with pytest.raises(ValidationTargetUnionError) as raised:
        validation_target_union([], [], ("build", "test"), {})
    assert raised.value.code == "REPAIR_VALIDATION_TARGET_INVALID"


def test_union_keeps_executable_targets_beyond_the_policy_checks():
    assert validation_target_union(
        ["build", "test"], [], ("build",), _commands()
    ) == ("build", "test")
    with pytest.raises(ValidationTargetUnionError) as raised:
        validation_target_union(
            ["test"], [], ("build",), {"lint": ({"command_id": "lint"},)}
        )
    assert raised.value.code == "REPAIR_VALIDATION_TARGET_INVALID"


def test_union_rejects_unknown_targets_consistently_with_bind_time():
    with pytest.raises(ValidationTargetUnionError) as raised:
        validation_target_union(
            ["deploy", "build"], ["other"], ("build", "test"), _commands()
        )
    assert raised.value.code == "REPAIR_VALIDATION_TARGET_INVALID"
    with pytest.raises(ValidationTargetUnionError) as raised:
        validation_target_union(
            ["build"], ["deploy"], ("build", "test"), _commands()
        )
    assert raised.value.code == "REPAIR_VALIDATION_TARGET_INVALID"


def test_union_always_includes_executable_mandatory_policy_targets():
    assert validation_target_union(
        ["test"], [], ("build", "test"), _commands()
    ) == ("build", "test")
    assert validation_target_union(
        [], [], ("build", "test"), _commands()
    ) == ("build", "test")
    assert validation_target_union(
        ["test"], ["test"], ("build", "test"), _commands()
    ) == ("build", "test")


def test_union_includes_reviewer_required_targets_when_their_group_has_commands():
    assert validation_target_union(
        ["build", "test"], ["lint"], ("build", "test"), _commands(lint=True)
    ) == ("build", "test", "lint")
    assert validation_target_union(
        ["build"], ["lint"], ("build",), _commands(lint=True)
    ) == ("build", "lint")
    assert validation_target_union(
        ["build", "test"], ["lint"], ("build", "test"), _commands(lint=False)
    ) == ("build", "test")


def test_union_is_deterministic():
    commands = _commands(lint=True)
    first = validation_target_union(
        ["test", "build"], ["lint", "build"], ("build", "test", "lint"), commands
    )
    second = validation_target_union(
        ["test", "build"], ["lint", "build"], ("build", "test", "lint"), commands
    )
    assert first == second == ("build", "test", "lint")


class RecordingValidationRunner:
    """Deliberate minimal seam: a real-runner-shaped fake that records and passes.

    advance_group records (group, attempt_key) exactly like the production
    runner's contract and returns "passed", so the affected-check loop can be
    driven end-to-end without stubbing ValidationRunner with MagicMock.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def advance_group(self, session, continuation, group, **kwargs) -> str:
        self.calls.append((group, str(kwargs.get("attempt_key"))))
        return "passed"


def _orchestrator(factory, validation_runner) -> TransformerOrchestrator:
    scope = _scope(factory)
    return TransformerOrchestrator(
        scope=scope,
        stage_service=TransformerStageService(scope=scope),
        gate_service=MagicMock(),
        transformation_evidence=MagicMock(),
        prompt_explainer=MagicMock(),
        validation_runner=validation_runner,
        failure_evidence=MagicMock(),
        repair_service=MagicMock(),
        patch_service=MagicMock(),
        sealing_flow=MagicMock(),
    )


def _seed_revalidation(
    factory,
    tmp_path: Path,
    *,
    proposal_targets=("build", "test"),
    review_targets=("test",),
    attempt_status: str = "applied",
    lint_commands: bool = True,
    persisted_targets=None,
    package_targets=None,
    commands_override=None,
):
    artifacts = tmp_path / "artifacts"
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    app_ts = workspace / "src" / "app.ts"
    app_ts.write_text("old", encoding="utf-8")
    (workspace / "package.json").write_text('{"name": "fixture"}', encoding="utf-8")
    store = LocalFilesystemArtifactStore(artifacts.parent, fixed_run_root=artifacts)
    attempt_id = "repair-1"
    proposal = store.write_text_artifact(
        "run-1",
        f"05_repairs/attempt-{attempt_id}/proposal.json",
        json.dumps(
            {
                "proposal_format": "operations",
                "operations": [
                    {
                        "operation": "replace_text",
                        "path": "src/app.ts",
                        "old_text": "old",
                        "new_text": "new",
                        "preimage_sha256": (
                            "sha256:" + hashlib.sha256(app_ts.read_bytes()).hexdigest()
                        ),
                    }
                ],
                "unified_diff": None,
                "failure_evidence_checksum": "sha256:failure",
                "context_pack_checksum": "sha256:context",
                "touched_files": ["src/app.ts"],
                "rationale": ["Fix the compiler error."],
                "risk_level": "low",
                "validation_targets": list(proposal_targets),
                "limitations": [],
            },
            sort_keys=True,
        ),
        ArtifactType.JSON,
        stage_id="stage-1",
        attempt_id=attempt_id,
        created_by="repair-proposal",
        created_at=NOW,
    )
    review = store.write_text_artifact(
        "run-1",
        f"05_repairs/attempt-{attempt_id}/review.json",
        json.dumps(
            {
                "decision": "accept",
                "findings": [],
                "policy_checks": ["paths"],
                "risk_assessment": "low risk, minimal change",
                "required_validation_targets": list(review_targets),
                "limitations": [],
                "proposal_checksum": proposal.ref.checksum,
            },
            sort_keys=True,
        ),
        ArtifactType.JSON,
        stage_id="stage-1",
        attempt_id=attempt_id,
        created_by="repair-review",
        created_at=NOW,
    )
    commands = {
        "bootstrap_install": ({"command_id": "bootstrap_install"},),
        "angular_update": ({"command_id": "angular_update"},),
        "target_version_check": ({"command_id": "target_version_check"},),
        "final_install": ({"command_id": "final_install"},),
        "builds": ({"command_id": "build"},),
        "tests": ({"command_id": "test"},),
    }
    if lint_commands:
        commands["lint"] = ({"command_id": "lint"},)
    if commands_override is not None:
        commands = commands_override
    stage_plan = {
        "validation_policy": {"required_checks": ["build", "test"]},
        "commands": commands,
    }
    package = None
    if package_targets is not None:
        package = store.write_text_artifact(
            "run-1",
            "04_workflow_state/stages/stage-1/gates/g10-package.json",
            json.dumps(
                {
                    "gate_id": "G10",
                    "run_id": "run-1",
                    "stage_id": "stage-1",
                    "validation_targets": list(package_targets),
                },
                sort_keys=True,
            ),
            ArtifactType.JSON,
            stage_id="stage-1",
            attempt_id=attempt_id,
            created_by="transformer",
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
        stage_plan=stage_plan,
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
        workspace_fingerprint="sha256:binding",
        active=True,
        created_at=NOW,
    )
    continuation = TransformationContinuationModel(
        id="cont-1",
        run_id="run-1",
        current_stage_id="stage-1",
        thread_id="thread-1",
        status="running",
        current_node="repair_revalidate",
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
        failure_evidence_artifact_id="artifact-failure",
        failure_evidence_checksum="sha256:failure",
        failure_route_artifact_id="artifact-route",
        failure_route_checksum="sha256:route",
        context_pack_artifact_id="artifact-context",
        context_pack_checksum="sha256:context",
        proposal_artifact_id=proposal.ref.artifact_id,
        proposal_checksum=proposal.ref.checksum,
        review_artifact_id=review.ref.artifact_id,
        review_checksum=review.ref.checksum,
        proposer_invocation_id=f"{attempt_id}:proposer",
        reviewer_invocation_id=f"{attempt_id}:reviewer",
        pre_fingerprint="sha256:pre",
        failure_fingerprint="fingerprint-failure",
        validation_targets=list(persisted_targets) if persisted_targets is not None else None,
        created_at=NOW,
        updated_at=NOW,
    )
    g10_package = None
    if package is not None:
        g10_package = StageGatePackageModel(
            id="gate-package-g10",
            run_id="run-1",
            stage_id="stage-1",
            gate_id="G10",
            gate_version=1,
            status="approved",
            package_artifact_id=package.ref.artifact_id,
            package_checksum=package.ref.checksum,
            artifact_set_checksum="sha256:set",
            plan_id="plan-1",
            plan_version=1,
            stage_plan_id="stage-plan-1",
            stage_plan_checksum="sha256:stage-plan",
            workspace_fingerprint="sha256:binding",
            expected_state_version=3,
            created_at=NOW,
        )
        attempt.g10_gate_package_id = g10_package.id
    session.add_all([run, plan, binding, continuation, attempt])
    for stored in (proposal, review):
        session.add(
            ArtifactMetadataModel(
                id="metadata-" + stored.ref.artifact_id,
                run_id="run-1",
                stage_id="stage-1",
                artifact_type=stored.ref.artifact_type.value,
                relative_path=stored.ref.relative_path,
                checksum=stored.ref.checksum,
                created_at=NOW,
                finalized_at=NOW,
                immutable=True,
            )
        )
    if g10_package is not None:
        session.add(g10_package)
        session.add(
            ArtifactMetadataModel(
                id="metadata-" + package.ref.artifact_id,
                run_id="run-1",
                stage_id="stage-1",
                artifact_type=package.ref.artifact_type.value,
                relative_path=package.ref.relative_path,
                checksum=package.ref.checksum,
                created_at=NOW,
                finalized_at=NOW,
                immutable=True,
            )
        )
    session.commit()
    session.close()
    return store, attempt_id, artifacts


def test_start_revalidation_executes_all_affected_targets_in_order(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _artifacts = _seed_revalidation(
        factory,
        tmp_path,
        proposal_targets=("build", "test"),
        review_targets=("test",),
    )
    runner = RecordingValidationRunner()

    _orchestrator(factory, runner).advance("cont-1", "worker-1")

    assert runner.calls == [
        ("builds", f"{attempt_id}:affected"),
        ("tests", f"{attempt_id}:affected"),
    ]
    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "queued"
    assert continuation.current_node == "final_install"
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.status == "revalidating"
    session.close()
    engine.dispose()


def test_start_revalidation_affected_attempt_key_shape_matches_idempotency_contract(
    tmp_path: Path,
):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _artifacts = _seed_revalidation(factory, tmp_path)
    runner = RecordingValidationRunner()

    _orchestrator(factory, runner).advance("cont-1", "worker-1")

    assert runner.calls[0][0] == "builds"
    assert runner.calls[0][1] == f"{attempt_id}:affected"
    assert runner.calls[1][0] == "tests"
    assert runner.calls[1][1] == f"{attempt_id}:affected"
    engine.dispose()


def test_start_revalidation_includes_mandatory_policy_targets_and_excludes_lint_without_commands(
    tmp_path: Path,
):
    engine, factory = _database(tmp_path)
    _store, _attempt_id, _artifacts = _seed_revalidation(
        factory,
        tmp_path,
        proposal_targets=("lint",),
        review_targets=("test",),
        lint_commands=False,
    )
    runner = RecordingValidationRunner()

    _orchestrator(factory, runner).advance("cont-1", "worker-1")

    assert [group for group, _key in runner.calls] == ["builds", "tests"]
    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "queued"
    assert continuation.current_node == "final_install"
    session.close()
    engine.dispose()


def test_start_revalidation_blocks_when_the_union_is_empty(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, _attempt_id, _artifacts = _seed_revalidation(
        factory,
        tmp_path,
        proposal_targets=("lint",),
        review_targets=(),
        lint_commands=False,
        commands_override={
            "bootstrap_install": ({"command_id": "bootstrap_install"},),
            "final_install": ({"command_id": "final_install"},),
        },
    )
    runner = RecordingValidationRunner()

    _orchestrator(factory, runner).advance("cont-1", "worker-1")

    assert runner.calls == []
    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "blocked"
    assert continuation.last_error_code == "REPAIR_VALIDATION_TARGET_INVALID"
    assert continuation.current_node == "repair_revalidate"
    attempt = session.get(RepairAttemptModel, "repair-1")
    assert attempt.status == "applied"
    session.close()
    engine.dispose()


def test_start_revalidation_missing_review_blocks_stale(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _artifacts = _seed_revalidation(factory, tmp_path)
    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    attempt.review_artifact_id = None
    attempt.review_checksum = None
    session.commit()
    session.close()
    runner = RecordingValidationRunner()

    _orchestrator(factory, runner).advance("cont-1", "worker-1")

    assert runner.calls == []
    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "blocked"
    assert continuation.last_error_code == "REPAIR_PROPOSAL_STALE"
    session.close()
    engine.dispose()


def test_start_revalidation_consumes_persisted_union_not_recomputed(tmp_path: Path):
    """The persisted union is the authority: the recomputed union (which would
    include lint from the proposal) must NOT be executed for a new row."""
    engine, factory = _database(tmp_path)
    _store, attempt_id, _artifacts = _seed_revalidation(
        factory,
        tmp_path,
        proposal_targets=("build", "test", "lint"),
        review_targets=("test",),
        persisted_targets=("build", "test"),
        package_targets=["build", "test"],
    )
    runner = RecordingValidationRunner()

    _orchestrator(factory, runner).advance("cont-1", "worker-1")

    assert runner.calls == [
        ("builds", f"{attempt_id}:affected"),
        ("tests", f"{attempt_id}:affected"),
    ]
    engine.dispose()


def test_start_revalidation_blocks_when_sealed_package_diverges_from_persisted_union(
    tmp_path: Path,
):
    """A package whose sealed targets differ from the persisted union is
    tampering: revalidation fails closed instead of trusting either side."""
    engine, factory = _database(tmp_path)
    _store, _attempt_id, _artifacts = _seed_revalidation(
        factory,
        tmp_path,
        proposal_targets=("build", "test"),
        review_targets=("test",),
        persisted_targets=("build", "test"),
        package_targets=["build", "test", "lint"],
    )
    runner = RecordingValidationRunner()

    _orchestrator(factory, runner).advance("cont-1", "worker-1")

    assert runner.calls == []
    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "blocked"
    assert continuation.last_error_code == "REPAIR_PROPOSAL_STALE"
    session.close()
    engine.dispose()
