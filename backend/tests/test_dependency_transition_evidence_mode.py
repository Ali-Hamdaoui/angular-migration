import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.command import NPM_DEPENDENCY_UNINSTALL_RENDERER
from app.domain.contracts import ArtifactType, CommandPolicyValidateRequestDto
from app.repositories.models import (
    ArtifactMetadataModel,
    MigrationRunModel,
    RepairAttemptModel,
    StageExecutionPlanModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
)
from app.repositories.models.base import Base
from app.services.command_registry_service import CommandPolicyEngineService
from app.services.dependency_transition_runner import (
    DependencyTransitionError,
    DependencyTransitionRunner,
)


NOW = datetime(2026, 8, 10, tzinfo=UTC)
PACKAGE = "jest-preset-angular"
BLOCKING = "@angular-devkit/build-angular"


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    value = sessionmaker(bind=engine)()
    yield value
    value.close()
    engine.dispose()


def _diagnosis(source="npm_eresolve_peer_conflict"):
    return {
        "kind": "peer_dependency_conflict",
        "source": source,
        "package": PACKAGE,
        "package_version": "13.1.6",
        "blocking_dependency": BLOCKING,
        "required_peer_range": ">=13.0.0 <18.0.0",
        "installed_version": "16.1.3",
        "required_ranges": {BLOCKING: ">=13.0.0 <18.0.0"},
        "proposed_angular_version": None,
    }


def _workspace(tmp_path):
    workspace = tmp_path / "workspace"
    installed = workspace / "node_modules" / PACKAGE
    installed.mkdir(parents=True)
    (workspace / "package.json").write_text(
        json.dumps({"devDependencies": {PACKAGE: "^13.0.0", BLOCKING: "^21.0.0"}}),
        encoding="utf-8",
    )
    (workspace / "package-lock.json").write_text(
        json.dumps(
            {
                "packages": {
                    "": {"devDependencies": {PACKAGE: "16.1.3", BLOCKING: "21.0.0"}},
                    f"node_modules/{PACKAGE}": {"version": "16.1.3"},
                }
            }
        ),
        encoding="utf-8",
    )
    (installed / "package.json").write_text(
        json.dumps(
            {
                "version": "16.1.3",
                "peerDependencies": {"@angular/core": ">=19.0.0 <22.0.0"},
            }
        ),
        encoding="utf-8",
    )
    return workspace


def _runner_context(workspace, diagnosis):
    return {
        "run": SimpleNamespace(id="run-1"),
        "attempt": SimpleNamespace(id="repair-current"),
        "workspace": workspace,
        "intent": {
            "blocking_package": PACKAGE,
            "installed_version": "16.1.3",
            "peer_ranges": {BLOCKING: ">=13.0.0 <18.0.0"},
            "evidence_diagnosis": diagnosis,
        },
    }


def test_npm_eresolve_runner_queues_current_attempt_uninstall_from_attempted_state(
    session, tmp_path
):
    runner = DependencyTransitionRunner(stage_service=MagicMock())
    runner._queue_transition_command = MagicMock(return_value="queued")
    continuation = SimpleNamespace(run_id="run-1", current_stage_id="stage-1")

    result = runner._phase_uninstall(
        session,
        continuation,
        _runner_context(_workspace(tmp_path), _diagnosis()),
    )

    assert result == "queued"
    assert runner._queue_transition_command.call_args.args[4] == (
        "repair-current:transition:uninstall"
    )


@pytest.mark.parametrize(
    "diagnosis",
    [
        _diagnosis("angular_update_peer_conflict"),
        {**_diagnosis(), "required_peer_range": None},
    ],
    ids=["installed-state-stays-strict", "malformed-npm-fails-closed"],
)
def test_runner_rejects_invalid_evidence_for_its_source(session, tmp_path, diagnosis):
    runner = DependencyTransitionRunner(stage_service=MagicMock())
    runner._queue_transition_command = MagicMock()

    with pytest.raises(DependencyTransitionError) as raised:
        runner._phase_uninstall(
            session,
            SimpleNamespace(run_id="run-1", current_stage_id="stage-1"),
            _runner_context(_workspace(tmp_path), diagnosis),
        )

    assert raised.value.code == "DEPENDENCY_TRANSITION_EVIDENCE_INVALID"
    runner._queue_transition_command.assert_not_called()


def _metadata(stored):
    return ArtifactMetadataModel(
        id="metadata-" + stored.ref.artifact_id,
        run_id="run-policy",
        stage_id="stage-1",
        artifact_type=stored.ref.artifact_type.value,
        relative_path=stored.ref.relative_path,
        checksum=stored.ref.checksum,
        created_at=NOW,
        finalized_at=NOW,
        immutable=True,
    )


