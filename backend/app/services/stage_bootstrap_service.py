"""Application service for stage bootstrap clean install (S3-F06)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.api.stage_contracts import (
    StageBootstrapInstallResponse,
    StageBootstrapStatusResponse,
)
from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType, WorkflowEventType
from app.domain.stage_workspace import BootstrapInstallResult, StageFingerprint
from app.repositories.models import ArtifactMetadataModel, CommandExecutionModel, MigrationRunModel
from app.repositories.models.workflow import MigrationStageModel, StageStepModel
from app.repositories.session import session_scope
from app.repositories.stage_workspace_models import StageWorkspaceModel
from app.state.transition_service import StateTransitionService, TransitionRequest


class StageApplicationError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.status_code = status_code


class StageBootstrapApplicationService:
    """Application service for S3-F06 stage bootstrap clean install."""

    STAGE_POLICY_VERSION = "stage-workspace-policy-v1"

    def __init__(self, *, session_scope_factory=session_scope, now_provider=None) -> None:
        self._scope = session_scope_factory
        self._now = now_provider or (lambda: datetime.now(UTC))

    def run_bootstrap_install(self, run_id: str, stage_id: str, request) -> StageBootstrapInstallResponse:
        """Execute the approved bootstrap install in the stage sandbox."""
        now = self._now()
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise StageApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)
            stage = session.get(MigrationStageModel, stage_id)
            if stage is None or stage.run_id != run_id:
                raise StageApplicationError("STAGE_NOT_FOUND", "Stage does not exist.", status_code=404)
            if run.state_version != request.expected_state_version:
                raise StageApplicationError("STALE_STATE_VERSION", "The run state version is stale.", status_code=409)

            # Verify sandbox exists and G07 approved
            workspace = session.scalar(
                select(StageWorkspaceModel)
                .where(StageWorkspaceModel.run_id == run_id, StageWorkspaceModel.stage_id == stage_id)
                .order_by(StageWorkspaceModel.created_at.desc())
            )
            if workspace is None:
                raise StageApplicationError("WORKSPACE_NOT_FOUND", "Stage workspace does not exist. Run sandbox preparation first.", status_code=409)

            # Check G07 approval
            from app.repositories.stage_workspace_models import G07ApprovalModel
            g07 = session.scalar(
                select(G07ApprovalModel)
                .where(G07ApprovalModel.run_id == run_id, G07ApprovalModel.stage_id == stage_id)
                .order_by(G07ApprovalModel.created_at.desc())
            )
            if g07 is None or g07.status not in ("approved", "approved_with_comment"):
                raise StageApplicationError("G07_REQUIRED", "G07 approval is required before bootstrap install.", status_code=409)

            # Check for existing idempotent execution
            existing = session.scalar(
                select(CommandExecutionModel)
                .where(CommandExecutionModel.run_id == run_id, CommandExecutionModel.idempotency_key == request.idempotency_key)
            )
            if existing is not None:
                step = session.scalar(
                    select(StageStepModel).where(
                        StageStepModel.run_id == run_id,
                        StageStepModel.stage_id == stage_id,
                        StageStepModel.name == "bootstrap_install",
                    ).order_by(StageStepModel.created_at.desc())
                )
                if step:
                    return StageBootstrapInstallResponse(
                        run_id=run_id, stage_id=stage_id, step_id=step.id,
                        status=existing.status, command=f"{existing.executable} {' '.join(existing.arguments)}",
                        exit_code=existing.exit_code, started_at=existing.started_at,
                        completed_at=existing.finished_at,
                        state_version=existing.state_version or 1,
                        event_sequence=existing.event_sequence or 1,
                        artifact_ids=existing.artifact_ids or [],
                        idempotent_replay=True,
                    )

            # Emit BOOTSTRAP_INSTALL_STARTED event
            transition = StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run_id, expected_state_version=run.state_version,
                idempotency_key=f"{request.idempotency_key}:started",
                event_type=WorkflowEventType.STAGE_BOOTSTRAP_INSTALL_STARTED,
                actor=request.actor, reason="Stage bootstrap install started", occurred_at=now,
                payload={"stage_id": stage_id},
            ))

            sandbox_path = Path(workspace.sandbox_path)
            pre_fingerprint = StageFingerprint(
                workspace_path=str(sandbox_path),
                fingerprint=self._dir_fingerprint(sandbox_path),
                policy_version=self.STAGE_POLICY_VERSION,
                file_count=0, total_size_bytes=0,
            )

            # Register command execution record
            cmd_exec = CommandExecutionModel(
                id=f"cmd-{uuid4().hex[:12]}",
                run_id=run_id, stage_id=stage_id,
                idempotency_key=request.idempotency_key,
                requested_by=request.actor,
                executable="npm",
                arguments=["ci"],
                working_directory_alias=self.STAGE_POLICY_VERSION,
                status="RUNNING",
                command_id=f"npm-ci-{uuid4().hex[:8]}",
                requester=request.actor,
                shell=False,
                timeout_seconds=600,
                network_profile="isolated",
                cancellation_policy="terminate_process_tree",
                state_version=transition.next_state_version,
                event_sequence=transition.event_sequence,
                start_fingerprint={"workspace_fingerprint": pre_fingerprint.fingerprint},
                requested_at=now, started_at=now,
            )
            session.add(cmd_exec)
            session.flush()

            # Create step record
            step = StageStepModel(
                id=f"step-{uuid4().hex[:12]}",
                run_id=run_id, stage_id=stage_id,
                name="bootstrap_install",
                status="RUNNING",
                component_type="StagePipelineService",
                idempotency_key=request.idempotency_key,
                started_at=now,
            )
            session.add(step)
            session.flush()

            # Emit command-started event
            StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run_id, expected_state_version=transition.next_state_version,
                idempotency_key=f"{request.idempotency_key}:command_started",
                event_type=WorkflowEventType.COMMAND_STARTED,
                actor=request.actor, reason="npm ci started", occurred_at=now,
                payload={"command_id": cmd_exec.id, "executable": "npm", "arguments": ["ci"], "stage_id": stage_id},
            ))

            return StageBootstrapInstallResponse(
                run_id=run_id, stage_id=stage_id, step_id=step.id,
                status="RUNNING",
                command="npm ci",
                started_at=now,
                state_version=transition.next_state_version,
                event_sequence=transition.event_sequence,
            )

    def get_bootstrap_status(self, run_id: str, stage_id: str) -> StageBootstrapStatusResponse | None:
        """Get the current bootstrap install step status."""
        with self._scope() as session:
            step = session.scalar(
                select(StageStepModel).where(
                    StageStepModel.run_id == run_id,
                    StageStepModel.stage_id == stage_id,
                    StageStepModel.name == "bootstrap_install",
                ).order_by(StageStepModel.started_at.desc())
            )
            if step is None:
                return None

            cmd = session.scalar(
                select(CommandExecutionModel).where(
                    CommandExecutionModel.run_id == run_id,
                    CommandExecutionModel.stage_id == stage_id,
                    CommandExecutionModel.executable == "npm",
                ).order_by(CommandExecutionModel.requested_at.desc())
            )
            return StageBootstrapStatusResponse(
                run_id=run_id, stage_id=stage_id, step_id=step.id,
                name=step.name, status=step.status,
                command=f"{cmd.executable} {' '.join(cmd.arguments)}" if cmd else None,
                exit_code=cmd.exit_code if cmd else None,
                started_at=step.started_at, completed_at=step.completed_at,
                artifact_ids=cmd.artifact_ids if cmd else [],
            )

    def _dir_fingerprint(self, path: Path) -> str:
        """Compute a simple directory fingerprint."""
        try:
            entries = sorted(
                str(f.relative_to(path)) for f in path.rglob("*") if f.is_file()
            )
            payload = json.dumps(entries, sort_keys=True, separators=(",", ":"))
            return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"
        except OSError:
            return "sha256:unavailable"
