"""Executor integration test: a real command failure produces a diagnostic pack (F03-04/05)."""

import time
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from app.command_execution.worker import SupervisedProcessResult
from app.domain.contracts import CommandStatus
from app.repositories.models import (
    CommandAuthorizationAuditModel,
    CommandExecutionModel,
    ExecutionProfileModel,
    FailureDiagnosticPackModel,
    MigrationRunModel,
)
from app.repositories.session import session_scope
from app.services.command_executor_service import CommandExecutorService

NOW = datetime.now(UTC)


def _seed_failing_execution(tmp_path: Path, *, run_id: str, execution_id: str) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(exist_ok=True)
    with session_scope() as session:
        session.add(
            MigrationRunModel(
                id=run_id, status="STAGE_CREATED", run_phase="FEASIBILITY_PLANNING",
                phase_status="completed", state_version=7, run_root=str(tmp_path),
                artifact_root=str(artifacts),
                workspace_aliases={"run_workspace": str(tmp_path)},
                created_at=NOW, updated_at=NOW,
            )
        )
        session.add(
            CommandAuthorizationAuditModel(
                id="authz-f03", run_id=run_id, stage_id=None, command_id="node-version",
                executable="node", arguments=["--version"], decision="accepted", reasons=[],
                policy_version="policy-v1", idempotency_key="authz:f03",
                request_payload_hash="sha256:req", expected_state_version=7,
                execution_profile_id="profile-1", workspace_alias="run_workspace",
                network_profile="none", correlation_id="corr-f03-exec", actor="operator",
                artifact_ids=[], state_version=7, created_at=NOW,
            )
        )
        session.add(
            ExecutionProfileModel(
                id="profile-f03", run_id=run_id, idempotency_key="profile:f03",
                request_checksum="sha256:profile", policy_version="profile-v1",
                status="selected", source_angular_exact="18.2.0",
                selected_profile_id="profile-1", selected_checksum="sha256:runtime",
                profiles=[
                    {
                        "profile_id": "profile-1",
                        "checksum": "sha256:runtime",
                        "node_executable": "node",
                        "node_exact": "18.20.8",
                        "package_manager": "npm",
                        "package_manager_executable": "npm",
                        "package_manager_exact": "10.8.2",
                        "npx_executable": "npx",
                        "npx_exact": "10.8.2",
                        "environment_allowlist": ["PATH"],
                    }
                ],
                blockers=[], guidance=[], artifact_ids=[], state_version=7,
                event_sequence=1, created_at=NOW, updated_at=NOW,
            )
        )
        session.add(
            CommandExecutionModel(
                id=execution_id, run_id=run_id, authorization_id="authz-f03",
                idempotency_key="exec:f03", request_payload_hash="sha256:exec",
                correlation_id="corr-f03-exec", requested_by="operator",
                executable="node", arguments=["--version"],
                working_directory_alias="run_workspace",
                runtime_profile_id="profile-1", status="queued",
                requested_at=NOW, command_id="node-version", requester="operator",
                shell=False, timeout_seconds=10, network_profile="none",
                operation_kind="read_only", state_version=1, event_sequence=1,
            )
        )
        session.commit()


def _wait_terminal(session_scope, run_id: str, execution_id: str, timeout: float = 60.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with session_scope() as session:
            model = session.get(CommandExecutionModel, execution_id)
            if model is not None and model.status in {
                CommandStatus.SUCCEEDED.value, CommandStatus.FAILED.value,
                CommandStatus.CANCELLED.value, CommandStatus.TIMED_OUT.value,
            }:
                return model.status
        time.sleep(0.2)
    raise TimeoutError("execution did not reach a terminal status")


def test_failed_command_produces_diagnostic_pack(tmp_path: Path):
    supervisor = MagicMock()
    supervisor.run.return_value = SupervisedProcessResult(
        status=CommandStatus.FAILED,
        exit_code=1,
        stdout="",
        stderr="npm ERR! code ERESOLVE\nfake failure for diagnostics",
        timed_out=False,
        cancelled=False,
    )
    service = CommandExecutorService(supervisor=supervisor)
    run_id = "run-f03-exec"
    execution_id = "exec-f03-exec"
    _seed_failing_execution(tmp_path, run_id=run_id, execution_id=execution_id)
    service.dispatch_execution(execution_id)
    status = _wait_terminal(session_scope, run_id, execution_id)
    assert status == CommandStatus.FAILED.value

    with session_scope() as session:
        model = session.get(CommandExecutionModel, execution_id)
        assert model.failure_code is not None
        packs = (
            session.query(FailureDiagnosticPackModel)
            .filter_by(run_id=run_id, execution_id=execution_id)
            .all()
        )
        assert len(packs) >= 1
        pack = packs[0]
        assert pack.fault_code is not None
        assert pack.correlation_id == "corr-f03-exec"
        assert pack.workflow_context["run_id"] == run_id
        assert pack.workflow_context["execution_id"] == execution_id
        assert pack.command_evidence["exit_code"] == 1
        assert "ERESOLVE" in pack.command_evidence["stderr"]
        assert pack.sanitized_traceback == ""