def _policy_case(session, tmp_path, diagnosis):
    workspace = _workspace(tmp_path)
    run_root = tmp_path / "artifacts" / "run-policy"
    store = LocalFilesystemArtifactStore(run_root, fixed_run_root=run_root)
    evidence = store.write_text_artifact(
        "run-policy",
        "05_repairs/failure.json",
        json.dumps(
            {
                "normalized_failure": {
                    "command_id": (
                        "npm-lockfile-generate"
                        if diagnosis["source"] == "npm_eresolve_peer_conflict"
                        else "angular-update-exact"
                    ),
                    "exit_code": 1,
                    "failure_diagnosis": diagnosis,
                }
            }
        ),
        ArtifactType.JSON,
        stage_id="stage-1",
        attempt_id="repair-policy",
        created_at=NOW,
    )
    proposal = store.write_text_artifact(
        "run-policy",
        "05_repairs/proposal.json",
        json.dumps(
            {
                "operations": [
                    {
                        "operation": "dependency_transition",
                        "schema_version": "transformer-repair-v2",
                        "repair_kind": "dependency_transition",
                        "failure_type": "peer_dependency_conflict",
                        "strategy": "detach_update_reattach",
                        "blocking_dependency": {
                            "package": PACKAGE,
                            "installed_version": "16.1.3",
                            "required_peer_ranges": [
                                {
                                    "package": BLOCKING,
                                    "version_range": ">=13.0.0 <18.0.0",
                                }
                            ],
                        },
                        "target_state": {
                            "package": PACKAGE,
                            "target_version": "16.1.3",
                            "angular_major": 21,
                        },
                    }
                ]
            }
        ),
        ArtifactType.JSON,
        stage_id="stage-1",
        attempt_id="repair-policy",
        created_at=NOW,
    )
    session.add_all(
        [
            MigrationRunModel(
                id="run-policy",
                status="RUNNING",
                run_phase="STAGED_MIGRATION",
                state_version=1,
                artifact_root=str(run_root),
                run_root=str(tmp_path),
                created_at=NOW,
                updated_at=NOW,
            ),
            RepairAttemptModel(
                id="repair-policy",
                run_id="run-policy",
                stage_id="stage-1",
                attempt_number=1,
                status="executing",
                risk_level="medium",
                proposal_artifact_id=proposal.ref.artifact_id,
                proposal_checksum=proposal.ref.checksum,
                failure_evidence_artifact_id=evidence.ref.artifact_id,
                failure_evidence_checksum=evidence.ref.checksum,
                created_at=NOW,
            ),
            StageWorkspaceBindingModel(
                id="binding-policy",
                run_id="run-policy",
                stage_id="stage-1",
                alias="stage_workspace",
                workspace_path=str(workspace),
                workspace_fingerprint="sha256:" + "1" * 64,
                active=True,
                created_at=NOW,
            ),
            StageExecutionPlanModel(
                id="stage-plan-policy",
                run_id="run-policy",
                migration_plan_id="plan-policy",
                stage_id="stage-1",
                idempotency_key="stage-plan-policy",
                request_checksum="sha256:" + "2" * 64,
                actor="operator",
                status="approved",
                version=1,
                stage_plan={
                    "target_exact": "21.0.0",
                    "commands": {
                        "angular_update": [
                            {
                                "command_id": "angular-update-exact",
                                "working_directory_alias": "stage_workspace",
                                "parameter_bindings": {"target_exact": "21.0.0"},
                            }
                        ]
                    },
                },
                checksum="sha256:" + "3" * 64,
                state_version=1,
                event_sequence=0,
                created_at=NOW,
                updated_at=NOW,
            ),
            TransformationContinuationModel(
                id="continuation-policy",
                run_id="run-policy",
                current_stage_id="stage-1",
                thread_id="thread-policy",
                status="running",
                current_node="dependency_transition",
                g06_approval_id="g06-policy",
                plan_id="plan-policy",
                plan_checksum="sha256:" + "4" * 64,
                stage_plan_id="stage-plan-policy",
                stage_plan_checksum="sha256:" + "3" * 64,
                idempotency_key="continuation-policy",
                request_checksum="sha256:" + "5" * 64,
                created_at=NOW,
                updated_at=NOW,
            ),
            _metadata(evidence),
            _metadata(proposal),
        ]
    )
    session.commit()
    return CommandPolicyValidateRequestDto(
        run_id="run-policy",
        stage_id="stage-1",
        plan_id="plan-policy",
        plan_version=1,
        command_id=NPM_DEPENDENCY_UNINSTALL_RENDERER.command_id,
        template_id=NPM_DEPENDENCY_UNINSTALL_RENDERER.template_id,
        template_version=1,
        executable="npm",
        arguments=list(
            NPM_DEPENDENCY_UNINSTALL_RENDERER.render_arguments({"package": PACKAGE})
        ),
        working_directory_alias="stage_workspace",
        working_directory=str(workspace),
        execution_profile_id="profile-policy",
        network_profile="approved-registries-only",
        timeout_seconds=1800,
        idempotency_key="repair-policy:transition:uninstall",
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("npm_eresolve_peer_conflict", True),
        ("angular_update_peer_conflict", False),
    ],
)
def test_command_policy_uses_the_same_evidence_source_semantics(
    session, tmp_path, source, expected
):
    request = _policy_case(session, tmp_path, _diagnosis(source))

    assert CommandPolicyEngineService._valid_repair_dependency_transition(
        session, request, "repair-policy"
    ) is expected
