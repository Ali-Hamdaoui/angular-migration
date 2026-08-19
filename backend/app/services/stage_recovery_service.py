"""One durable, restart-safe owner for deterministic stage recovery."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, update

from app.artifact_store import ArtifactNotFoundError, ArtifactStoreError, LocalFilesystemArtifactStore
from app.domain.contracts import WorkflowEventType
from app.repositories.models import (
    ArtifactMetadataModel,
    CommandAuthorizationAuditModel,
    CommandExecutionModel,
    MigrationRunModel,
    MigrationStageModel,
    RepairAttemptModel,
    StageCheckpointModel,
    StageGateDecisionModel,
    StageGatePackageModel,
    StageRecoveryOperationModel,
    StageStepModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
    WorkflowEventModel,
)
from app.repositories.session import session_scope
from app.services.dependency_repair_preflight_service import (
    DependencyRepairPreflightService,
)
from app.services.lockfile_generation_runner import (
    LockfileGenerationError,
    LockfileGenerationRunner,
    is_npm_eresolve_failure,
    workspace_excluding_governed_volatile_fingerprint,
)
from app.services.patch_apply_service import PatchApplyService
from app.services.repair_application_service import RepairApplicationError
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
PROVEN_INTERRUPTED_PREPARATION_DRIFT = "PROVEN_INTERRUPTED_PREPARATION_DRIFT"
EXPECTED_LOCKFILE_ARGUMENTS = [
    "install",
    "--package-lock-only",
    "--ignore-scripts",
    "--no-audit",
    "--no-fund",
]


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
        self._patches = PatchApplyService(now_provider=self._now)

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

    @classmethod
    def normal_failure_handoff_allowed(cls, session, continuation) -> bool:
        if continuation.last_error_code != "LOCKFILE_RECONCILIATION_WORKSPACE_STALE":
            return False
        active = session.scalar(
            select(StageRecoveryOperationModel).where(
                StageRecoveryOperationModel.run_id == continuation.run_id,
                StageRecoveryOperationModel.stage_id == continuation.current_stage_id,
                StageRecoveryOperationModel.status.in_(ACTIVE_RECOVERY_STATUSES),
            )
        )
        if active is not None:
            return False
        operation = session.scalar(
            select(StageRecoveryOperationModel)
            .where(
                StageRecoveryOperationModel.run_id == continuation.run_id,
                StageRecoveryOperationModel.stage_id == continuation.current_stage_id,
                StageRecoveryOperationModel.status == "FAILED",
            )
            .order_by(StageRecoveryOperationModel.updated_at.desc())
        )
        execution = (
            session.get(CommandExecutionModel, operation.command_execution_id)
            if operation is not None and operation.command_execution_id
            else None
        )
        return bool(
            operation is not None
            and operation.last_error_code == "COMMAND_EXIT_NONZERO"
            and execution is not None
            and execution.command_id == "npm-lockfile-generate"
            and execution.status == "failed"
            and is_npm_eresolve_failure(execution)
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
                "observed_workspace_fingerprint": context["observed_workspace_fingerprint"],
                "governed_workspace_fingerprint": context["governed_workspace_fingerprint"],
                "drift_classification": context["drift_classification"],
                "interrupted_evidence_checksum": context["interrupted_evidence_checksum"],
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
                continuation_id=continuation.id,
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
                observed_workspace_fingerprint=context["observed_workspace_fingerprint"],
                governed_workspace_fingerprint=context["governed_workspace_fingerprint"],
                drift_classification=context["drift_classification"],
                interrupted_evidence_checksum=context["interrupted_evidence_checksum"],
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

    def retry_failed(
        self,
        *,
        run_id: str,
        recovery_id: str,
        expected_state_version: int,
        idempotency_key: str,
        actor: str,
        correlation_id: str | None = None,
    ) -> dict[str, object]:
        """Reactivate a failed pre-external-work recovery without a new operation."""
        with self._scope() as session:
            continuation = session.scalar(
                select(TransformationContinuationModel).where(
                    TransformationContinuationModel.run_id == run_id
                )
            )
            operation = session.get(StageRecoveryOperationModel, recovery_id)
            if operation is None or operation.run_id != run_id:
                raise StageRecoveryError(
                    "RECOVERY_NOT_FOUND", "Stage recovery operation is missing"
                )
            if continuation is None:
                raise StageRecoveryError(
                    "TRANSFORMATION_NOT_FOUND", "Transformer continuation is missing"
                )
            self._continuation_for_operation(session, operation)
            request_payload = {
                "run_id": run_id,
                "recovery_id": recovery_id,
                "continuation_id": continuation.id,
                "expected_state_version": expected_state_version,
                "idempotency_key": idempotency_key,
                "correlation_id": correlation_id,
                "recovery_checksum": operation.recovery_checksum,
                "actor": actor,
            }
            request_checksum = self.checksum(request_payload)
            retry_suffix = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:16]
            event_key = f"stage-recovery:{operation.id}:retry:{retry_suffix}"
            event = session.scalar(
                select(WorkflowEventModel).where(
                    WorkflowEventModel.run_id == run_id,
                    WorkflowEventModel.idempotency_key == f"{continuation.id}:{event_key}",
                )
            )
            if event is not None:
                if (event.payload or {}).get("request_checksum") != request_checksum:
                    raise StageRecoveryError(
                        "IDEMPOTENCY_PAYLOAD_MISMATCH",
                        "Recovery retry key was already used with a different payload",
                    )
                return self._result(operation, continuation, True)
            if operation.status != "FAILED":
                raise StageRecoveryError(
                    "RECOVERY_RETRY_NOT_ELIGIBLE",
                    "Only a failed stage recovery can be retried",
                )
            if continuation.state_version != expected_state_version:
                raise StageRecoveryError(
                    "TRANSFORMATION_STATE_CONFLICT",
                    "Transformer state changed; refresh authoritative state",
                )
            if operation.last_error_code not in {
                "RECOVERY_AUTHORITY_MISSING",
                "STAGE_RECOVERY_AUTHORITY_MISSING",
                "RECOVERY_CONTINUATION_AUTHORITY_INVALID",
                "RECONSTRUCTION_AUTHORIZATION_INVALID",
                "LOCKFILE_RECONCILIATION_WORKSPACE_STALE",
                "WORKSPACE_BINDING_STALE",
            }:
                raise StageRecoveryError(
                    "RECOVERY_RETRY_NOT_SAFE",
                    "Recovery progressed beyond a safely replayable pre-external-work boundary",
                )
            if any(
                getattr(operation, field) is not None
                for field in (
                    "command_execution_id",
                    "preparation_artifact_id",
                    "prepared_workspace_fingerprint",
                )
            ):
                raise StageRecoveryError(
                    "RECOVERY_RETRY_NOT_SAFE",
                    "Recovery has durable external-work evidence and cannot restart blindly",
                )
            active_command = session.scalar(
                select(CommandExecutionModel.id).where(
                    CommandExecutionModel.run_id == run_id,
                    CommandExecutionModel.stage_id == operation.stage_id,
                    CommandExecutionModel.status.in_(("queued", "pending", "running")),
                )
            )
            if active_command is not None:
                raise StageRecoveryError(
                    "RECOVERY_RETRY_NOT_SAFE",
                    "An active command still owns the recovery boundary",
                )
            now = self._now()
            operation.status = "RECONSTRUCTING"
            operation.last_error_code = None
            operation.last_error_message = None
            operation.updated_at = now
            continuation.status = "blocked"
            continuation.current_node = "lockfile_generation"
            continuation.worker_id = None
            continuation.lease_expires_at = None
            continuation.waiting_execution_id = None
            continuation.last_error_code = "RECOVERY_ACTION_REQUIRED"
            continuation.last_error_message = (
                f"Stage recovery {operation.id} retry is active; use RECOVER_STAGE"
            )
            previous_state_version = continuation.state_version
            continuation.state_version += 1
            continuation.updated_at = now
            append_continuation_event(
                session,
                continuation,
                event_type=WorkflowEventType.STAGE_RECOVERY_OPERATION_RETRIED,
                key=event_key,
                reason="failed stage recovery retried from its durable pre-external-work boundary",
                actor=actor,
                occurred_at=now,
                payload={
                    "recovery_id": operation.id,
                    "request_checksum": request_checksum,
                    "recovery_checksum": operation.recovery_checksum,
                    "previous_state_version": previous_state_version,
                    "next_state_version": continuation.state_version,
                    "retry_status": operation.status,
                    "correlation_id": correlation_id,
                },
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
        step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.run_id == continuation.run_id,
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "lockfile_generation-0",
            )
        )
        interrupted, drift = self._select_interrupted_preparation(
            session,
            run,
            continuation.current_stage_id,
            binding,
            workspace,
            live,
            step,
        )
        causal = None
        causal_evidence = None
        package_checksum = self.file_checksum(workspace / "package.json")
        governed_checksum = workspace_excluding_governed_volatile_fingerprint(workspace)
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
            start = candidate.start_fingerprint or {}
            if (
                not is_npm_eresolve_failure(candidate)
                or start.get("post_apply_pre_command_binding_fingerprint")
                != binding.workspace_fingerprint
                or start.get("post_apply_pre_command_package_json_sha256")
                != package_checksum
                or start.get("post_apply_pre_command_governed_workspace_fingerprint")
                != governed_checksum
            ):
                continue
            try:
                causal_evidence = self._validate_causal_evidence(
                    session,
                    run,
                    continuation.current_stage_id,
                    candidate,
                )
            except StageRecoveryError:
                continue
            causal = candidate
            break
        if causal is None:
            raise StageRecoveryError(
                "DEPENDENCY_STATE_RECOVERY_EVIDENCE_MISSING",
                "No immutable failed ERESOLVE lockfile execution authorizes reconciliation",
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
            "causal_evidence_checksum": causal_evidence["checksum"],
            "interrupted_evidence_checksum": drift["evidence_checksum"],
            "attempt": attempt,
            "checkpoint": checkpoint,
            "diagnosis": diagnosis,
            "manifest_checksum": self.file_checksum(workspace / "package.json"),
            "stale_lock_checksum": start.get("post_apply_pre_command_package_lock_sha256", "missing"),
            "source_workspace_fingerprint": binding.workspace_fingerprint,
            "observed_workspace_fingerprint": drift["observed_workspace_fingerprint"],
            "governed_workspace_fingerprint": drift["governed_workspace_fingerprint"],
            "drift_classification": drift["classification"],
        }

    @staticmethod
    def _is_interrupted_lockfile(execution) -> bool:
        return bool(
            execution is not None
            and execution.command_id == "npm-lockfile-generate"
            and execution.status == "interrupted"
            and execution.failure_code == "COMMAND_RECOVERY_REQUIRED"
        )

    def _select_interrupted_preparation(
        self,
        session,
        run,
        stage_id: str,
        binding,
        workspace: Path,
        live: str,
        step,
    ) -> tuple[object, dict[str, str]]:
        candidates = []
        seen = set()
        if step is not None and step.execution_id:
            pointed = session.get(CommandExecutionModel, step.execution_id)
            if pointed is not None:
                candidates.append(pointed)
                seen.add(pointed.id)
        candidates.extend(
            candidate
            for candidate in session.scalars(
                select(CommandExecutionModel)
                .where(
                    CommandExecutionModel.run_id == run.id,
                    CommandExecutionModel.stage_id == stage_id,
                    CommandExecutionModel.command_id == "npm-lockfile-generate",
                    CommandExecutionModel.status == "interrupted",
                )
                .order_by(CommandExecutionModel.requested_at.desc())
            )
            if candidate.id not in seen
        )
        for candidate in candidates:
            if not self._is_interrupted_lockfile(candidate):
                continue
            try:
                drift = self._validate_interrupted_preparation(
                    session,
                    run,
                    stage_id,
                    binding,
                    workspace,
                    live,
                    step,
                    candidate,
                    require_stage_step_pointer=False,
                )
            except StageRecoveryError:
                continue
            if step is not None and step.execution_id != candidate.id:
                step.execution_id = candidate.id
            return candidate, drift
        raise StageRecoveryError(
            "COMMAND_RECOVERY_EVIDENCE_MISSING",
            "No interrupted governed command matches the current workspace authority",
        )

    def _validate_interrupted_preparation(
        self,
        session,
        run,
        stage_id: str,
        binding,
        workspace: Path,
        live: str,
        step,
        execution,
        *,
        require_stage_step_pointer: bool = True,
    ) -> dict[str, str]:
        start = execution.start_fingerprint or {}
        if (
            execution.run_id != run.id
            or execution.stage_id != stage_id
            or (
                require_stage_step_pointer
                and (step is None or step.execution_id != execution.id)
            )
            or execution.arguments != EXPECTED_LOCKFILE_ARGUMENTS
            or start.get("fingerprint_scope") != "lockfile-generation-mutation-v2"
        ):
            raise StageRecoveryError(
                "WORKSPACE_AUTHORITY_MISMATCH",
                "Interrupted lockfile preparation is not bound to the current stage authority",
            )
        authorization = session.get(CommandAuthorizationAuditModel, execution.authorization_id)
        authorization_artifacts = list(authorization.artifact_ids or []) if authorization else []
        if (
            authorization is None
            or authorization.run_id != run.id
            or authorization.stage_id != stage_id
            or authorization.command_id != execution.command_id
            or authorization.decision != "accepted"
            or not authorization_artifacts
        ):
            raise StageRecoveryError(
                "WORKSPACE_AUTHORITY_MISMATCH",
                "Interrupted lockfile preparation lacks accepted immutable authorization evidence",
            )
        evidence_refs = [
            self._validated_artifact(
                session,
                run,
                stage_id,
                artifact_id,
                expected_execution_id=None,
            )
            for artifact_id in authorization_artifacts
        ]
        for artifact_id in execution.artifact_ids or []:
            evidence_refs.append(
                self._validated_artifact(
                    session,
                    run,
                    stage_id,
                    artifact_id,
                    expected_execution_id=execution.id,
                )
            )
        expected_binding = start.get("post_apply_pre_command_binding_fingerprint")
        expected_package = start.get("post_apply_pre_command_package_json_sha256")
        expected_lock = start.get("post_apply_pre_command_package_lock_sha256")
        expected_governed = start.get("post_apply_pre_command_governed_workspace_fingerprint")
        actual_package = self.file_checksum(workspace / "package.json")
        actual_lock = self.file_checksum(workspace / "package-lock.json")
        actual_governed = workspace_excluding_governed_volatile_fingerprint(workspace)
        lockfile_drift_proven = (
            expected_lock == actual_lock
            or (
                execution.command_id == "npm-lockfile-generate"
                and execution.status == "interrupted"
                and execution.failure_code == "COMMAND_RECOVERY_REQUIRED"
                and expected_package == actual_package
                and expected_governed == actual_governed
            )
        )
        if (
            expected_binding != binding.workspace_fingerprint
            or expected_package != actual_package
            or not lockfile_drift_proven
            or expected_governed != actual_governed
        ):
            raise StageRecoveryError(
                "WORKSPACE_AUTHORITY_MISMATCH",
                "Live workspace drift is not fully proven by the interrupted preparation evidence",
                {
                    "binding": binding.workspace_fingerprint,
                    "live": live,
                    "expected_package": expected_package,
                    "actual_package": actual_package,
                    "expected_lock": expected_lock,
                    "actual_lock": actual_lock,
                    "expected_governed": expected_governed,
                    "actual_governed": actual_governed,
                },
            )
        evidence_checksum = self.checksum(
            {
                "execution_id": execution.id,
                "authorization_id": authorization.id,
                "stage_step_id": step.id,
                "start_fingerprint": start,
                "artifact_refs": evidence_refs,
                "observed_workspace_fingerprint": live,
                "expected_lockfile_checksum": expected_lock,
                "observed_lockfile_checksum": actual_lock,
                "governed_workspace_fingerprint": actual_governed,
            }
        )
        return {
            "classification": (
                PROVEN_INTERRUPTED_PREPARATION_DRIFT
                if live != binding.workspace_fingerprint
                else "NORMAL_AUTHORITY"
            ),
            "observed_workspace_fingerprint": live,
            "governed_workspace_fingerprint": actual_governed,
            "evidence_checksum": evidence_checksum,
        }

    def _validate_causal_evidence(
        self,
        session,
        run,
        stage_id: str,
        execution,
    ) -> dict[str, str]:
        artifact_refs = []
        for field in (
            "stdout_artifact_id",
            "stderr_artifact_id",
            "command_log_artifact_id",
            "manifest_artifact_id",
            "result_artifact_id",
        ):
            artifact_refs.append(
                self._validated_artifact(
                    session,
                    run,
                    stage_id,
                    getattr(execution, field),
                    expected_execution_id=execution.id,
                )
            )
        return {
            "checksum": self.checksum(
                {"execution_id": execution.id, "artifacts": artifact_refs}
            )
        }

    @staticmethod
    def _validated_artifact(
        session,
        run,
        stage_id: str,
        artifact_id: str | None,
        *,
        expected_execution_id: str | None,
    ) -> dict[str, str]:
        if not artifact_id:
            raise StageRecoveryError(
                "WORKSPACE_AUTHORITY_MISMATCH",
                "Required immutable recovery evidence is missing",
            )
        clean_id = str(artifact_id).removeprefix("metadata-")
        metadata = session.get(ArtifactMetadataModel, "metadata-" + clean_id)
        if (
            metadata is None
            or metadata.run_id != run.id
            or metadata.stage_id != stage_id
            or not metadata.immutable
            or (expected_execution_id is not None and metadata.execution_id != expected_execution_id)
        ):
            raise StageRecoveryError(
                "WORKSPACE_AUTHORITY_MISMATCH",
                "Recovery evidence metadata is missing, mutable, or cross-bound",
            )
        try:
            store = LocalFilesystemArtifactStore(
                Path(run.artifact_root).parent,
                fixed_run_root=Path(run.artifact_root),
            )
            stored = store.read_artifact(run.id, metadata.relative_path)
        except (ArtifactNotFoundError, ArtifactStoreError, OSError) as error:
            raise StageRecoveryError(
                "WORKSPACE_AUTHORITY_MISMATCH",
                "Recovery evidence bytes are missing or checksum-invalid",
            ) from error
        if stored.ref.artifact_id != clean_id or stored.ref.checksum != metadata.checksum:
            raise StageRecoveryError(
                "WORKSPACE_AUTHORITY_MISMATCH",
                "Recovery evidence checksum does not match durable metadata",
            )
        return {"artifact_id": clean_id, "checksum": metadata.checksum}

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
            continuation = self._continuation_for_operation(session, operation)
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
            continuation = self._continuation_for_operation(session, operation)
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
            binding_preimages = {
                operation.source_workspace_fingerprint,
                operation.observed_workspace_fingerprint,
            }
            cas = session.execute(
                update(StageWorkspaceBindingModel)
                .where(
                    StageWorkspaceBindingModel.id == binding.id,
                    StageWorkspaceBindingModel.active.is_(True),
                    StageWorkspaceBindingModel.workspace_fingerprint.in_(
                        binding_preimages
                    ),
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
        replay_context = None
        with self._scope() as session:
            operation = session.get(StageRecoveryOperationModel, operation_id)
            if operation is None or operation.status != "RECONSTRUCTED":
                return
            continuation = self._continuation_for_operation(session, operation)
            stage = session.get(MigrationStageModel, operation.stage_id)
            binding = session.scalar(
                select(StageWorkspaceBindingModel).where(
                    StageWorkspaceBindingModel.run_id == operation.run_id,
                    StageWorkspaceBindingModel.stage_id == operation.stage_id,
                    StageWorkspaceBindingModel.active.is_(True),
                )
            )
            if stage is None or binding is None:
                raise StageRecoveryError(
                    "RECOVERY_AUTHORITY_MISSING",
                    "Recovery stage or workspace binding is missing",
                )
            replay_context = self._approved_repair_replay_context(
                session, operation, continuation, binding
            )

        replay_artifacts = ()
        if replay_context is not None and replay_context["needs_apply"]:
            try:
                prepared, ledger, fingerprint = self._patches.apply(
                    proposal=replay_context["proposal"],
                    workspace_path=replay_context["workspace_path"],
                    expected_fingerprint=replay_context["pre_fingerprint"],
                    run_id=replay_context["run_id"],
                    stage_id=replay_context["stage_id"],
                    artifact_root=replay_context["artifact_root"],
                    attempt_id=replay_context["attempt_id"],
                    approved_proposal_checksum=replay_context["proposal_checksum"],
                    proposal_artifact_checksum=replay_context["proposal_checksum"],
                )
            except RepairApplicationError as error:
                raise StageRecoveryError(
                    "REPAIR_RECOVERY_REPLAY_INVALID",
                    error.message,
                ) from error
            if fingerprint != replay_context["post_fingerprint"]:
                raise StageRecoveryError(
                    "REPAIR_RECOVERY_REPLAY_INVALID",
                    "Approved repair replay produced an unexpected workspace fingerprint",
                )
            replay_artifacts = (prepared, ledger)

        with self._scope() as session:
            operation = session.get(StageRecoveryOperationModel, operation_id)
            if operation is None or operation.status != "RECONSTRUCTED":
                return
            continuation = self._continuation_for_operation(session, operation)
            binding = session.scalar(
                select(StageWorkspaceBindingModel).where(
                    StageWorkspaceBindingModel.run_id == operation.run_id,
                    StageWorkspaceBindingModel.stage_id == operation.stage_id,
                    StageWorkspaceBindingModel.active.is_(True),
                )
            )
            if replay_context is not None:
                live = STAGE_FINGERPRINT_PROFILE.fingerprint(
                    Path(replay_context["workspace_path"])
                )
                if live != replay_context["post_fingerprint"]:
                    raise StageRecoveryError(
                        "REPAIR_RECOVERY_REPLAY_INVALID",
                        "Approved repair replay post-state is not authoritative",
                    )
                if binding.workspace_fingerprint not in {
                    replay_context["pre_fingerprint"],
                    replay_context["post_fingerprint"],
                }:
                    raise StageRecoveryError(
                        "WORKSPACE_BINDING_STALE",
                        "Workspace binding changed during approved repair replay",
                    )
                if binding.workspace_fingerprint != live:
                    changed = session.execute(
                        update(StageWorkspaceBindingModel)
                        .where(
                            StageWorkspaceBindingModel.id == binding.id,
                            StageWorkspaceBindingModel.active.is_(True),
                            StageWorkspaceBindingModel.workspace_fingerprint
                            == replay_context["pre_fingerprint"],
                        )
                        .values(
                            workspace_fingerprint=live,
                            last_verified_fingerprint=live,
                            last_verified_at=self._now(),
                        )
                    )
                    if changed.rowcount != 1:
                        raise StageRecoveryError(
                            "WORKSPACE_BINDING_STALE",
                            "Workspace binding changed before repair replay commit",
                        )
                for artifact in replay_artifacts:
                    self._stage.register_artifact(session, artifact, continuation)
                replay_event_key = f"stage-recovery:{operation.id}:repair-replay"
                replay_event = session.scalar(
                    select(WorkflowEventModel).where(
                        WorkflowEventModel.run_id == operation.run_id,
                        WorkflowEventModel.idempotency_key
                        == f"{continuation.id}:{replay_event_key}",
                    )
                )
                if replay_event is None:
                    append_continuation_event(
                        session,
                        continuation,
                        event_type=WorkflowEventType.STAGE_RECOVERY_REPAIR_REPLAYED,
                        key=replay_event_key,
                        reason="replayed the immutable approved repair postimage during stage recovery",
                        payload={
                            "recovery_id": operation.id,
                            "attempt_id": replay_context["attempt_id"],
                            "proposal_checksum": replay_context["proposal_checksum"],
                            "source_fingerprint": replay_context["pre_fingerprint"],
                            "restored_fingerprint": replay_context["post_fingerprint"],
                            "prepared_artifact_id": (
                                replay_artifacts[0].ref.artifact_id
                                if replay_artifacts
                                else None
                            ),
                            "ledger_artifact_id": (
                                replay_artifacts[1].ref.artifact_id
                                if replay_artifacts
                                else None
                            ),
                        },
                    )
            stage = session.get(MigrationStageModel, operation.stage_id)
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

    def _approved_repair_replay_context(
        self, session, operation, continuation, binding
    ) -> dict[str, object] | None:
        attempt = session.get(RepairAttemptModel, operation.repair_attempt_id)
        if attempt is None or attempt.checkpoint_id != operation.checkpoint_id:
            raise StageRecoveryError(
                "REPAIR_RECOVERY_REPLAY_INVALID",
                "Recovery repair attempt is not bound to its checkpoint",
            )
        if not all(
            (
                attempt.proposal_artifact_id,
                attempt.proposal_checksum,
                attempt.apply_ledger_artifact_id,
                attempt.apply_ledger_checksum,
                attempt.post_fingerprint,
            )
        ):
            raise StageRecoveryError(
                "REPAIR_RECOVERY_REPLAY_INVALID",
                "Approved repair replay evidence is incomplete",
            )
        gate = session.get(StageGatePackageModel, attempt.g10_gate_package_id)
        decision = session.scalar(
            select(StageGateDecisionModel).where(
                StageGateDecisionModel.gate_package_id == attempt.g10_gate_package_id,
                StageGateDecisionModel.accepted.is_(True),
                StageGateDecisionModel.decision == "approve",
                StageGateDecisionModel.package_checksum == gate.package_checksum
                if gate is not None
                else False,
            )
        )
        if (
            gate is None
            or gate.gate_id != "G10"
            or gate.status != "approved"
            or gate.stale_at is not None
            or decision is None
        ):
            raise StageRecoveryError(
                "REPAIR_RECOVERY_REPLAY_INVALID",
                "Approved G10 repair authority is missing or stale",
            )
        checkpoint = session.get(StageCheckpointModel, operation.checkpoint_id)
        pre_fingerprint = self._checkpoint_authority(session, checkpoint, binding)
        if pre_fingerprint is None or attempt.pre_fingerprint != pre_fingerprint:
            raise StageRecoveryError(
                "REPAIR_RECOVERY_REPLAY_INVALID",
                "Repair preimage is not bound to the authoritative checkpoint",
            )
        run = session.get(MigrationRunModel, operation.run_id)
        proposal = self._read_json_artifact(
            session,
            run,
            operation.stage_id,
            attempt.proposal_artifact_id,
            attempt.proposal_checksum,
        )
        ledger = self._read_json_artifact(
            session,
            run,
            operation.stage_id,
            attempt.apply_ledger_artifact_id,
            attempt.apply_ledger_checksum,
        )
        if (
            ledger.get("schema_version") != "repair-apply-ledger-v1"
            or ledger.get("attempt_id") != attempt.id
            or ledger.get("status") not in {"applied", "ledger_only"}
            or ledger.get("pre_fingerprint") != pre_fingerprint
            or ledger.get("post_fingerprint") != attempt.post_fingerprint
        ):
            raise StageRecoveryError(
                "REPAIR_RECOVERY_REPLAY_INVALID",
                "Immutable repair ledger is not bound to the recovery checkpoint",
            )
        package_operation = next(
            (
                item
                for item in ledger.get("operations", [])
                if isinstance(item, dict) and item.get("path") == "package.json"
            ),
            None,
        )
        package_postimage = (
            package_operation.get("postimage_sha256")
            if isinstance(package_operation, dict)
            else None
        )
        if not isinstance(package_postimage, str):
            raise StageRecoveryError(
                "REPAIR_RECOVERY_REPLAY_INVALID",
                "Approved repair ledger has no package.json postimage",
            )
        workspace = Path(binding.workspace_path)
        live = STAGE_FINGERPRINT_PROFILE.fingerprint(workspace)
        package_checksum = self.file_checksum(workspace / "package.json")
        if live == attempt.post_fingerprint:
            if package_checksum != package_postimage:
                raise StageRecoveryError(
                    "REPAIR_RECOVERY_REPLAY_INVALID",
                    "Workspace fingerprint claims the repair postimage but package.json differs",
                )
            return {
                "needs_apply": False,
                "run_id": operation.run_id,
                "stage_id": operation.stage_id,
                "attempt_id": attempt.id,
                "proposal": proposal,
                "proposal_checksum": attempt.proposal_checksum,
                "pre_fingerprint": pre_fingerprint,
                "post_fingerprint": attempt.post_fingerprint,
                "workspace_path": str(workspace),
                "artifact_root": run.artifact_root,
            }
        if live != pre_fingerprint:
            raise StageRecoveryError(
                "REPAIR_RECOVERY_REPLAY_INVALID",
                "Workspace is neither the approved repair preimage nor postimage",
            )
        proposal_operation = next(
            (
                item
                for item in proposal.get("operations", [])
                if isinstance(item, dict) and item.get("path") == "package.json"
            ),
            None,
        )
        if not isinstance(proposal_operation, dict) or proposal_operation.get(
            "preimage_sha256"
        ) != package_checksum:
            raise StageRecoveryError(
                "REPAIR_RECOVERY_REPLAY_INVALID",
                "Workspace package.json is not the approved repair preimage",
            )
        return {
            "needs_apply": True,
            "run_id": operation.run_id,
            "stage_id": operation.stage_id,
            "attempt_id": attempt.id,
            "proposal": proposal,
            "proposal_checksum": attempt.proposal_checksum,
            "pre_fingerprint": pre_fingerprint,
            "post_fingerprint": attempt.post_fingerprint,
            "workspace_path": str(workspace),
            "artifact_root": run.artifact_root,
        }

    @staticmethod
    def _read_json_artifact(session, run, stage_id, artifact_id, checksum):
        metadata = session.get(ArtifactMetadataModel, "metadata-" + str(artifact_id))
        if (
            metadata is None
            or metadata.run_id != run.id
            or metadata.stage_id != stage_id
            or not metadata.immutable
            or metadata.checksum != checksum
        ):
            raise StageRecoveryError(
                "REPAIR_RECOVERY_REPLAY_INVALID",
                "Immutable repair artifact metadata is missing or stale",
            )
        try:
            stored = LocalFilesystemArtifactStore(
                Path(run.artifact_root).parent,
                fixed_run_root=Path(run.artifact_root),
            ).read_artifact(run.id, metadata.relative_path)
            if stored.ref.artifact_id != artifact_id or stored.ref.checksum != checksum:
                raise StageRecoveryError(
                    "REPAIR_RECOVERY_REPLAY_INVALID",
                    "Immutable repair artifact identity changed",
                )
            payload = json.loads(stored.content)
        except (ArtifactNotFoundError, ArtifactStoreError, OSError, ValueError) as error:
            if isinstance(error, StageRecoveryError):
                raise
            raise StageRecoveryError(
                "REPAIR_RECOVERY_REPLAY_INVALID",
                "Immutable repair artifact cannot be verified",
            ) from error
        if not isinstance(payload, dict):
            raise StageRecoveryError(
                "REPAIR_RECOVERY_REPLAY_INVALID",
                "Immutable repair artifact is not a JSON object",
            )
        return payload

    def _advance_preparation(self, operation_id: str) -> None:
        with self._scope() as session:
            operation = session.get(StageRecoveryOperationModel, operation_id)
            if operation is None or operation.status != "PREPARING":
                return
            continuation = self._continuation_for_operation(session, operation)
            step = session.scalar(
                select(StageStepModel).where(
                    StageStepModel.run_id == operation.run_id,
                    StageStepModel.stage_id == operation.stage_id,
                    StageStepModel.name == "lockfile_generation-0",
                )
            )
            if continuation is None or step is None:
                raise StageRecoveryError("RECOVERY_AUTHORITY_MISSING", "Recovery lockfile command authority is incomplete")
            context = self._resolve_context(session, continuation)
            causal = context["causal"]
            operation.causal_execution_id = causal.id
            operation.causal_evidence_checksum = context["causal_evidence_checksum"]
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
            continuation = self._continuation_for_operation(session, operation)
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
            continuation = self._continuation_for_operation(session, operation)
            operation.status = "FAILED"
            operation.last_error_code = code
            operation.last_error_message = message[:4000]
            operation.updated_at = self._now()
            if continuation is not None:
                expected_state_version = continuation.state_version
                execution = (
                    session.get(CommandExecutionModel, operation.command_execution_id)
                    if operation.command_execution_id
                    else None
                )
                normal_failure_handoff = bool(
                    execution is not None
                    and execution.command_id == "npm-lockfile-generate"
                    and execution.status == "failed"
                    and is_npm_eresolve_failure(execution)
                )
                continuation.status = "queued" if normal_failure_handoff else "blocked"
                continuation.current_node = (
                    "classify_failure" if normal_failure_handoff else "lockfile_generation"
                )
                continuation.worker_id = None
                continuation.lease_expires_at = None
                continuation.waiting_execution_id = None
                continuation.last_error_code = code
                continuation.last_error_message = message[:2000]
                continuation.state_version += 1
                continuation.updated_at = self._now()
                failure_event_type = (
                    WorkflowEventType.TRANSFORMATION_CONTINUATION_FAILED
                    if normal_failure_handoff
                    else WorkflowEventType.TRANSFORMATION_CONTINUATION_BLOCKED
                )
                failure_event_key = f"stage-recovery:{operation.id}:failed:{code}"
                existing_failure = session.scalar(
                    select(WorkflowEventModel).where(
                        WorkflowEventModel.run_id == operation.run_id,
                        WorkflowEventModel.idempotency_key
                        == f"{continuation.id}:{failure_event_key}",
                    )
                )
                if existing_failure is not None:
                    stable_payload = existing_failure.payload or {}
                    if (
                        existing_failure.event_type != failure_event_type
                        or stable_payload.get("recovery_id") != operation.id
                        or stable_payload.get("last_error_code") != code
                    ):
                        raise StageRecoveryError(
                            "RECOVERY_FAILURE_EVENT_IDENTITY_MISMATCH",
                            "Recovery failure event is bound to different durable evidence",
                        )
                else:
                    append_continuation_event(
                        session,
                        continuation,
                        event_type=failure_event_type,
                        key=failure_event_key,
                        reason=(
                            "Fresh npm ERESOLVE handed to normal failure classification"
                            if normal_failure_handoff
                            else message[:500]
                        ),
                        payload={
                            "recovery_id": operation.id,
                            "last_error_code": code,
                            "expected_state_version": expected_state_version,
                            "normal_failure_handoff": normal_failure_handoff,
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
    def _continuation_for_operation(session, operation):
        continuation_id = getattr(operation, "continuation_id", None)
        continuation = (
            session.get(TransformationContinuationModel, continuation_id)
            if continuation_id
            else None
        )
        if (
            continuation is None
            or continuation.run_id != operation.run_id
            or continuation.current_stage_id != operation.stage_id
        ):
            raise StageRecoveryError(
                "RECOVERY_CONTINUATION_AUTHORITY_INVALID",
                "Recovery operation is not bound to the authoritative stage continuation",
            )
        return continuation

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
                "continuation_id": operation.continuation_id,
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
            "continuation_id": operation.continuation_id,
            "kind": operation.kind,
            "status": operation.status,
            "state_version": continuation.state_version,
            "causal_execution_id": operation.causal_execution_id,
            "interrupted_execution_id": operation.interrupted_execution_id,
            "checkpoint_id": operation.checkpoint_id,
            "repair_attempt_id": operation.repair_attempt_id,
            "command_execution_id": operation.command_execution_id,
            "observed_workspace_fingerprint": operation.observed_workspace_fingerprint,
            "governed_workspace_fingerprint": operation.governed_workspace_fingerprint,
            "drift_classification": operation.drift_classification,
            "interrupted_evidence_checksum": operation.interrupted_evidence_checksum,
            "required_action": "RECOVER_STAGE",
            "idempotent_replay": replay,
        }
