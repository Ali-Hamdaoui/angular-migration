"""Approved-stage preparation, preflight, and frozen command helpers."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import select

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType, RunStatus, WorkflowEventType
from app.repositories.models import (
    ArtifactMetadataModel,
    CommandExecutionModel,
    ExecutionProfileModel,
    G06ApprovalModel,
    MigrationPlanModel,
    MigrationRunModel,
    StageCheckpointModel,
    StageExecutionPlanModel,
    StageStepModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
)
from app.repositories.session import session_scope
from app.services.stage_execution_application_service import (
    StageExecutionApplicationService,
    StageExecutionError,
    _ValidatedStageStart,
)
from app.services.stage_preparation_application_service import StagePreparationResult
from app.state import StateTransitionService, TransitionRequest


class TransformerStageError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class TransformerStageService:
    def __init__(self, *, scope=session_scope, stage_execution=None, now_provider=None) -> None:
        self._scope = scope
        self._stage_execution = stage_execution or StageExecutionApplicationService(scope=scope)
        self._now = now_provider or (lambda: datetime.now(UTC))

    def prepare(self, continuation_id: str, worker_id: str) -> str:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            run = session.get(MigrationRunModel, continuation.run_id)
            plan = session.get(MigrationPlanModel, continuation.plan_id)
            stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
            gate = session.get(G06ApprovalModel, continuation.g06_approval_id)
            if not run or not plan or not stage_plan or not gate:
                raise TransformerStageError("G06_BINDING_STALE", "Approved stage binding is missing")
            request = self._request(run, continuation, gate)
            validated = _ValidatedStageStart(
                run.id,
                continuation.current_stage_id,
                run.actor or "transformer",
                request,
                plan,
                stage_plan,
                gate.artifact_set_checksum,
                dict(run.workspace_aliases or {}),
                run.artifact_root,
            )
        try:
            preparation = self._stage_execution._prepare_workspace(validated)
            artifacts = self._stage_execution._write_preparation_artifacts(validated, preparation)
        except StageExecutionError as error:
            raise TransformerStageError(error.code, error.message) from error
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            run = session.get(MigrationRunModel, continuation.run_id)
            if run.state_version != request.expected_state_version:
                raise TransformerStageError("STALE_STATE_VERSION", "Run changed during workspace preparation")
            stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
            self._stage_execution._persist_prepared_stage(
                session, run, continuation.current_stage_id, stage_plan, preparation, artifacts
            )
            StateTransitionService(session).apply_transition(
                TransitionRequest(
                    run_id=run.id,
                    expected_state_version=run.state_version,
                    idempotency_key=request.idempotency_key,
                    event_type=WorkflowEventType.STAGE_CREATED,
                    next_run_status=RunStatus.STAGE_CREATED,
                    actor=run.actor or "transformer",
                    reason="durable Transformer prepared the approved stage workspace",
                    stage_id=continuation.current_stage_id,
                    payload={
                        "plan_checksum": continuation.plan_checksum,
                        "stage_plan_checksum": continuation.stage_plan_checksum,
                        "workspace_alias": preparation.workspace_alias,
                        "workspace_fingerprint": preparation.fingerprint,
                    },
                    occurred_at=self._now(),
                )
            )
            self._stage_execution._record_preparation_events(
                session,
                run,
                continuation.current_stage_id,
                request,
                run.actor or "transformer",
                preparation,
            )
            self._checkpoint(
                session,
                continuation,
                preparation,
                "pre_bootstrap",
                artifacts[-1].ref.artifact_id,
                artifacts[-1].ref.checksum,
            )
            self._advance(continuation, "resolve_runtime")
            return preparation.fingerprint

    def runtime_binding(self, session, continuation: TransformationContinuationModel) -> dict[str, object]:
        stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
        profile = session.scalar(
            select(ExecutionProfileModel)
            .where(ExecutionProfileModel.run_id == continuation.run_id)
            .order_by(ExecutionProfileModel.created_at.desc())
        )
        expected_id = (stage_plan.stage_plan or {}).get("execution_profile_id") if stage_plan else None
        selected = next(
            (
                item
                for item in (profile.profiles or [])
                if item.get("profile_id") == profile.selected_profile_id
                and item.get("checksum") == profile.selected_checksum
            ),
            None,
        ) if profile else None
        if profile is None or profile.status != "selected" or expected_id != profile.selected_profile_id or not selected:
            raise TransformerStageError(
                "EXECUTION_PROFILE_STALE",
                "Selected execution profile no longer matches the approved stage plan",
            )
        return {
            "profile_id": profile.selected_profile_id,
            "checksum": profile.selected_checksum,
            "node_executable": selected.get("node_executable"),
            "package_manager_executable": selected.get("package_manager_executable", "npm"),
        }

    def preflight(self, session, continuation: TransformationContinuationModel) -> dict[str, object]:
        binding = self._binding(session, continuation)
        workspace = Path(binding.workspace_path)
        package_path = workspace / "package.json"
        lock_path = workspace / "package-lock.json"
        blockers: list[str] = []
        if not package_path.is_file():
            blockers.append("PACKAGE_JSON_MISSING")
            package: dict[str, object] = {}
        else:
            try:
                package = json.loads(package_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                package = {}
                blockers.append("PACKAGE_JSON_INVALID")
        if not lock_path.is_file():
            blockers.append("PACKAGE_LOCK_MISSING")
        dependencies = {
            **(package.get("dependencies") or {}),
            **(package.get("devDependencies") or {}),
        }
        if any(
            isinstance(value, str) and value.startswith(("file:", "git:", "git+", "http:"))
            for value in dependencies.values()
        ):
            blockers.append("NON_REGISTRY_DEPENDENCY")
        npmrc = workspace / ".npmrc"
        if npmrc.is_file():
            text = npmrc.read_text(encoding="utf-8", errors="replace")
            if "legacy-peer-deps=true" in text.lower() or "force=true" in text.lower():
                blockers.append("FORCED_DEPENDENCY_RESOLUTION")
        return {
            "status": "blocked" if blockers else "compatible",
            "blockers": sorted(set(blockers)),
            "package_manager": (package.get("packageManager") or "npm"),
            "workspace_fingerprint": binding.workspace_fingerprint,
        }

    def known_decisions(self, session, continuation: TransformationContinuationModel) -> dict[str, object]:
        stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
        value = stage_plan.stage_plan or {}
        return {
            "build_system_decision": value.get("build_system_decision"),
            "validation_policy": value.get("validation_policy"),
            "recovery_policy": value.get("recovery_policy"),
            "repair_policy": value.get("repair_policy"),
            "forbidden_change_policy": value.get("forbidden_change_policy"),
        }

    def write_gate_package(
        self,
        *,
        run_id: str,
        stage_id: str,
        artifact_root: str,
        gate_id: str,
        payload: dict[str, object],
    ):
        now = self._now()
        run_root = Path(artifact_root)
        store = LocalFilesystemArtifactStore(run_root.parent, fixed_run_root=run_root)
        return store.write_text_artifact(
            run_id,
            f"04_workflow_state/stages/{stage_id}/gates/{gate_id.lower()}-package.json",
            json.dumps(payload, sort_keys=True, indent=2),
            ArtifactType.JSON,
            stage_id=stage_id,
            created_by="transformer",
            created_at=now,
            input_hashes={"stage_plan": str(payload["stage_plan_checksum"])},
            policy_version="transformer-gate-v1",
        )

    @staticmethod
    def register_artifact(session, stored, continuation: TransformationContinuationModel) -> None:
        if session.get(ArtifactMetadataModel, "metadata-" + stored.ref.artifact_id) is None:
            session.add(
                ArtifactMetadataModel(
                    id="metadata-" + stored.ref.artifact_id,
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

    def queue_bootstrap(self, session, continuation: TransformationContinuationModel):
        run = session.get(MigrationRunModel, continuation.run_id)
        plan = session.get(MigrationPlanModel, continuation.plan_id)
        stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
        binding = self._binding(session, continuation)
        preparation = StagePreparationResult(
            binding.alias,
            binding.workspace_path,
            binding.workspace_fingerprint,
            0,
            False,
        )
        request = SimpleNamespace(idempotency_key=f"{continuation.id}:command")
        try:
            result = self._stage_execution._authorize_and_queue_first_command(
                session,
                run,
                plan,
                stage_plan,
                preparation,
                request,
                run.actor or "transformer",
                "bootstrap_install",
            )
        except StageExecutionError as error:
            raise TransformerStageError(error.code, error.message) from error
        step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "bootstrap_install-0",
            )
        )
        if step is not None:
            step.execution_id = result.execution_id
            step.status = "RUNNING"
            step.updated_at = self._now()
        continuation.status = "waiting_command"
        continuation.current_node = "verify_bootstrap"
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.state_version += 1
        continuation.updated_at = self._now()
        session.flush()
        return result

    def verify_bootstrap(self, session, continuation: TransformationContinuationModel) -> str:
        step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "bootstrap_install-0",
            )
        )
        execution = session.get(CommandExecutionModel, step.execution_id) if step and step.execution_id else None
        if execution is None or execution.status != "succeeded":
            raise TransformerStageError(
                "BOOTSTRAP_INSTALL_FAILED",
                execution.failure_code if execution else "Bootstrap command evidence is missing",
            )
        binding = self._binding(session, continuation)
        workspace = Path(binding.workspace_path)
        fingerprint = self._stage_execution._preparation._copier.fingerprint(workspace)
        if fingerprint == binding.workspace_fingerprint:
            raise TransformerStageError("BOOTSTRAP_NO_CHANGE", "Bootstrap install produced no workspace change")
        binding.workspace_fingerprint = fingerprint
        binding.last_verified_fingerprint = fingerprint
        binding.last_verified_at = self._now()
        step.status = "PASSED"
        step.completed_at = self._now()
        step.workspace_fingerprint = fingerprint
        self._checkpoint(
            session,
            continuation,
            StagePreparationResult(binding.alias, binding.workspace_path, fingerprint, 0, False),
            "post_bootstrap",
            execution.result_artifact_id or execution.id,
            execution.runtime_checksum,
            execution.id,
        )
        continuation.status = "blocked"
        continuation.current_node = "angular_update"
        continuation.last_error_code = None
        continuation.last_error_message = "Bootstrap complete; Angular update has not started"
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.state_version += 1
        continuation.updated_at = self._now()
        session.flush()
        return fingerprint

    @staticmethod
    def _request(run, continuation, gate):
        return SimpleNamespace(
            expected_state_version=run.state_version,
            idempotency_key=f"{continuation.id}:prepare",
            artifact_set_checksum=gate.artifact_set_checksum,
            plan_checksum=continuation.plan_checksum,
            stage_plan_checksum=continuation.stage_plan_checksum,
            workspace_fingerprint=gate.workspace_fingerprint,
        )

    @staticmethod
    def _owned(session, continuation_id: str, worker_id: str):
        continuation = session.get(TransformationContinuationModel, continuation_id)
        if continuation is None or continuation.status != "running" or continuation.worker_id != worker_id:
            raise TransformerStageError("TRANSFORMATION_CLAIM_STALE", "Worker no longer owns continuation")
        return continuation

    @staticmethod
    def _binding(session, continuation):
        binding = session.scalar(
            select(StageWorkspaceBindingModel).where(
                StageWorkspaceBindingModel.run_id == continuation.run_id,
                StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                StageWorkspaceBindingModel.active.is_(True),
            )
        )
        if binding is None:
            raise TransformerStageError("STAGE_WORKSPACE_MISSING", "Prepared stage workspace binding is missing")
        return binding

    def _checkpoint(
        self,
        session,
        continuation,
        preparation,
        kind,
        manifest_artifact_id,
        manifest_checksum,
        execution_id=None,
    ):
        latest = session.scalar(
            select(StageCheckpointModel)
            .where(StageCheckpointModel.stage_id == continuation.current_stage_id)
            .order_by(StageCheckpointModel.sequence.desc())
        )
        checkpoint = StageCheckpointModel(
            id=f"checkpoint-{uuid4().hex[:12]}",
            run_id=continuation.run_id,
            stage_id=continuation.current_stage_id,
            kind=kind,
            sequence=(latest.sequence if latest else 0) + 1,
            source_checkpoint_id=latest.id if latest else None,
            workspace_alias=preparation.workspace_alias,
            workspace_path=preparation.workspace_path,
            workspace_fingerprint=preparation.fingerprint,
            manifest_artifact_id=manifest_artifact_id,
            manifest_checksum=manifest_checksum,
            created_from_execution_id=execution_id,
            safe_for_resume=True,
            sealed=False,
            state_version=continuation.state_version,
            created_at=self._now(),
        )
        session.add(checkpoint)
        return checkpoint

    def _advance(self, continuation, node: str) -> None:
        continuation.current_node = node
        continuation.status = "queued"
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.state_version += 1
        continuation.updated_at = self._now()

    @staticmethod
    def checksum(value: object) -> str:
        return "sha256:" + hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
