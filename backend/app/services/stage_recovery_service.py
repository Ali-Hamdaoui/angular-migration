"""One durable, restart-safe owner for deterministic stage recovery."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, update

from app.domain.contracts import WorkflowEventType
from app.repositories.models import (
    ArtifactMetadataModel,
    CommandExecutionModel,
    MigrationRunModel,
    MigrationStageModel,
    RepairAttemptModel,
    StageCheckpointModel,
    StageGatePackageModel,
    StageRecoveryOperationModel,
    StageStepModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
)
from app.repositories.session import session_scope
from app.services.dependency_repair_preflight_service import (
    DependencyRepairPreflightService,
)
from app.services.lockfile_generation_runner import (
    LockfileGenerationError,
    LockfileGenerationRunner,
    is_npm_eresolve_failure,
)
from app.services.repair_lifecycle_service import RepairLifecycleService
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.transformer_stage_service import (
    ReconstructionMode,
    TransformerStageError,
    TransformerStageService,
)
from app.services.workspace_fingerprint import STAGE_FINGERPRINT_PROFILE
from app.services.transformation_continuation_service import append_continuation_event
from app.state import StateTransitionService


ACTIVE_RECOVERY_STATUSES = (
    "PLANNED",
    "RECONSTRUCTING",
    "RECONSTRUCTED",
    "PREPARING",
    "COMMAND_QUEUED",
    "COMMAND_RUNNING",
    "VERIFYING",
)
RECOVERY_REQUIRED_ERRORS = frozenset(
    {
        "COMMAND_RECOVERY_REQUIRED",
        "WORKSPACE_RECONSTRUCTION_REQUIRED",
        "DEPENDENCY_STATE_RECOVERY_REQUIRED",
        "LOCKFILE_GENERATION_COMMAND_FAILED",
        "LOCKFILE_RECONCILIATION_WORKSPACE_STALE",
    }
)
APPLIED_EVIDENCE_STATUSES = frozenset(
    {
        "applied",
        "applied_verified",
        "migration_retried",
        "revalidating",
        "revalidating_affected",
        "validation_failed",
        "superseded",
    }
)


class StageRecoveryError(ValueError):
    def __init__(self, code: str, message: str, details: dict[str, object] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class StageRecoveryService:
    """Own recovery intent, reconstruction, reconciliation, and handoff."""

    def __init__(self, *, scope=session_scope, now_provider=None) -> None:
        self._scope = scope
        self._now = now_provider or (lambda: datetime.now(UTC))
        self._stage = TransformerStageService(scope=scope)
        self._lockfiles = LockfileGenerationRunner(stage_service=self._stage)

    @staticmethod
    def checksum(value: object) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
        return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def file_checksum(path: Path) -> str:
        if not path.is_file() or path.is_symlink():
            return "missing"
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    @classmethod
    def recovery_required(cls, continuation, operation=None) -> bool:
        if operation is not None and operation.status in ACTIVE_RECOVERY_STATUSES:
            return True
        return bool(
            continuation.status == "blocked"
            and continuation.last_error_code in RECOVERY_REQUIRED_ERRORS
        )

    def create(
        self,
        *,
        run_id: str,
        expected_state_version: int,
        idempotency_key: str,
        actor: str,
        correlation_id: str | None = None,
    ) -> dict[str, object]:
        with self._scope() as session:
            continuation = session.scalar(
                select(TransformationContinuationModel).where(
                    TransformationContinuationModel.run_id == run_id
                )
            )
            if continuation is None:
                raise StageRecoveryError("TRANSFORMATION_NOT_FOUND", "Transformer continuation is missing")
            replay = session.scalar(
                select(StageRecoveryOperationModel).where(
                    StageRecoveryOperationModel.run_id == run_id,
                    StageRecoveryOperationModel.idempotency_key == idempotency_key,
                )
            )
            if replay is not None:
                if replay.source_state_version != expected_state_version:
                    raise StageRecoveryError(
                        "IDEMPOTENCY_PAYLOAD_MISMATCH",
                        "Recovery key was already used with a different state version",
                    )
                return self._result(replay, continuation, True)
            if continuation.state_version != expected_state_version:
                raise StageRecoveryError(
                    "TRANSFORMATION_STATE_CONFLICT",
                    "Transformer state changed; refresh authoritative state",
                )
            active = self._active(session, run_id, continuation.current_stage_id)
            if active is not None:
                raise StageRecoveryError(
                    "RECOVERY_ALREADY_ACTIVE",
                    "A stage recovery operation already owns this recovery boundary",
                    {"recovery_id": active.id, "kind": active.kind, "status": active.status},
                )
            context = self._resolve_context(session, continuation)
            request_payload = {
                "run_id": run_id,
                "stage_id": continuation.current_stage_id,
                "continuation_id": continuation.id,
                "expected_state_version": expected_state_version,
                "idempotency_key": idempotency_key,
                "correlation_id": correlation_id,
                "recovery_kind": context["kind"],
                "causal_execution_id": context["causal"].id,
                "interrupted_execution_id": (
                    context["interrupted"].id if context["interrupted"] is not None else None
                ),
                "causal_evidence_checksum": context["causal_evidence_checksum"],
                "checkpoint_id": context["checkpoint"].id,
                "repair_attempt_id": context["attempt"].id,
                "source_workspace_fingerprint": context["source_workspace_fingerprint"],
                "classification": context["diagnosis"]["classification"],
            }
            recovery_payload = dict(request_payload)
            recovery_payload.pop("idempotency_key", None)
            recovery_payload.pop("correlation_id", None)
            request_checksum = self.checksum(request_payload)
            recovery_checksum = self.checksum(recovery_payload)
            existing = session.scalar(
                select(StageRecoveryOperationModel).where(
                    StageRecoveryOperationModel.run_id == run_id,
                    StageRecoveryOperationModel.recovery_checksum == recovery_checksum,
                )
            )
            if existing is not None:
                return self._result(existing, continuation, True)
            now = self._now()
            self._supersede_non_executable_attempts(
                session,
                continuation,
                context["attempt"],
                now,
            )
            operation = StageRecoveryOperationModel(
                id="recovery-" + recovery_checksum.removeprefix("sha256:")[:32],
                run_id=run_id,
                stage_id=continuation.current_stage_id,
                kind=context["kind"],
                status="PLANNED",
                causal_execution_id=context["causal"].id,
                interrupted_execution_id=(
                    context["interrupted"].id if context["interrupted"] is not None else None
                ),
                causal_evidence_checksum=context["causal_evidence_checksum"],
                checkpoint_id=context["checkpoint"].id,
                source_state_version=expected_state_version,
                source_workspace_fingerprint=context["source_workspace_fingerprint"],
                request_checksum=request_checksum,
                recovery_checksum=recovery_checksum,
                idempotency_key=idempotency_key,
                repair_attempt_id=context["attempt"].id,
                source_error_code=continuation.last_error_code,
                source_error_message=continuation.last_error_message,
                manifest_checksum=context["manifest_checksum"],
                stale_lock_checksum=context["stale_lock_checksum"],
                created_at=now,
                updated_at=now,
            )
            session.add(operation)
            continuation.status = "blocked"
            continuation.worker_id = None
            continuation.lease_expires_at = None
            continuation.last_error_code = "RECOVERY_ACTION_REQUIRED"
            continuation.last_error_message = (
                f"Stage recovery {operation.id} owns deterministic recovery; use RECOVER_STAGE"
            )
            continuation.state_version += 1
            continuation.updated_at = now
            session.flush()
            self._operation_event(
                session,
                operation,
                WorkflowEventType.STAGE_RECOVERY_OPERATION_CREATED,
                "created",
                actor,
                "durable stage recovery operation created from immutable failure evidence",
            )
            return self._result(operation, continuation, False)

    def advance_next(self) -> bool:
        with self._scope() as session:
            operation = session.scalar(
                select(StageRecoveryOperationModel)
                .where(StageRecoveryOperationModel.status.in_(ACTIVE_RECOVERY_STATUSES))
                .order_by(StageRecoveryOperationModel.created_at)
                .limit(1)
            )
            if operation is None:
                return False
            operation_id = operation.id
            status = operation.status
            if status == "PLANNED":
                operation.status = "RECONSTRUCTING"
                operation.updated_at = self._now()
                return True
        try:
            if status == "RECONSTRUCTING":
                self._advance_reconstruction(operation_id)
            elif status == "RECONSTRUCTED":
                self._advance_classification(operation_id)
            elif status == "PREPARING":
                self._advance_preparation(operation_id)
            elif status in {"COMMAND_QUEUED", "COMMAND_RUNNING"}:
                self._advance_command(operation_id)
            elif status == "VERIFYING":
                self._advance_verification(operation_id)
            return True
        except StageRecoveryError as error:
            self._fail(operation_id, error.code, error.message)
            return True
        except (LockfileGenerationError, TransformerStageError, OSError, ValueError) as error:
            self._fail(
                operation_id,
                getattr(error, "code", "STAGE_RECOVERY_FAILED"),
                str(getattr(error, "message", error))[:2000],
            )
            return True

    def _resolve_context(self, session, continuation) -> dict[str, object]:
        run = session.get(MigrationRunModel, continuation.run_id)
        stage = session.get(MigrationStageModel, continuation.current_stage_id)
        binding = session.scalar(
            select(StageWorkspaceBindingModel).where(
                StageWorkspaceBindingModel.run_id == continuation.run_id,
                StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                StageWorkspaceBindingModel.active.is_(True),
            )
        )
        if run is None or stage is None or binding is None:
            raise StageRecoveryError(
                "STAGE_RECOVERY_AUTHORITY_MISSING",
                "Run, stage, and active workspace binding are required for recovery",
            )
        if continuation.status != "blocked" or continuation.current_node != "lockfile_generation":
            raise StageRecoveryError(
                "RECOVERY_ACTION_NOT_REQUIRED",
                "The current stage is not blocked at a recoverable lockfile boundary",
            )
        try:
            workspace = Path(binding.workspace_path).resolve(strict=True)
            workspace.relative_to(Path(run.run_root).resolve(strict=True))
            live = STAGE_FINGERPRINT_PROFILE.fingerprint(workspace)
        except (OSError, ValueError) as error:
            raise StageRecoveryError(
                "WORKSPACE_FINGERPRINT_MISMATCH",
                "The governed recovery workspace cannot be read safely",
            ) from error
        if live != binding.workspace_fingerprint:
            raise StageRecoveryError(
                "WORKSPACE_FINGERPRINT_MISMATCH",
                "Live workspace does not match its durable binding",
                {"live": live, "binding": binding.workspace_fingerprint},
            )
        step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.run_id == continuation.run_id,
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "lockfile_generation-0",
            )
        )
        interrupted = session.get(CommandExecutionModel, step.execution_id) if step and step.execution_id else None
        if not self._is_interrupted_lockfile(interrupted):
            interrupted = session.scalar(
                select(CommandExecutionModel)
                .where(
                    CommandExecutionModel.run_id == continuation.run_id,
                    CommandExecutionModel.stage_id == continuation.current_stage_id,
                    CommandExecutionModel.command_id == "npm-lockfile-generate",
                    CommandExecutionModel.status == "interrupted",
                    CommandExecutionModel.failure_code == "COMMAND_RECOVERY_REQUIRED",
                )
                .order_by(CommandExecutionModel.finished_at.desc())
                .limit(1)
            )
        if interrupted is None:
            raise StageRecoveryError(
                "COMMAND_RECOVERY_EVIDENCE_MISSING",
                "No interrupted governed lockfile command authorizes stage recovery",
            )
        causal = None
        for candidate in session.scalars(
            select(CommandExecutionModel)
            .where(
                CommandExecutionModel.run_id == continuation.run_id,
                CommandExecutionModel.stage_id == continuation.current_stage_id,
                CommandExecutionModel.command_id == "npm-lockfile-generate",
                CommandExecutionModel.status == "failed",
            )
            .order_by(CommandExecutionModel.finished_at.desc())
        ):
            if is_npm_eresolve_failure(candidate):
                causal = candidate
                break
        if causal is None:
            raise StageRecoveryError(
                "DEPENDENCY_STATE_RECOVERY_EVIDENCE_MISSING",
                "No immutable failed ERESOLVE lockfile execution authorizes reconciliation",
            )
        result = session.get(ArtifactMetadataModel, "metadata-" + str(causal.result_artifact_id))
        if result is None or not result.immutable or result.execution_id != causal.id:
            raise StageRecoveryError(
                "DEPENDENCY_STATE_RECOVERY_EVIDENCE_INVALID",
                "Causal ERESOLVE result evidence is missing or not immutable",
            )
        diagnosis = DependencyRepairPreflightService().classify_current_state(
            workspace=workspace,
            source_family=stage.source_version_family or "",
            target_family=stage.target_version_family or "",
        )
        if diagnosis.get("classification") != "TARGET_MANIFEST_AHEAD":
            raise StageRecoveryError(
                "DEPENDENCY_STATE_RECOVERY_NOT_APPLICABLE",
                f"Deterministic recovery requires TARGET_MANIFEST_AHEAD, got {diagnosis.get('classification')}",
            )
        attempt = self._select_applied_attempt(session, continuation, binding)
        checkpoint = session.get(StageCheckpointModel, attempt.checkpoint_id) if attempt else None
        if checkpoint is None or self._checkpoint_authority(session, checkpoint, binding) is None:
            raise StageRecoveryError(
                "CHECKPOINT_RECOVERY_AUTHORITY_MISSING",
                "No authoritative safe checkpoint is bound to the applied repair evidence",
            )
        start = causal.start_fingerprint or {}
        return {
            "kind": "RECONSTRUCT_THEN_RECONCILE",
            "run": run,
            "stage": stage,
            "binding": binding,
            "workspace": workspace,
            "live": live,
            "interrupted": interrupted,
            "causal": causal,
            "causal_evidence_checksum": result.checksum,
            "attempt": attempt,
            "checkpoint": checkpoint,
            "diagnosis": diagnosis,
            "manifest_checksum": self.file_checksum(workspace / "package.json"),
            "stale_lock_checksum": start.get("post_apply_pre_command_package_lock_sha256", "missing"),
            "source_workspace_fingerprint": binding.workspace_fingerprint,
        }

    @staticmethod
    def _is_interrupted_lockfile(execution) -> bool:
        return bool(
            execution is not None
            and execution.command_id == "npm-lockfile-generate"
            and execution.status == "interrupted"
            and execution.failure_code == "COMMAND_RECOVERY_REQUIRED"
        )

    def _select_applied_attempt(self, session, continuation, binding):
        for attempt in session.scalars(
            select(RepairAttemptModel)
            .where(
                RepairAttemptModel.run_id == continuation.run_id,
                RepairAttemptModel.stage_id == continuation.current_stage_id,
                RepairAttemptModel.status.in_(APPLIED_EVIDENCE_STATUSES),
                RepairAttemptModel.apply_ledger_artifact_id.is_not(None),
                RepairAttemptModel.apply_ledger_checksum.is_not(None),
            )
            .order_by(RepairAttemptModel.attempt_number.desc())
        ):
            checkpoint = session.get(StageCheckpointModel, attempt.checkpoint_id)
            gate = session.get(StageGatePackageModel, attempt.g10_gate_package_id)
            if (
                checkpoint is not None
                and gate is not None
                and gate.gate_id == "G10"
                and gate.status == "approved"
                and gate.stale_at is None
                and self._checkpoint_authority(session, checkpoint, binding) is not None
                and LockfileGenerationRunner._has_approved_dependency_change(
                    session, session.get(MigrationRunModel, continuation.run_id), attempt,
                    continuation.current_stage_id,
                )
            ):
                return attempt
        raise StageRecoveryError(
            "REPAIR_RECOVERY_AUTHORITY_MISSING",
            "No immutable applied G10-approved dependency repair authorizes recovery",
        )

    def _checkpoint_authority(self, session, checkpoint, binding) -> str | None:
        if (
            checkpoint.run_id != binding.run_id
            or checkpoint.stage_id != binding.stage_id
            or checkpoint.workspace_alias != binding.alias
            or checkpoint.kind not in {"pre_repair", "pre_angular_update"}
            or not checkpoint.safe_for_resume
        ):
            return None
        return self._stage.authoritative_checkpoint_fingerprint(session, checkpoint)

    @staticmethod
    def _supersede_non_executable_attempts(session, continuation, selected, now) -> None:
        for attempt in session.scalars(
            select(RepairAttemptModel)
            .where(
                RepairAttemptModel.run_id == continuation.run_id,
                RepairAttemptModel.stage_id == continuation.current_stage_id,
                RepairAttemptModel.attempt_number > selected.attempt_number,
            )
            .order_by(RepairAttemptModel.attempt_number)
        ):
            if attempt.status in {"superseded", "rejected", "cancelled"}:
                continue
            try:
                RepairLifecycleService.transition_in_session(
                    session,
                    attempt,
                    "superseded",
                    reason="stage recovery selected immutable applied dependency evidence",
                    now=now,
                )
            except Exception as error:
                raise StageRecoveryError(
                    "REPAIR_RECOVERY_LINEAGE_INVALID",
                    f"Non-executable repair attempt {attempt.id} cannot be superseded safely",
                ) from error
            gate = session.get(StageGatePackageModel, attempt.g10_gate_package_id)
            if gate is not None and gate.status == "pending":
                gate.status = "stale"
                gate.stale_at = now

    def _advance_reconstruction(self, operation_id: str) -> None:
        with self._scope() as session:
            operation = session.get(StageRecoveryOperationModel, operation_id)
            if operation is None or operation.status != "RECONSTRUCTING":
                return
            continuation = session.get(TransformationContinuationModel, operation.run_id)
            checkpoint = session.get(StageCheckpointModel, operation.checkpoint_id)
            run = session.get(MigrationRunModel, operation.run_id)
            if continuation is None or checkpoint is None or run is None:
                raise StageRecoveryError("RECOVERY_AUTHORITY_MISSING", "Recovery operation bindings are incomplete")
            binding = session.scalar(
                select(StageWorkspaceBindingModel).where(
                    StageWorkspaceBindingModel.run_id == operation.run_id,
                    StageWorkspaceBindingModel.stage_id == operation.stage_id,
                    StageWorkspaceBindingModel.active.is_(True),
                )
            )
            if binding is None:
                raise StageRecoveryError("WORKSPACE_BINDING_MISSING", "Active stage workspace binding is missing")
            expected = self._checkpoint_authority(session, checkpoint, binding)
            if expected is None:
                raise StageRecoveryError("CHECKPOINT_INTEGRITY_FAILED", "Recovery checkpoint is not authoritative")
            live = STAGE_FINGERPRINT_PROFILE.fingerprint(Path(binding.workspace_path))
            self._stage.begin_reconstruction(
                session,
                continuation,
                checkpoint=checkpoint,
                reason="stage_recovery_operation",
                execution_id=operation.causal_execution_id,
                attempt_id=operation.repair_attempt_id,
                mode=ReconstructionMode.RECOVERY_OPERATION,
                recovery_operation_id=operation.id,
            )
            source = checkpoint.workspace_path
            target = binding.workspace_path
            stage_root = run.run_root
            snapshot_root = run.artifact_root
            session.commit()
        if live != expected:
            TransformerStageService.reconstruct_workspace(
                source,
                target,
                stage_root,
                expected,
                snapshot_root,
            )
        with self._scope() as session:
            operation = session.get(StageRecoveryOperationModel, operation_id)
            continuation = session.get(TransformationContinuationModel, operation.run_id)
            checkpoint = session.get(StageCheckpointModel, operation.checkpoint_id)
            binding = session.scalar(
                select(StageWorkspaceBindingModel).where(
                    StageWorkspaceBindingModel.run_id == operation.run_id,
                    StageWorkspaceBindingModel.stage_id == operation.stage_id,
                    StageWorkspaceBindingModel.active.is_(True),
                )
            )
            expected = self._checkpoint_authority(session, checkpoint, binding)
            restored = STAGE_FINGERPRINT_PROFILE.fingerprint(Path(binding.workspace_path))
            if restored != expected:
                raise StageRecoveryError(
                    "WORKSPACE_RECONSTRUCTION_FINGERPRINT_MISMATCH",
                    "Reconstructed workspace does not match the authoritative checkpoint",
                )
            self._stage.record_reconstruction(
                session,
                continuation,
                checkpoint=checkpoint,
                reason="stage_recovery_operation",
                restored_fingerprint=restored,
                execution_id=operation.causal_execution_id,
                attempt_id=operation.repair_attempt_id,
                mode=ReconstructionMode.RECOVERY_OPERATION,
                recovery_operation_id=operation.id,
            )
            cas = session.execute(
                update(StageWorkspaceBindingModel)
                .where(
                    StageWorkspaceBindingModel.id == binding.id,
                    StageWorkspaceBindingModel.active.is_(True),
                    StageWorkspaceBindingModel.workspace_fingerprint
                    == operation.source_workspace_fingerprint,
                )
                .values(
                    workspace_fingerprint=restored,
                    last_verified_fingerprint=restored,
                    last_verified_at=self._now(),
                )
            )
            if cas.rowcount != 1 and binding.workspace_fingerprint != restored:
                raise StageRecoveryError(
                    "WORKSPACE_BINDING_STALE",
                    "Active workspace binding changed during reconstruction",
                )
            operation.status = "RECONSTRUCTED"
            operation.source_workspace_fingerprint = restored
            operation.updated_at = self._now()

    def _advance_classification(self, operation_id: str) -> None:
        with self._scope() as session:
            operation = session.get(StageRecoveryOperationModel, operation_id)
            if operation is None or operation.status != "RECONSTRUCTED":
                return
            continuation = session.get(TransformationContinuationModel, operation.run_id)
            stage = session.get(MigrationStageModel, operation.stage_id)
            binding = session.scalar(
                select(StageWorkspaceBindingModel).where(
                    StageWorkspaceBindingModel.run_id == operation.run_id,
                    StageWorkspaceBindingModel.stage_id == operation.stage_id,
                    StageWorkspaceBindingModel.active.is_(True),
                )
            )
            diagnosis = DependencyRepairPreflightService().classify_current_state(
                workspace=Path(binding.workspace_path),
                source_family=stage.source_version_family or "",
                target_family=stage.target_version_family or "",
            )
            if diagnosis.get("classification") != "TARGET_MANIFEST_AHEAD":
                raise StageRecoveryError(
                    "DEPENDENCY_STATE_RECOVERY_NOT_APPLICABLE",
                    f"Recovery classification changed to {diagnosis.get('classification')}",
                )
            operation.manifest_checksum = self.file_checksum(Path(binding.workspace_path) / "package.json")
            operation.status = "PREPARING"
            operation.updated_at = self._now()

    def _advance_preparation(self, operation_id: str) -> None:
        with self._scope() as session:
            operation = session.get(StageRecoveryOperationModel, operation_id)
            if operation is None or operation.status != "PREPARING":
                return
            continuation = session.get(TransformationContinuationModel, operation.run_id)
            causal = session.get(CommandExecutionModel, operation.causal_execution_id)
            step = session.scalar(
                select(StageStepModel).where(
                    StageStepModel.run_id == operation.run_id,
                    StageStepModel.stage_id == operation.stage_id,
                    StageStepModel.name == "lockfile_generation-0",
                )
            )
            if continuation is None or causal is None or step is None:
                raise StageRecoveryError("RECOVERY_AUTHORITY_MISSING", "Recovery lockfile command authority is incomplete")
            step.execution_id = causal.id
            step.status = "FAILED"
            step.completed_at = causal.finished_at
            outcome = self._lockfiles._queue_stale_lock_reconciliation(
                session,
                continuation,
                causal,
                recovery_id=operation.id,
                recovery_owned=True,
            )
            owner_prefix = operation.id + ":stale-lock:"
            preparation = session.scalar(
                select(ArtifactMetadataModel)
                .where(
                    ArtifactMetadataModel.run_id == operation.run_id,
                    ArtifactMetadataModel.stage_id == operation.stage_id,
                    ArtifactMetadataModel.owner_reference.like(owner_prefix + "%"),
                    ArtifactMetadataModel.immutable.is_(True),
                )
                .order_by(ArtifactMetadataModel.created_at.desc())
            )
            operation.preparation_artifact_id = (
                preparation.id.removeprefix("metadata-") if preparation else operation.preparation_artifact_id
            )
            operation.preparation_checksum = preparation.checksum if preparation else operation.preparation_checksum
            operation.stale_lock_checksum = (
                (causal.start_fingerprint or {}).get("post_apply_pre_command_package_lock_sha256")
                or operation.stale_lock_checksum
            )
            operation.prepared_workspace_fingerprint = self._binding_fingerprint(session, operation)
            if outcome == "queued":
                operation.command_execution_id = step.execution_id
                operation.status = "COMMAND_QUEUED"
            operation.updated_at = self._now()

    def _advance_command(self, operation_id: str) -> None:
        with self._scope() as session:
            operation = session.get(StageRecoveryOperationModel, operation_id)
            if operation is None or operation.status not in {"COMMAND_QUEUED", "COMMAND_RUNNING"}:
                return
            execution = session.get(CommandExecutionModel, operation.command_execution_id)
            if execution is None:
                raise StageRecoveryError("RECOVERY_COMMAND_MISSING", "Recovery command execution is missing")
            if execution.status in {"queued", "pending"}:
                return
            if execution.status == "running":
                operation.status = "COMMAND_RUNNING"
                operation.updated_at = self._now()
                return
            if execution.status != "succeeded" or execution.exit_code != 0:
                raise StageRecoveryError(
                    execution.failure_code or "STAGE_RECOVERY_COMMAND_FAILED",
                    execution.failure_message or "Recovery command failed",
                )
            operation.status = "VERIFYING"
            operation.updated_at = self._now()

    def _advance_verification(self, operation_id: str) -> None:
        with self._scope() as session:
            operation = session.get(StageRecoveryOperationModel, operation_id)
            if operation is None or operation.status != "VERIFYING":
                return
            continuation = session.get(TransformationContinuationModel, operation.run_id)
            step = session.scalar(
                select(StageStepModel).where(
                    StageStepModel.run_id == operation.run_id,
                    StageStepModel.stage_id == operation.stage_id,
                    StageStepModel.name == "lockfile_generation-0",
                )
            )
            execution = session.get(CommandExecutionModel, operation.command_execution_id)
            if continuation is None or step is None or execution is None:
                raise StageRecoveryError("RECOVERY_VERIFICATION_EVIDENCE_MISSING", "Recovery verification evidence is incomplete")
            self._lockfiles._verify(session, continuation, step, execution)
            self._lockfiles._record_catalogue_evidence(session, continuation, execution)
            for validation_step in session.query(StageStepModel).filter(
                StageStepModel.stage_id == operation.stage_id,
                (
                    StageStepModel.name.like("final_install-%")
                    | StageStepModel.name.like("builds-%")
                    | StageStepModel.name.like("tests-%")
                    | StageStepModel.name.like("lint-%")
                ),
            ):
                validation_step.status = "PENDING"
                validation_step.execution_id = None
                validation_step.completed_at = None
                validation_step.updated_at = self._now()
            operation.status = "COMPLETED"
            operation.completed_at = self._now()
            operation.updated_at = operation.completed_at
            continuation.status = "queued"
            continuation.current_node = "final_install"
            continuation.worker_id = None
            continuation.lease_expires_at = None
            continuation.waiting_execution_id = None
            continuation.last_error_code = None
            continuation.last_error_message = None
            expected_state_version = continuation.state_version
            continuation.state_version += 1
            continuation.updated_at = self._now()
            self._operation_event(
                session,
                operation,
                WorkflowEventType.STAGE_RECOVERY_OPERATION_COMPLETED,
                "completed",
                "transformer",
                "durable stage recovery completed and returned the stage to normal validation",
            )
            append_continuation_event(
                session,
                continuation,
                event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_RESUMED,
                key=f"stage-recovery:{operation.id}:handoff",
                reason="stage recovery completed; normal stage validation resumed",
                payload={
                    "recovery_id": operation.id,
                    "execution_id": execution.id,
                    "expected_state_version": expected_state_version,
                },
            )

    def _fail(self, operation_id: str, code: str, message: str) -> None:
        with self._scope() as session:
            operation = session.get(StageRecoveryOperationModel, operation_id)
            if operation is None or operation.status in {"COMPLETED", "FAILED"}:
                return
            continuation = session.get(TransformationContinuationModel, operation.run_id)
            operation.status = "FAILED"
            operation.last_error_code = code
            operation.last_error_message = message[:4000]
            operation.updated_at = self._now()
            if continuation is not None:
                expected_state_version = continuation.state_version
                continuation.status = "blocked"
                continuation.current_node = "lockfile_generation"
                continuation.worker_id = None
                continuation.lease_expires_at = None
                continuation.waiting_execution_id = None
                continuation.last_error_code = code
                continuation.last_error_message = message[:2000]
                continuation.state_version += 1
                continuation.updated_at = self._now()
                append_continuation_event(
                    session,
                    continuation,
                    event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_BLOCKED,
                    key=f"stage-recovery:{operation.id}:failed:{code}",
                    reason=message[:500],
                    payload={
                        "recovery_id": operation.id,
                        "last_error_code": code,
                        "expected_state_version": expected_state_version,
                    },
                )
            self._operation_event(
                session,
                operation,
                WorkflowEventType.STAGE_RECOVERY_OPERATION_FAILED,
                f"failed:{code}",
                "transformer",
                message[:500],
            )

    @staticmethod
    def _active(session, run_id: str, stage_id: str):
        return session.scalar(
            select(StageRecoveryOperationModel)
            .where(
                StageRecoveryOperationModel.run_id == run_id,
                StageRecoveryOperationModel.stage_id == stage_id,
                StageRecoveryOperationModel.status.in_(ACTIVE_RECOVERY_STATUSES),
            )
            .order_by(StageRecoveryOperationModel.created_at.desc())
            .limit(1)
        )

    @staticmethod
    def _binding_fingerprint(session, operation) -> str | None:
        binding = session.scalar(
            select(StageWorkspaceBindingModel).where(
                StageWorkspaceBindingModel.run_id == operation.run_id,
                StageWorkspaceBindingModel.stage_id == operation.stage_id,
                StageWorkspaceBindingModel.active.is_(True),
            )
        )
        return binding.workspace_fingerprint if binding else None

    @staticmethod
    def _operation_event(session, operation, event_type, suffix, actor, reason) -> None:
        StateTransitionService(session).append_audit_event(
            run_id=operation.run_id,
            idempotency_key=f"stage-recovery:{operation.id}:{suffix}",
            event_type=event_type,
            actor=actor,
            reason=reason,
            occurred_at=operation.updated_at,
            payload={
                "recovery_id": operation.id,
                "stage_id": operation.stage_id,
                "kind": operation.kind,
                "status": operation.status,
                "causal_execution_id": operation.causal_execution_id,
                "checkpoint_id": operation.checkpoint_id,
                "command_execution_id": operation.command_execution_id,
                "last_error_code": operation.last_error_code,
            },
        )

    @staticmethod
    def _result(operation, continuation, replay: bool) -> dict[str, object]:
        return {
            "run_id": operation.run_id,
            "stage_id": operation.stage_id,
            "recovery_id": operation.id,
            "kind": operation.kind,
            "status": operation.status,
            "state_version": continuation.state_version,
            "causal_execution_id": operation.causal_execution_id,
            "interrupted_execution_id": operation.interrupted_execution_id,
            "checkpoint_id": operation.checkpoint_id,
            "repair_attempt_id": operation.repair_attempt_id,
            "command_execution_id": operation.command_execution_id,
            "required_action": "RECOVER_STAGE",
            "idempotent_replay": replay,
        }
