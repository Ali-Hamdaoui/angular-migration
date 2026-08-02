"""Approved-stage preparation, preflight, and frozen command helpers."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

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
    StageReconstructionRecordModel,
    StageStepModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
)
from app.repositories.session import session_scope
from app.services.command_executor_service import (
    CommandExecutorError,
    CommandExecutorService,
)
from app.services.stage_execution_application_service import (
    StageExecutionApplicationService,
    StageExecutionError,
    _ValidatedStageStart,
)
from app.services.stage_preparation_application_service import StagePreparationResult
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.state import StateTransitionService, TransitionRequest


class TransformerStageError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def artifact_metadata_id(artifact_id: str) -> str:
    """Artifact metadata primary key binding for an immutable artifact id.

    The row primary key keeps the codebase-wide ``"metadata-" + artifact_id``
    contract (consumers strip the prefix and look rows up by artifact id), while
    exactly-once semantics are enforced by the pending-aware registration guard
    and by committed-evidence replay keyed on the failure fingerprint.
    """
    return "metadata-" + artifact_id


class TransformerStageService:
    def __init__(
        self,
        *,
        scope=session_scope,
        stage_execution=None,
        command_executor=None,
        now_provider=None,
    ) -> None:
        self._scope = scope
        self._stage_execution = stage_execution or StageExecutionApplicationService(scope=scope)
        self._command_executor = command_executor or CommandExecutorService()
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
            durable = session.scalar(
                select(StageWorkspaceBindingModel).where(
                    StageWorkspaceBindingModel.run_id == run.id,
                    StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                    StageWorkspaceBindingModel.active.is_(True),
                )
            )
            expected_fingerprint = durable.workspace_fingerprint if durable is not None else None
        try:
            preparation = self._stage_execution._prepare_workspace(
                validated, expected_fingerprint=expected_fingerprint
            )
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
            input_checkpoint = self._checkpoint(
                session,
                continuation,
                preparation,
                "pre_bootstrap",
                artifacts[-1].ref.artifact_id,
                artifacts[-1].ref.checksum,
            )
            binding = self._binding(session, continuation)
            binding.source_checkpoint_id = input_checkpoint.id
            self._advance(continuation, "resolve_runtime")
            return preparation.fingerprint

    def runtime_binding(self, session, continuation: TransformationContinuationModel) -> dict[str, object]:
        evidence, selected = self.runtime_binding_evidence(session, continuation)
        if evidence["mismatches"]:
            raise TransformerStageError(
                "EXECUTION_PROFILE_STALE",
                "Selected execution profile no longer matches the approved stage plan: "
                + json.dumps(evidence, sort_keys=True, separators=(",", ":")),
            )
        return {
            "profile_id": evidence["actual"]["profile_id"],
            "checksum": evidence["actual"]["checksum"],
            "node_executable": selected.get("node_executable"),
            "package_manager_executable": selected.get("package_manager_executable", "npm"),
        }

    @staticmethod
    def runtime_binding_evidence(session, continuation: TransformationContinuationModel):
        stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
        profile = session.scalar(
            select(ExecutionProfileModel)
            .where(ExecutionProfileModel.run_id == continuation.run_id)
            .order_by(ExecutionProfileModel.created_at.desc())
        )
        planned = stage_plan.stage_plan or {} if stage_plan else {}
        expected_id = planned.get("execution_profile_id")
        expected_checksums = sorted(
            {
                command.get("runtime_profile_checksum")
                for commands in (planned.get("commands") or {}).values()
                for command in commands
                if command.get("runtime_profile_checksum")
            }
        )
        selected = next(
            (
                item
                for item in (profile.profiles or [])
                if item.get("profile_id") == profile.selected_profile_id
            ),
            None,
        ) if profile else None
        actual = {
            "status": profile.status if profile else None,
            "profile_id": profile.selected_profile_id if profile else None,
            "checksum": profile.selected_checksum if profile else None,
            "persisted_profile_checksum": selected.get("checksum") if selected else None,
        }
        expected = {
            "statuses": ["resolved", "selected"],
            "profile_id": expected_id,
            "checksums": expected_checksums,
        }
        mismatches = []
        if actual["status"] not in expected["statuses"]:
            mismatches.append("status")
        if actual["profile_id"] != expected_id:
            mismatches.append("profile_id")
        if expected_checksums != [actual["checksum"]]:
            mismatches.append("checksum")
        if actual["persisted_profile_checksum"] != actual["checksum"]:
            mismatches.append("persisted_profile_checksum")
        return {"expected": expected, "actual": actual, "mismatches": mismatches}, selected

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
        attempt_id: str | None = None,
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
            attempt_id=attempt_id,
            created_by="transformer",
            created_at=now,
            input_hashes={"stage_plan": str(payload["stage_plan_checksum"])},
            policy_version="transformer-gate-v1",
        )

    @staticmethod
    def register_artifact(session, stored, continuation: TransformationContinuationModel) -> None:
        metadata_id = artifact_metadata_id(stored.ref.artifact_id)
        committed = session.get(ArtifactMetadataModel, metadata_id)
        if committed is not None:
            TransformerStageService._validate_committed_metadata(committed, continuation, stored)
            return
        for pending in (*session.new, *session.dirty):
            if isinstance(pending, ArtifactMetadataModel) and pending.id == metadata_id:
                return
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

    @staticmethod
    def _validate_committed_metadata(committed, continuation, stored) -> None:
        mismatches = []
        if committed.run_id != continuation.run_id:
            mismatches.append(f"run_id (expected {continuation.run_id}, stored {committed.run_id})")
        if committed.stage_id != continuation.current_stage_id:
            mismatches.append(
                f"stage_id (expected {continuation.current_stage_id}, stored {committed.stage_id})"
            )
        if committed.artifact_type != stored.ref.artifact_type.value:
            mismatches.append(
                f"artifact_type (expected {stored.ref.artifact_type.value}, stored {committed.artifact_type})"
            )
        if committed.relative_path != stored.ref.relative_path:
            mismatches.append(
                f"relative_path (expected {stored.ref.relative_path}, stored {committed.relative_path})"
            )
        if committed.checksum != stored.ref.checksum:
            mismatches.append(f"checksum (expected {stored.ref.checksum}, stored {committed.checksum})")
        if mismatches:
            raise TransformerStageError(
                "ARTIFACT_METADATA_IDENTITY_CONFLICT",
                "Committed artifact metadata for the same artifact id carries a different payload: "
                + "; ".join(mismatches),
            )

    def queue_bootstrap(self, session, continuation: TransformationContinuationModel):
        return self._queue_group(
            session,
            continuation,
            group="bootstrap_install",
            next_node="verify_bootstrap",
            attempt_key="initial",
        )

    def queue_angular_update(
        self,
        session,
        continuation: TransformationContinuationModel,
        *,
        checkpoint_id: str,
        prompt_id: str | None,
    ):
        return self._queue_group(
            session,
            continuation,
            group="angular_update",
            next_node="handle_prompt",
            attempt_key=prompt_id or "initial",
            checkpoint_id=checkpoint_id,
            prompt_id=prompt_id,
        )

    def queue_version_check(self, session, continuation: TransformationContinuationModel):
        return self._queue_group(
            session,
            continuation,
            group="target_version_check",
            next_node="version_verify",
            attempt_key="target",
        )

    def snapshot_workspace(self, workspace_path: str, stage_root: str, stage_id: str) -> StagePreparationResult:
        workspace = Path(workspace_path).resolve(strict=True)
        root = Path(stage_root).resolve(strict=True)
        workspace.relative_to(root)
        checkpoint_root = root / ".checkpoints"
        checkpoint_root.mkdir(parents=True, exist_ok=True)
        target = checkpoint_root / f"{stage_id}-{uuid4().hex[:12]}"
        temporary = checkpoint_root / f".{target.name}.preparing"
        if any(item.is_symlink() for item in workspace.rglob("*")):
            raise TransformerStageError("WORKSPACE_SYMLINK_UNSUPPORTED", "Checkpoint source contains a symlink")
        try:
            shutil.copytree(workspace, temporary)
            temporary.replace(target)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        return StagePreparationResult(
            "STAGE_WORKSPACE_" + stage_id.upper().replace("-", "_"),
            str(target),
            StageSandboxCopier.fingerprint(target),
            sum(1 for item in target.rglob("*") if item.is_file()),
            True,
        )

    def persist_snapshot_checkpoint(
        self,
        session,
        continuation,
        snapshot: StagePreparationResult,
        kind: str,
    ) -> StageCheckpointModel:
        return self._checkpoint(
            session,
            continuation,
            snapshot,
            kind,
            f"snapshot:{continuation.current_stage_id}:{kind}",
            snapshot.fingerprint,
        )

    @staticmethod
    def reconstruct_workspace(
        snapshot_path: str,
        workspace_path: str,
        stage_root: str,
        expected_fingerprint: str,
    ) -> str:
        snapshot = Path(snapshot_path).resolve(strict=True)
        workspace = Path(workspace_path).resolve(strict=True)
        root = Path(stage_root).resolve(strict=True)
        snapshot.relative_to(root)
        workspace.relative_to(root)
        if StageSandboxCopier.fingerprint(snapshot) != expected_fingerprint:
            raise TransformerStageError("CHECKPOINT_INTEGRITY_FAILED", "Checkpoint fingerprint changed")
        temporary = workspace.parent / f".{workspace.name}.reconstructing-{uuid4().hex[:12]}"
        quarantine = workspace.parent / f".{workspace.name}.interrupted-{uuid4().hex[:12]}"
        shutil.copytree(snapshot, temporary)
        try:
            workspace.replace(quarantine)
            temporary.replace(workspace)
        except Exception:
            if not workspace.exists() and quarantine.exists():
                quarantine.replace(workspace)
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        shutil.rmtree(quarantine)
        return StageSandboxCopier.fingerprint(workspace)

    def begin_reconstruction(
        self,
        session,
        continuation: TransformationContinuationModel,
        *,
        checkpoint: StageCheckpointModel,
        reason: str,
        execution_id: str | None = None,
        attempt_id: str | None = None,
    ) -> None:
        """Record governed reconstruction intent before the filesystem swap.

        Verifies the durable binding still agrees with the immutable source
        checkpoint; on disagreement the reconstruction is refused and the
        FINGERPRINT_MISMATCH event is committed durably.  Otherwise the
        STARTED event is emitted in the caller's transaction (the tx that
        records intent).  The caller must then swap the workspace and write
        the ledger row + binding in one authoritative transaction.
        """
        transitions = StateTransitionService(session)
        binding = session.scalar(
            select(StageWorkspaceBindingModel).where(
                StageWorkspaceBindingModel.run_id == continuation.run_id,
                StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                StageWorkspaceBindingModel.active.is_(True),
            )
        )
        if binding is not None and binding.workspace_fingerprint != checkpoint.workspace_fingerprint:
            transitions.append_audit_event(
                run_id=continuation.run_id,
                idempotency_key=(
                    f"{continuation.current_stage_id}:reconstruct:{reason}:{checkpoint.id}:mismatch"
                ),
                event_type=WorkflowEventType.STAGE_WORKSPACE_FINGERPRINT_MISMATCH,
                actor="transformer",
                reason="workspace binding fingerprint no longer matches the reconstruction checkpoint",
                occurred_at=self._now(),
                payload={
                    "stage_id": continuation.current_stage_id,
                    "checkpoint_id": checkpoint.id,
                    "binding_workspace_fingerprint": binding.workspace_fingerprint,
                    "checkpoint_workspace_fingerprint": checkpoint.workspace_fingerprint,
                    "reason": reason,
                },
            )
            session.commit()
            raise TransformerStageError(
                "WORKSPACE_FINGERPRINT_MISMATCH",
                "Durable workspace binding no longer matches the reconstruction checkpoint",
            )
        transitions.append_audit_event(
            run_id=continuation.run_id,
            idempotency_key=(
                f"{continuation.current_stage_id}:reconstruct:{reason}:{checkpoint.id}:started"
            ),
            event_type=WorkflowEventType.STAGE_WORKSPACE_RECONSTRUCTION_STARTED,
            actor="transformer",
            reason=f"workspace reconstruction started ({reason})",
            occurred_at=self._now(),
            payload={
                "stage_id": continuation.current_stage_id,
                "checkpoint_id": checkpoint.id,
                "checkpoint_fingerprint": checkpoint.workspace_fingerprint,
                "reason": reason,
                "execution_id": execution_id,
                "attempt_id": attempt_id,
            },
        )

    def record_reconstruction(
        self,
        session,
        continuation: TransformationContinuationModel,
        *,
        checkpoint: StageCheckpointModel,
        reason: str,
        restored_fingerprint: str,
        execution_id: str | None = None,
        attempt_id: str | None = None,
    ) -> StageReconstructionRecordModel:
        """Write the durable ledger row and the RECONSTRUCTED event.

        Must be called in the same transaction as the authoritative binding /
        checkpoint state change so the binding is never updated while the
        ledger row is absent.
        """
        record = StageReconstructionRecordModel(
            id=f"reconstruction-{uuid4().hex[:12]}",
            run_id=continuation.run_id,
            stage_id=continuation.current_stage_id,
            checkpoint_id=checkpoint.id,
            reason=reason,
            source_workspace_fingerprint=checkpoint.workspace_fingerprint,
            restored_workspace_fingerprint=restored_fingerprint,
            created_from_execution_id=execution_id,
            attempt_id=attempt_id,
            state_version=continuation.state_version,
            created_at=self._now(),
        )
        session.add(record)
        StateTransitionService(session).append_audit_event(
            run_id=continuation.run_id,
            idempotency_key=f"{record.id}:reconstructed",
            event_type=WorkflowEventType.STAGE_WORKSPACE_RECONSTRUCTED,
            actor="transformer",
            reason=f"workspace reconstructed from immutable checkpoint ({reason})",
            occurred_at=self._now(),
            payload={
                "stage_id": continuation.current_stage_id,
                "checkpoint_id": checkpoint.id,
                "source_workspace_fingerprint": checkpoint.workspace_fingerprint,
                "restored_workspace_fingerprint": restored_fingerprint,
                "reason": reason,
                "execution_id": execution_id,
                "attempt_id": attempt_id,
                "ledger_record_id": record.id,
            },
        )
        session.flush()
        return record

    def _queue_group(
        self,
        session,
        continuation,
        *,
        group,
        next_node,
        attempt_key,
        checkpoint_id=None,
        prompt_id=None,
    ):
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
        request = SimpleNamespace(idempotency_key=f"{continuation.id}:command:{attempt_key}")
        try:
            result = self._stage_execution._authorize_and_queue_first_command(
                session,
                run,
                plan,
                stage_plan,
                preparation,
                request,
                run.actor or "transformer",
                group,
            )
        except StageExecutionError as error:
            raise TransformerStageError(error.code, error.message) from error
        step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == f"{group}-0",
            )
        )
        execution = session.get(CommandExecutionModel, result.execution_id)
        execution.checkpoint_id = checkpoint_id
        execution.prompt_request_id = prompt_id
        if step is not None:
            step.execution_id = result.execution_id
            step.status = "RUNNING"
            step.updated_at = self._now()
        continuation.status = "waiting_command"
        continuation.current_node = next_node
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
        if execution is not None and execution.status in {"pending", "queued", "running"}:
            self._wait_for_command(continuation)
            return execution.id
        if (
            execution is not None
            and (
                execution.status == "failed"
                or (
                    execution.status == "interrupted"
                    and execution.reconstruction_required
                )
            )
        ):
            workspace_recovered = False
            if execution.process_id is not None or execution.exit_code is not None:
                binding = self._binding(session, continuation)
                current_fingerprint = StageSandboxCopier.fingerprint(
                    Path(binding.workspace_path)
                )
                if current_fingerprint != binding.workspace_fingerprint:
                    raise TransformerStageError(
                        "BOOTSTRAP_RETRY_REQUIRES_RECOVERY",
                        "Failed bootstrap changed the workspace; reconstruct from the safe checkpoint before retry.",
                    )
                workspace_recovered = True
            try:
                retry = self._command_executor.queue_retry_execution(
                    session,
                    execution.id,
                    idempotency_key=f"{execution.id}:retry:1",
                    workspace_recovered=workspace_recovered,
                )
            except CommandExecutorError as error:
                raise TransformerStageError(error.code, error.message) from error
            successor = session.get(CommandExecutionModel, retry.execution_id)
            step.execution_id = successor.id
            step.attempt_id = successor.id
            step.status = "RUNNING"
            step.updated_at = self._now()
            self._wait_for_command(continuation)
            return successor.id
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
        continuation.status = "queued"
        continuation.current_node = "angular_update"
        continuation.last_error_code = None
        continuation.last_error_message = None
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.state_version += 1
        continuation.updated_at = self._now()
        session.flush()
        return fingerprint

    def _wait_for_command(self, continuation: TransformationContinuationModel) -> None:
        continuation.status = "waiting_command"
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.state_version += 1
        continuation.updated_at = self._now()

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
        for _attempt in range(2):
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
            try:
                with session.begin_nested():
                    session.add(checkpoint)
                    session.flush()
                return checkpoint
            except IntegrityError as error:
                detail = str(getattr(error, "orig", "") or error)
                if "stage_checkpoints" not in detail:
                    raise
        raise TransformerStageError(
            "CHECKPOINT_SEQUENCE_CONFLICT",
            "Concurrent checkpoint creation for the same stage exceeded the retry budget",
        )

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
