"""Durable Transformer continuation lifecycle."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType, WorkflowEventType
from app.domain.transformation import TransformationNode, TransformationStatus
from app.repositories.models import (
    ArtifactMetadataModel,
    CommandExecutionModel,
    G06ApprovalModel,
    MigrationPlanModel,
    MigrationStageModel,
    MigrationRunModel,
    RepairAttemptModel,
    StageCheckpointModel,
    StageExecutionPlanModel,
    StageGatePackageModel,
    StageWorkspaceBindingModel,
    WorkspaceGenerationModel,
    TransformationContinuationModel,
    WorkflowEventModel,
)
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.state import StateTransitionService


class TransformationContinuationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def append_continuation_event(
    session: Session,
    continuation: TransformationContinuationModel,
    *,
    event_type: WorkflowEventType,
    key: str,
    reason: str,
    payload: dict[str, str | int | None] | None = None,
    occurred_at: datetime | None = None,
    actor: str = "transformer",
) -> None:
    """Append a durable continuation lifecycle event atomically in the caller's transaction.

    The event shares the continuation's transaction, so the status change and
    the event commit together; replaying the same deterministic key appends
    nothing a second time.
    """
    StateTransitionService(session).append_audit_event(
        run_id=continuation.run_id,
        idempotency_key=f"{continuation.id}:{key}",
        event_type=event_type,
        actor=actor,
        reason=reason,
        occurred_at=occurred_at or continuation.updated_at,
        payload=payload or {},
    )


class TransformationContinuationService:
    def __init__(self, *, lease_seconds: int = 120) -> None:
        self.lease_seconds = lease_seconds

    def ensure_created_in_session(
        self,
        session: Session,
        *,
        run_id: str,
        stage_id: str,
        g06_approval_id: str,
        plan_id: str,
        plan_checksum: str,
        stage_plan_id: str,
        stage_plan_checksum: str,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> TransformationContinuationModel:
        created_at = now or datetime.now(UTC)
        request_checksum = self._checksum(
            {
                "run_id": run_id,
                "stage_id": stage_id,
                "g06_approval_id": g06_approval_id,
                "plan_id": plan_id,
                "plan_checksum": plan_checksum,
                "stage_plan_id": stage_plan_id,
                "stage_plan_checksum": stage_plan_checksum,
                "idempotency_key": idempotency_key,
            }
        )
        existing = session.scalar(
            select(TransformationContinuationModel).where(
                TransformationContinuationModel.run_id == run_id
            )
        )
        if existing is not None:
            if existing.request_checksum != request_checksum:
                raise TransformationContinuationError(
                    "IDEMPOTENCY_PAYLOAD_MISMATCH",
                    "Transformation continuation already exists with a different payload",
                )
            return existing
        g06 = session.get(G06ApprovalModel, g06_approval_id)
        plan = session.get(MigrationPlanModel, plan_id)
        stage_plan = session.get(StageExecutionPlanModel, stage_plan_id)
        stage = session.get(MigrationStageModel, stage_id)
        if (
            g06 is None
            or g06.run_id != run_id
            or g06.status not in {"approved", "approved_with_comment"}
            or g06.plan_checksum != plan_checksum
            or g06.stage_plan_checksum != stage_plan_checksum
        ):
            raise TransformationContinuationError("G06_BINDING_STALE", "Approved G06 binding is missing or stale")
        if plan is None or plan.run_id != run_id or plan.checksum != plan_checksum:
            raise TransformationContinuationError("G06_BINDING_STALE", "Migration plan binding is stale")
        if (
            stage_plan is None
            or stage_plan.run_id != run_id
            or stage_plan.stage_id != stage_id
            or stage_plan.migration_plan_id != plan_id
            or stage_plan.checksum != stage_plan_checksum
        ):
            raise TransformationContinuationError("STAGE_PLAN_STALE", "Stage plan binding is stale")
        if stage is None:
            planned = stage_plan.stage_plan or {}
            stage = MigrationStageModel(
                id=stage_id,
                run_id=run_id,
                stage_order=session.query(MigrationStageModel).filter_by(run_id=run_id).count() + 1,
                source_version_family=planned.get("source_family"),
                target_version_family=planned.get("target_family"),
                source_version_detected=planned.get("source_exact"),
                target_version_resolved=planned.get("target_exact"),
                source_angular_version=planned.get("source_exact"),
                target_angular_version=planned.get("target_exact"),
                status="planned",
                created_at=created_at,
            )
            session.add(stage)
            session.flush()
        if stage.run_id != run_id:
            raise TransformationContinuationError("STAGE_PLAN_STALE", "Stage does not belong to the run")
        model = TransformationContinuationModel(
            id=f"transform-{uuid4().hex[:12]}",
            run_id=run_id,
            current_stage_id=stage_id,
            thread_id=f"transform:{run_id}",
            status=TransformationStatus.QUEUED.value,
            current_node=TransformationNode.VALIDATE_G06.value,
            g06_approval_id=g06_approval_id,
            plan_id=plan_id,
            plan_checksum=plan_checksum,
            stage_plan_id=stage_plan_id,
            stage_plan_checksum=stage_plan_checksum,
            attempt=0,
            max_attempts=3,
            claim_count=0,
            wake_sequence=0,
            idempotency_key=idempotency_key,
            request_checksum=request_checksum,
            state_version=1,
            created_at=created_at,
            updated_at=created_at,
        )
        session.add(model)
        session.flush()
        StateTransitionService(session).append_audit_event(
            run_id=run_id,
            idempotency_key=f"{idempotency_key}:continuation",
            event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_CREATED,
            actor="transformer",
            reason="durable Transformer continuation created",
            occurred_at=created_at,
            payload={"continuation_id": model.id, "stage_id": stage_id},
        )
        return model

    def claim_next(
        self,
        session: Session,
        worker_id: str,
        now: datetime | None = None,
    ) -> TransformationContinuationModel | None:
        claimed_at = now or datetime.now(UTC)
        candidate = session.scalar(
            select(TransformationContinuationModel)
            .where(
                or_(
                    TransformationContinuationModel.status == TransformationStatus.QUEUED.value,
                    TransformationContinuationModel.status == TransformationStatus.CANCELLING.value,
                    TransformationContinuationModel.status == TransformationStatus.WAITING_RETRY.value,
                    (
                        (TransformationContinuationModel.status == TransformationStatus.RUNNING.value)
                        & (TransformationContinuationModel.lease_expires_at <= claimed_at)
                    ),
                )
            )
            .where(
                or_(
                    TransformationContinuationModel.next_attempt_at.is_(None),
                    TransformationContinuationModel.next_attempt_at <= claimed_at,
                )
            )
            .order_by(TransformationContinuationModel.created_at)
            .limit(1)
        )
        if candidate is None:
            return None
        prior_claim_count = candidate.claim_count or 0
        claimed = session.execute(
            update(TransformationContinuationModel)
            .where(TransformationContinuationModel.id == candidate.id)
            .where(TransformationContinuationModel.state_version == candidate.state_version)
            .values(
                status=TransformationStatus.RUNNING.value,
                worker_id=worker_id,
                claim_count=prior_claim_count + 1,
                lease_expires_at=claimed_at + timedelta(seconds=self.lease_seconds),
                state_version=candidate.state_version + 1,
                started_at=candidate.started_at or claimed_at,
                updated_at=claimed_at,
            )
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:
            session.expire_all()
            return None
        session.refresh(candidate)
        append_continuation_event(
            session,
            candidate,
            event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_CLAIMED,
            key=f"claim:{candidate.claim_count}",
            reason="durable Transformer continuation claimed by worker",
            payload={
                "worker_id": candidate.worker_id or "",
                "expected_state_version": candidate.state_version - 1,
            },
            occurred_at=claimed_at,
        )
        return candidate

    def _recovery_policy_context(self, session, continuation):
        """Load immutable failure and safety facts for the pure recovery policy."""
        from app.services.failure_evidence_service import FailureEvidenceService
        from app.services.stage_recovery_policy_service import (
            RecoveryFailureClass,
            StageRecoveryPolicyContext,
        )
        from app.services.stage_plan_authority_service import StagePlanAuthorityService

        binding = session.scalar(
            select(StageWorkspaceBindingModel)
            .where(
                StageWorkspaceBindingModel.run_id == continuation.run_id,
                StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                StageWorkspaceBindingModel.active.is_(True),
            )
            .order_by(
                StageWorkspaceBindingModel.created_at.desc(),
                StageWorkspaceBindingModel.id.desc(),
            )
            .limit(1)
        )
        run = session.get(MigrationRunModel, continuation.run_id)
        plan = session.get(MigrationPlanModel, continuation.plan_id)
        stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
        active_command = session.scalar(
            select(CommandExecutionModel.id).where(
                CommandExecutionModel.run_id == continuation.run_id,
                CommandExecutionModel.stage_id == continuation.current_stage_id,
                CommandExecutionModel.plan_id == continuation.plan_id,
                CommandExecutionModel.status.in_(("queued", "pending", "running")),
            )
        )
        commands_executed = session.scalar(
            select(CommandExecutionModel.id)
            .where(
                CommandExecutionModel.run_id == continuation.run_id,
                CommandExecutionModel.stage_id == continuation.current_stage_id,
                CommandExecutionModel.plan_id == continuation.plan_id,
            )
            .limit(1)
        ) is not None
        command = session.get(CommandExecutionModel, continuation.waiting_execution_id) if continuation.waiting_execution_id else None
        if command is not None and command.plan_id != continuation.plan_id:
            command = None
        if command is None:
            command = session.scalar(
                select(CommandExecutionModel)
                .where(
                    CommandExecutionModel.run_id == continuation.run_id,
                    CommandExecutionModel.stage_id == continuation.current_stage_id,
                    CommandExecutionModel.plan_id == continuation.plan_id,
                    CommandExecutionModel.status.in_(("failed", "cancelled", "interrupted")),
                )
                .order_by(
                    CommandExecutionModel.finished_at.desc(),
                    CommandExecutionModel.id.desc(),
                )
                .limit(1)
            )
        pending_gate = session.scalar(
            select(StageGatePackageModel)
            .where(
                StageGatePackageModel.run_id == continuation.run_id,
                StageGatePackageModel.stage_id == continuation.current_stage_id,
                StageGatePackageModel.status == "pending",
            )
            .order_by(
                StageGatePackageModel.gate_version.desc(),
                StageGatePackageModel.id.desc(),
            )
            .limit(1)
        )
        approved_gate = session.scalar(
            select(StageGatePackageModel)
            .where(
                StageGatePackageModel.run_id == continuation.run_id,
                StageGatePackageModel.stage_id == continuation.current_stage_id,
                StageGatePackageModel.status == "approved",
            )
            .order_by(StageGatePackageModel.gate_version.desc(), StageGatePackageModel.id.desc())
            .limit(1)
        )
        checkpoint = session.scalar(
            select(StageCheckpointModel)
            .where(
                StageCheckpointModel.run_id == continuation.run_id,
                StageCheckpointModel.stage_id == continuation.current_stage_id,
                StageCheckpointModel.safe_for_resume.is_(True),
            )
            .order_by(StageCheckpointModel.sequence.desc(), StageCheckpointModel.id.desc())
            .limit(1)
        )
        if checkpoint is None:
            checkpoint = session.scalar(
                select(StageCheckpointModel)
                .where(
                    StageCheckpointModel.run_id == continuation.run_id,
                    StageCheckpointModel.safe_for_resume.is_(True),
                    StageCheckpointModel.sealed.is_(True),
                )
                .order_by(StageCheckpointModel.created_at.desc(), StageCheckpointModel.id.desc())
                .limit(1)
            )
        workspace_authority_valid = bool(
            binding is not None
            and plan is not None
            and stage_plan is not None
            and run is not None
            and plan.run_id == continuation.run_id
            and stage_plan.run_id == continuation.run_id
            and stage_plan.stage_id == continuation.current_stage_id
            and plan.checksum == continuation.plan_checksum
            and stage_plan.checksum == continuation.stage_plan_checksum
            and Path(binding.workspace_path).is_dir()
        )
        workspace_binding_stale = bool(
            binding is not None
            and (
                not binding.workspace_generation_id
                or session.get(WorkspaceGenerationModel, binding.workspace_generation_id) is None
            )
        )
        aliases = dict(run.workspace_aliases or {}) if run is not None else {}
        safe_predecessor_present = bool(
            aliases.get("BASELINE_SANDBOX")
            and aliases.get("STAGE_SANDBOX")
            and Path(str(aliases["BASELINE_SANDBOX"])).is_dir()
        )
        gate_binding_stale = False
        if pending_gate is not None and binding is not None and Path(binding.workspace_path).is_dir():
            try:
                gate_binding_stale = pending_gate.workspace_fingerprint != StageSandboxCopier.fingerprint(Path(binding.workspace_path))
            except (OSError, ValueError):
                gate_binding_stale = True
        plan_authority_stale = False
        if plan is not None and stage_plan is not None:
            try:
                plan_authority_stale = StagePlanAuthorityService().compare(
                    stage_plan.stage_plan or {}, plan.plan or {}
                ).stale
            except (TypeError, ValueError):
                # An unresolvable authority is not evidence for an automatic
                # refresh; the normal unknown-failure path remains fail-closed.
                plan_authority_stale = False
        planned_aliases = {
            reference.get("working_directory_alias")
            for references in ((stage_plan.stage_plan or {}).get("commands") or {}).values()
            for reference in (references if isinstance(references, list) else (references,))
            if isinstance(reference, dict) and reference.get("working_directory_alias")
        }
        command_authority_mismatch = bool(
            binding is not None
            and stage_plan is not None
            and (
                (stage_plan.stage_plan or {}).get("stage_id") != continuation.current_stage_id
                or planned_aliases != {binding.alias}
            )
        )
        projection_authority_stale = bool(
            continuation.last_error_code == "PROVEN_PRIOR_STEP_NOT_VERIFIED"
            and commands_executed
        )
        # The continuation error may be a controller-level route such as a
        # retry-budget boundary.  The terminal command is the authoritative
        # failure evidence used for recovery classification.
        failure_code = (command.failure_code if command else None) or continuation.last_error_code
        failure_message = (
            FailureEvidenceService._execution_output(session, run, command)
            if command is not None and run is not None
            else None
        ) or (command.failure_message if command else None) or continuation.last_error_message
        gate_package = pending_gate or approved_gate
        if pending_gate is not None and gate_binding_stale:
            failure_class = RecoveryFailureClass.STALE_GATE_BINDING
        elif failure_code == "STAGE_RUNTIME_G07_BINDING_INVALID":
            failure_class = RecoveryFailureClass.STALE_GATE_BINDING
            gate_binding_stale = approved_gate is not None and not commands_executed
        elif plan_authority_stale:
            failure_class = RecoveryFailureClass.STAGE_PLAN_AUTHORITY_STALE
        elif command_authority_mismatch:
            failure_class = RecoveryFailureClass.COMMAND_AUTHORITY_MISMATCH
        elif projection_authority_stale:
            failure_class = RecoveryFailureClass.PROJECTION_AUTHORITY_STALE
        elif workspace_binding_stale:
            failure_class = RecoveryFailureClass.STALE_WORKSPACE_BINDING
        elif failure_code == "PROVEN_TARGET_COHORT_INCOMPLETE":
            failure_class = RecoveryFailureClass.TARGET_COHORT_INCOMPLETE
        elif failure_code in {"PROVEN_LOCK_RESOLUTION_FAILED", "LOCKFILE_GENERATION_ERESOLVE"}:
            failure_class = RecoveryFailureClass.LOCK_RESOLUTION_FAILED
        elif (
            command is not None
            and (
                command.status == "interrupted"
                or command.reconstruction_required
            )
        ) or continuation.status == TransformationStatus.CANCELLED.value:
            failure_class = RecoveryFailureClass.COMMAND_INTERRUPTED
        else:
            failure_class = RecoveryFailureClass.UNKNOWN_FAILURE
        output_nodes = {
            "target_tree",
            "target_version_proof",
            "execute_migration_owner",
            "validation_build",
            "validation_test",
        }
        stage_output_invalid = continuation.current_node in output_nodes
        # A governed stage re-execution always reconstructs the workspace from
        # the verified predecessor before replacing stale authority.  The
        # failed command itself may be read-only, so derive this safety fact
        # from the stage boundary rather than from that command's operation
        # kind alone.
        reconstruction_required = bool(
            safe_predecessor_present
            and (commands_executed or stage_output_invalid)
        )
        return StageRecoveryPolicyContext(
            run_id=continuation.run_id,
            stage_id=continuation.current_stage_id,
            stage_status=continuation.status,
            failure_code=failure_code,
            failure_message=failure_message,
            failure_class=failure_class,
            evidence_refs=tuple(
                ref
                for ref in (
                    command.id if command else None,
                    gate_package.id if gate_package else None,
                    checkpoint.id if checkpoint else None,
                )
                if ref
            ),
            checkpoint_present=checkpoint is not None,
            checkpoint_safe=bool(checkpoint and checkpoint.safe_for_resume and safe_predecessor_present),
            workspace_authority_valid=workspace_authority_valid,
            active_command=active_command is not None,
            active_gate=(pending_gate.gate_id if pending_gate else "G07" if gate_binding_stale else None),
            gate_binding_stale=gate_binding_stale,
            stage_output_invalid=stage_output_invalid,
            introduced_by_migration=continuation.current_node in output_nodes,
            command_id=command.command_id if command else None,
            plan_authority_stale=plan_authority_stale,
            commands_executed=commands_executed,
            command_authority_mismatch=command_authority_mismatch,
            projection_authority_stale=projection_authority_stale,
            reconstruction_required=reconstruction_required,
            retry_budget_exhausted=continuation.attempt >= continuation.max_attempts,
        )

    def reexecute_blocked_stage_from_g07(
        self,
        session: Session,
        continuation: TransformationContinuationModel,
        *,
        expected_state_version: int,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> object | None:
        """Orchestrate a policy decision and dispatch it to the recovery owner."""
        from app.services.stage_recovery_policy_service import RecoveryAction, StageRecoveryPolicyService
        from app.services.stage_recovery_service import StageRecoveryError, StageRecoveryService

        policy_context = self._recovery_policy_context(session, continuation)
        decision = StageRecoveryPolicyService().decide(policy_context)
        if not decision.allowed:
            raise TransformationContinuationError(
                decision.reason_code,
                "Recovery policy denied automatic stage transition",
            )
        recovery = StageRecoveryService()
        try:
            if decision.action is RecoveryAction.RECREATE_GATE:
                recovery.recreate_gate_in_session(
                    session,
                    continuation,
                    gate_id=str(policy_context.active_gate),
                    expected_state_version=expected_state_version,
                    idempotency_key=idempotency_key,
                )
                return None
            if decision.action not in {
                RecoveryAction.RECONSTRUCT_WORKSPACE,
                RecoveryAction.REEXECUTE_FROM_G07,
            }:
                raise StageRecoveryError(
                    "RECOVERY_ACTION_NOT_STAGE_REEXECUTION",
                    f"Recovery policy selected {decision.action.value}; use its governed flow",
                )
            return recovery.reexecute_from_g07_in_session(
                session,
                continuation,
                expected_state_version=expected_state_version,
                idempotency_key=idempotency_key,
                refresh_plan=policy_context.plan_authority_stale or policy_context.command_authority_mismatch,
                refresh_reason_code=policy_context.failure_class.value,
            )
        except StageRecoveryError as error:
            raise TransformationContinuationError(error.code, error.message) from error

    def record_unhandled_workflow_fault(
        self,
        session: Session,
        *,
        continuation_id: str,
        claimed_worker_id: str,
        claim_snapshot: dict[str, object],
        exception_type: str,
        sanitized_message: str,
        traceback_text: str,
    ) -> bool:
        """Persist an unexpected claimed-workflow failure in a fresh transaction.

        The worker owns the invocation only while the durable row is still the
        same running claim. A stale claim is intentionally a no-op.
        """
        continuation = session.get(TransformationContinuationModel, continuation_id)
        if continuation is None:
            return False
        fault_fingerprint = self._fault_fingerprint(
            continuation_id, continuation.state_version, continuation.current_node,
            exception_type, sanitized_message, traceback_text,
        )
        event_key = f"fault:{continuation.state_version}:{continuation.current_node}:{fault_fingerprint}"
        existing = session.scalar(
            select(WorkflowEventModel).where(
                WorkflowEventModel.run_id == continuation.run_id,
                WorkflowEventModel.idempotency_key == f"{continuation.id}:{event_key}",
            )
        )
        if existing is not None:
            return True
        if (
            continuation.status != TransformationStatus.RUNNING.value
            or continuation.worker_id != claimed_worker_id
        ):
            return False

        now = datetime.now(UTC)
        previous_state_version = continuation.state_version
        run = session.get(MigrationRunModel, continuation.run_id)
        binding = session.scalar(
            select(StageWorkspaceBindingModel)
            .where(
                StageWorkspaceBindingModel.run_id == continuation.run_id,
                StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                StageWorkspaceBindingModel.active.is_(True),
            )
            .order_by(
                StageWorkspaceBindingModel.created_at.desc(),
                StageWorkspaceBindingModel.id.desc(),
            )
        )
        persisted_fingerprint = binding.workspace_fingerprint if binding else None
        live_fingerprint = self._safe_workspace_fingerprint(binding.workspace_path if binding else None)
        reconstruction_required = live_fingerprint != persisted_fingerprint
        attempt = session.scalar(
            select(RepairAttemptModel)
            .where(
                RepairAttemptModel.run_id == continuation.run_id,
                RepairAttemptModel.stage_id == continuation.current_stage_id,
            )
            .order_by(RepairAttemptModel.created_at.desc(), RepairAttemptModel.id.desc())
        )
        checkpoint = session.scalar(
            select(StageCheckpointModel)
            .where(
                StageCheckpointModel.run_id == continuation.run_id,
                StageCheckpointModel.stage_id == continuation.current_stage_id,
                StageCheckpointModel.safe_for_resume.is_(True),
            )
            .order_by(StageCheckpointModel.sequence.desc(), StageCheckpointModel.id.desc())
        )
        waiting_execution_id = continuation.waiting_execution_id
        current_command = session.scalar(
            select(CommandExecutionModel)
            .where(
                CommandExecutionModel.run_id == continuation.run_id,
                CommandExecutionModel.stage_id == continuation.current_stage_id,
                CommandExecutionModel.status.in_(("queued", "pending", "running")),
            )
            .order_by(CommandExecutionModel.requested_at.desc(), CommandExecutionModel.id.desc())
        )

        claimed = session.execute(
            update(TransformationContinuationModel)
            .where(
                TransformationContinuationModel.id == continuation.id,
                TransformationContinuationModel.status == TransformationStatus.RUNNING.value,
                TransformationContinuationModel.worker_id == claimed_worker_id,
                TransformationContinuationModel.state_version == previous_state_version,
            )
            .values(
                status=TransformationStatus.BLOCKED.value,
                last_error_code="TRANSFORMER_WORKFLOW_UNHANDLED_ERROR",
                last_error_message=(
                    f"Unhandled Transformer workflow exception: {sanitized_message[:2000]}"
                ),
                worker_id=None,
                lease_expires_at=None,
                state_version=previous_state_version + 1,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:
            return False
        session.refresh(continuation)

        diagnostic = {
            "schema_version": 1,
            "run_id": continuation.run_id,
            "continuation_id": continuation.id,
            "stage_id": continuation.current_stage_id,
            "node": continuation.current_node,
            "state_version_before_fault": previous_state_version,
            "state_version_at_persistence": continuation.state_version,
            "worker_id": claimed_worker_id,
            "claim_count": claim_snapshot.get("claim_count"),
            "exception_type": exception_type,
            "sanitized_message": sanitized_message[:2000],
            "traceback": traceback_text[:100000],
            "attempt_id": attempt.id if attempt else None,
            "attempt_number": attempt.attempt_number if attempt else None,
            "waiting_execution_id": waiting_execution_id,
            "current_command_id": current_command.id if current_command else None,
            "workspace_binding_id": binding.id if binding else None,
            "persisted_workspace_fingerprint": persisted_fingerprint,
            "live_workspace_fingerprint": live_fingerprint,
            "workspace_reconstruction_required": reconstruction_required,
            "latest_checkpoint_id": checkpoint.id if checkpoint else None,
            "occurred_at": now.isoformat(),
        }
        if run is None or not run.artifact_root:
            raise TransformationContinuationError(
                "WORKFLOW_FAULT_ARTIFACT_ROOT_MISSING",
                "Cannot persist workflow fault without a run artifact root",
            )
        store = LocalFilesystemArtifactStore(
            Path(run.artifact_root).parent,
            fixed_run_root=Path(run.artifact_root),
        )
        stored = store.write_text_artifact(
            continuation.run_id,
            f"04_workflow_state/transformer_faults/{continuation.id}.{previous_state_version}.{fault_fingerprint}.json",
            json.dumps(diagnostic, sort_keys=True, indent=2),
            ArtifactType.JSON,
            stage_id=continuation.current_stage_id,
            created_by="transformer-worker-fault-boundary",
            created_at=now,
            input_hashes={"exception": fault_fingerprint},
            policy_version="transformer-workflow-fault-v1",
        )
        session.add(
            ArtifactMetadataModel(
                id=f"metadata-{stored.ref.artifact_id}",
                run_id=continuation.run_id,
                stage_id=continuation.current_stage_id,
                artifact_type=stored.ref.artifact_type.value,
                relative_path=stored.ref.relative_path,
                checksum=stored.ref.checksum,
                created_at=stored.ref.created_at,
                finalized_at=stored.ref.created_at,
                immutable=True,
                owner_reference=continuation.id,
                mime_type="application/json",
                size_bytes=len(stored.content.encode("utf-8")),
            )
        )
        append_continuation_event(
            session,
            continuation,
            event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_BLOCKED,
            key=event_key,
            reason="Unhandled Transformer workflow exception; immutable diagnostic persisted",
            payload={
                "error_code": "TRANSFORMER_WORKFLOW_UNHANDLED_ERROR",
                "exception_type": exception_type,
                "node": continuation.current_node,
                "previous_state_version": previous_state_version,
                "diagnostic_artifact_id": stored.ref.artifact_id,
                "diagnostic_checksum": stored.ref.checksum,
                "workspace_reconstruction_required": reconstruction_required,
            },
            occurred_at=now,
            actor="transformer-worker",
        )
        return True

    def wait(
        self,
        session: Session,
        continuation_id: str,
        worker_id: str,
        *,
        status: str,
        current_node: str,
        now: datetime | None = None,
    ) -> TransformationContinuationModel:
        if status not in {
            TransformationStatus.WAITING_COMMAND.value,
            TransformationStatus.WAITING_GATE.value,
            TransformationStatus.WAITING_PROMPT.value,
            TransformationStatus.WAITING_RETRY.value,
            TransformationStatus.WAITING_REPAIR_REVISION.value,
            TransformationStatus.BLOCKED.value,
        }:
            raise TransformationContinuationError("TRANSFORMATION_STATUS_INVALID", "Invalid continuation wait status")
        model = self._owned(session, continuation_id, worker_id)
        occurred_at = now or datetime.now(UTC)
        expected_state_version = model.state_version
        model.status = status
        model.current_node = TransformationNode(current_node).value
        model.worker_id = None
        model.lease_expires_at = None
        model.state_version += 1
        model.updated_at = occurred_at
        session.flush()
        append_continuation_event(
            session,
            model,
            event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_WAITING,
            key=f"wait:{status}:{expected_state_version}",
            reason=f"Transformer continuation waits on {status}",
            payload={"expected_state_version": expected_state_version},
            occurred_at=occurred_at,
        )
        return model

    def wake(
        self,
        session: Session,
        continuation_id: str,
        *,
        now: datetime | None = None,
    ) -> TransformationContinuationModel:
        model = self._get(session, continuation_id)
        if model.status in {
            TransformationStatus.CANCELLED.value,
            TransformationStatus.FAILED.value,
            TransformationStatus.COMPLETED.value,
        }:
            raise TransformationContinuationError(
                "TRANSFORMATION_ALREADY_TERMINAL",
                "Terminal continuation cannot be woken",
            )
        if model.status != TransformationStatus.QUEUED.value:
            model.status = TransformationStatus.QUEUED.value
            model.worker_id = None
            model.lease_expires_at = None
            model.wake_sequence += 1
            model.state_version += 1
            model.updated_at = now or datetime.now(UTC)
            session.flush()
        return model

    def request_cancel(
        self,
        session: Session,
        continuation_id: str,
        *,
        actor: str,
        idempotency_key: str,
        expected_state_version: int,
        now: datetime | None = None,
    ) -> TransformationContinuationModel:
        model = self._get(session, continuation_id)
        checksum = self._checksum(
            {"continuation_id": continuation_id, "actor": actor, "idempotency_key": idempotency_key}
        )
        if model.cancel_idempotency_key is not None:
            if (
                model.cancel_idempotency_key != idempotency_key
                or model.cancel_request_checksum != checksum
            ):
                raise TransformationContinuationError(
                    "IDEMPOTENCY_PAYLOAD_MISMATCH",
                    "Cancellation key was already used with a different payload",
                )
            return model
        if model.state_version != expected_state_version:
            raise TransformationContinuationError(
                "TRANSFORMATION_STATE_CONFLICT",
                "Transformation state changed; refresh authoritative state",
            )
        if model.status in {
            TransformationStatus.CANCELLED.value,
            TransformationStatus.FAILED.value,
            TransformationStatus.COMPLETED.value,
        }:
            raise TransformationContinuationError(
                "TRANSFORMATION_ALREADY_TERMINAL",
                "Terminal continuation cannot be cancelled",
            )
        requested_at = now or datetime.now(UTC)
        expected_state_version = model.state_version
        model.cancel_requested_at = requested_at
        model.cancel_requested_by = actor
        model.cancel_idempotency_key = idempotency_key
        model.cancel_request_checksum = checksum
        model.status = TransformationStatus.CANCELLING.value
        model.current_node = TransformationNode.CANCEL.value
        model.worker_id = None
        model.lease_expires_at = None
        model.state_version += 1
        model.updated_at = requested_at
        session.flush()
        append_continuation_event(
            session,
            model,
            event_type=WorkflowEventType.TRANSFORMATION_CANCEL_REQUESTED,
            key=f"cancel:{idempotency_key}",
            reason="Transformer cancellation requested",
            payload={
                "actor": actor,
                "expected_state_version": expected_state_version,
            },
            occurred_at=requested_at,
        )
        return model

    def complete(
        self,
        session: Session,
        continuation_id: str,
        worker_id: str,
        *,
        now: datetime | None = None,
    ) -> TransformationContinuationModel:
        model = self._owned(session, continuation_id, worker_id)
        completed_at = now or datetime.now(UTC)
        expected_state_version = model.state_version
        model.status = TransformationStatus.COMPLETED.value
        model.current_node = TransformationNode.TERMINAL.value
        model.worker_id = None
        model.lease_expires_at = None
        model.completed_at = completed_at
        model.updated_at = completed_at
        model.state_version += 1
        session.flush()
        append_continuation_event(
            session,
            model,
            event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_COMPLETED,
            key="complete",
            reason="durable Transformer continuation completed",
            payload={"expected_state_version": expected_state_version},
            occurred_at=completed_at,
        )
        return model

    @staticmethod
    def _checksum(value: dict[str, object]) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _fault_fingerprint(
        continuation_id: str,
        state_version: int,
        node: str,
        exception_type: str,
        message: str,
        traceback_text: str,
    ) -> str:
        payload = "\n".join(
            (continuation_id, str(state_version), node, exception_type, message, traceback_text)
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:32]

    @staticmethod
    def _safe_workspace_fingerprint(path: str | None) -> str | None:
        if not path:
            return None
        try:
            return StageSandboxCopier.fingerprint(Path(path))
        except (OSError, ValueError):
            return None

    @staticmethod
    def _get(session: Session, continuation_id: str) -> TransformationContinuationModel:
        model = session.get(TransformationContinuationModel, continuation_id)
        if model is None:
            raise TransformationContinuationError("TRANSFORMATION_NOT_FOUND", "Continuation does not exist")
        return model

    def _owned(
        self,
        session: Session,
        continuation_id: str,
        worker_id: str,
    ) -> TransformationContinuationModel:
        model = self._get(session, continuation_id)
        if model.status != TransformationStatus.RUNNING.value or model.worker_id != worker_id:
            raise TransformationContinuationError("TRANSFORMATION_CLAIM_STALE", "Worker no longer owns continuation")
        return model
