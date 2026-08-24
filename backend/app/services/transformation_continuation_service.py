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
    ActivePlanVersionModel,
    ArtifactMetadataModel,
    BuildSystemDecisionModel,
    CommandExecutionModel,
    G06ApprovalModel,
    MigrationPlanModel,
    MigrationStageModel,
    MigrationRunModel,
    RepairAttemptModel,
    StageCheckpointModel,
    StageExecutionPlanModel,
    StageStepModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
    WorkflowEventModel,
)
from app.domain.planning import BuildSystemDecision, MigrationPlan, StageExecutionPlan, checksum_model
from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider
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

    def reexecute_blocked_stage_from_g07(
        self,
        session: Session,
        continuation: TransformationContinuationModel,
        *,
        expected_state_version: int,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> StageExecutionPlan:
        """Rebuild only a blocked stage's derived cohort through the Factory boundary."""
        if continuation.state_version != expected_state_version:
            raise TransformationContinuationError("TRANSFORMATION_STATE_CONFLICT", "Transformer state changed; refresh authoritative state")
        if continuation.status != TransformationStatus.BLOCKED.value:
            raise TransformationContinuationError("STAGE_REEXECUTION_NOT_ALLOWED", "Only a blocked stage may be re-executed")
        approved_authority_failure = (
            continuation.current_node == "prove_discovery_cli_authority"
            and continuation.last_error_code in {"TRANSFORMER_WORKFLOW_UNHANDLED_ERROR", "FIRST_COMMAND_NOT_AUTHORIZED"}
        )
        approved_discovery_failure = (
            continuation.current_node == "assess_discovery"
            and continuation.last_error_code == "COMMAND_EXIT_NONZERO"
            and "single package must be specified" in (continuation.last_error_message or "").lower()
        )
        run_for_failure = session.get(MigrationRunModel, continuation.run_id)
        latest_test_failure = session.scalar(
            select(CommandExecutionModel)
            .where(
                CommandExecutionModel.run_id == continuation.run_id,
                CommandExecutionModel.stage_id == continuation.current_stage_id,
                CommandExecutionModel.command_id == "npm-script-test-ci",
                CommandExecutionModel.status == "failed",
            )
            .order_by(CommandExecutionModel.requested_at.desc())
        )
        test_failure_output = latest_test_failure.failure_message if latest_test_failure is not None else ""
        if latest_test_failure is not None and latest_test_failure.stdout_artifact_id and run_for_failure is not None:
            try:
                store = LocalFilesystemArtifactStore(
                    Path(run_for_failure.artifact_root),
                    fixed_run_root=Path(run_for_failure.artifact_root),
                )
                test_failure_output += "\n" + store.read_artifact_by_id(latest_test_failure.stdout_artifact_id).content
            except Exception:
                pass
        approved_missing_cli_owner = (
            continuation.current_node == "classify_failure"
            and continuation.last_error_code == "DEPENDENCY_BUNDLE_MISSING_FOR_CONTEXT"
            and latest_test_failure is not None
            and "__webpack_require__(...).context is not a function" in test_failure_output
        )
        approved_reexecution_retry = (
            "-reexec-" in (continuation.stage_plan_id or "")
            and (
                (
                    continuation.current_node == "source_install_same_authority"
                    and continuation.last_error_code == "IDEMPOTENCY_KEY_REUSED"
                )
                or (
                    continuation.current_node == "classify_failure"
                    and continuation.last_error_code == "CAUSAL_EXECUTION_AMBIGUOUS"
                )
                or (
                    continuation.current_node == "execute_migration_owner"
                    and continuation.last_error_code == "TRANSFORMER_WORKFLOW_UNHANDLED_ERROR"
                )
                or (
                    continuation.current_node == "target_tree"
                    and continuation.last_error_code == "PROVEN_TARGET_INSTALL_NOT_VERIFIED"
                )
                or (
                    continuation.current_node == "target_install_same_authority"
                    and continuation.last_error_code == "FIRST_COMMAND_NOT_AUTHORIZED"
                )
                or (
                    continuation.current_node == "source_install_same_authority"
                    and continuation.last_error_code == "TRANSFORMER_WORKFLOW_UNHANDLED_ERROR"
                )
                or (
                    continuation.current_node == "propose_repair"
                    and continuation.last_error_code == "REPAIR_CAUSAL_KIND_MISMATCH"
                    and "cannot find module 'source-map'" in test_failure_output.lower()
                )
            )
        )
        if not (
            approved_authority_failure
            or approved_discovery_failure
            or approved_missing_cli_owner
            or approved_reexecution_retry
        ):
            raise TransformationContinuationError("STAGE_REEXECUTION_NOT_ALLOWED", "The blocked evidence is not the approved target-cohort authority failure")
        replay = session.scalar(
            select(WorkflowEventModel).where(
                WorkflowEventModel.run_id == continuation.run_id,
                WorkflowEventModel.idempotency_key == f"{continuation.id}:reexecute:{idempotency_key}",
            )
        )
        if replay is not None:
            stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
            if stage_plan is None:
                raise TransformationContinuationError("STAGE_PLAN_STALE", "Re-executed stage plan is missing")
            return StageExecutionPlan.model_validate(stage_plan.stage_plan)
        plan = session.get(MigrationPlanModel, continuation.plan_id)
        current = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
        run = session.get(MigrationRunModel, continuation.run_id)
        binding = session.scalar(
            select(StageWorkspaceBindingModel).where(
                StageWorkspaceBindingModel.run_id == continuation.run_id,
                StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                StageWorkspaceBindingModel.active.is_(True),
            )
        )
        if plan is None or current is None or run is None or binding is None:
            raise TransformationContinuationError("STAGE_REEXECUTION_CONTEXT_MISSING", "Stage re-execution evidence is incomplete")
        created_at = now or datetime.now(UTC)
        # Reexecution restarts the whole governed stage. Old step execution
        # pointers are audit history, not reusable work for the replacement.
        for step in session.scalars(
            select(StageStepModel).where(
                StageStepModel.run_id == run.id,
                StageStepModel.stage_id == continuation.current_stage_id,
            )
        ).all():
            step.status = "PENDING"
            step.attempt_id = None
            step.idempotency_key = None
            step.started_at = None
            step.completed_at = None
            step.execution_id = None
            step.output_checksum = None
            step.workspace_fingerprint = None
            step.artifact_ids = []
            step.updated_at = created_at
        workspace_drifted = StageSandboxCopier.fingerprint(Path(binding.workspace_path)) != binding.workspace_fingerprint
        if workspace_drifted and not (
            approved_discovery_failure or approved_missing_cli_owner or approved_reexecution_retry
        ):
            raise TransformationContinuationError("STALE_WORKSPACE", "The isolated stage workspace changed after the block")
        restored_fingerprint = None
        if approved_discovery_failure or approved_missing_cli_owner or approved_reexecution_retry:
            aliases = dict(run.workspace_aliases or {})
            baseline = aliases.get("BASELINE_SANDBOX")
            stage_root = aliases.get("STAGE_SANDBOX")
            expected = aliases.get("BASELINE_SANDBOX_FINGERPRINT") or binding.workspace_fingerprint
            if not baseline or not stage_root:
                raise TransformationContinuationError("STAGE_REEXECUTION_CONTEXT_MISSING", "The sealed predecessor is unavailable for discovery re-execution")
            try:
                from app.services.transformer_stage_service import TransformerStageError, TransformerStageService

                restored_fingerprint = TransformerStageService.reconstruct_workspace(
                    baseline,
                    binding.workspace_path,
                    stage_root,
                    expected,
                )
            except TransformerStageError as error:
                raise TransformationContinuationError(error.code, error.message) from error
            binding.workspace_fingerprint = restored_fingerprint
            binding.last_verified_fingerprint = restored_fingerprint
            binding.last_verified_at = now or datetime.now(UTC)
        current_values = dict(current.stage_plan or {})
        catalogue = CompatibilityCatalogueProvider().load((plan.plan or {}).get("catalogue_version", "catalog-v4"))
        entry = catalogue.entry_for(current_values["source_family"], current_values["target_family"])
        current_values.update(
            target_exact=entry.target_angular_exact,
            target_cli_exact=entry.target_cli_exact,
            target_cohort=entry.target_cohort(),
        )
        commands = dict(current_values.get("commands") or {})
        final_install = [dict(item) for item in commands.get("final_install", [])]
        if final_install:
            final_install[0].update(
                template_id="tpl-npm-ci-final-v3",
                template_version=3,
                arguments=["ci", "--include=optional"],
            )
            commands["final_install"] = final_install
            current_values["commands"] = commands
        replacement_version = current.version + 1
        reexecution_suffix = f"reexec-{hashlib.sha256(idempotency_key.encode()).hexdigest()[:12]}"
        plan_id = f"{plan.id[:128 - len(reexecution_suffix) - 1]}-{reexecution_suffix}"
        plan_values = dict(plan.plan or {})
        plan_values.update(plan_id=plan_id, version=replacement_version, checksum="sha256:" + "0" * 64)
        rebuilt_plan = MigrationPlan.model_validate(plan_values)
        rebuilt_plan = rebuilt_plan.model_copy(update={"checksum": checksum_model(rebuilt_plan)})
        stage_id = f"{current.id[:128 - len(reexecution_suffix) - 1]}-{reexecution_suffix}"
        rebuilt = StageExecutionPlan.model_validate(
            {
                **current_values,
                "stage_plan_id": stage_id,
                "plan_version": replacement_version,
                "checksum": "sha256:" + "0" * 64,
            }
        )
        rebuilt = rebuilt.model_copy(update={
            "build_system_decision": BuildSystemDecision.create(
                decision_id=f"builder-{run.id}-{continuation.current_stage_id}-reexec-{replacement_version}",
                builder=rebuilt.build_system_decision.builder,
                action=rebuilt.build_system_decision.action,
                rationale=rebuilt.build_system_decision.rationale,
            ),
            "checksum": "sha256:" + "0" * 64,
        })
        rebuilt = rebuilt.model_copy(update={"checksum": checksum_model(rebuilt)})
        store = LocalFilesystemArtifactStore(Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root))
        stored = store.write_text_artifact(
            run.id,
            f"04_workflow_state/stages/{continuation.current_stage_id}/reexecution/{stage_id}.json",
            json.dumps({
                "reason": "refresh exact target cohort from current compatibility catalogue",
                "old_stage_plan_checksum": current.checksum,
                "new_stage_plan_checksum": rebuilt.checksum,
                "target_cohort": rebuilt.target_cohort,
                "workspace_fingerprint": binding.workspace_fingerprint,
                "restored_from_sealed_predecessor": restored_fingerprint is not None,
            }, sort_keys=True, indent=2),
            ArtifactType.JSON,
            stage_id=continuation.current_stage_id,
            created_by="transformation-reexecution",
            created_at=created_at,
            input_hashes={"stage_plan": current.checksum, "workspace": binding.workspace_fingerprint},
            policy_version="proven-stage-reexecution-v1",
        )
        session.add(ArtifactMetadataModel(
            id="metadata-" + stored.ref.artifact_id,
            run_id=run.id,
            stage_id=continuation.current_stage_id,
            artifact_type=stored.ref.artifact_type.value,
            relative_path=stored.ref.relative_path,
            checksum=stored.ref.checksum,
            created_at=created_at,
        ))
        current.status = "stale"
        plan.status = "stale"
        plan_artifact_ids = list(plan.artifact_ids or []) + [stored.ref.artifact_id]
        plan_artifact_checksums = dict(plan.artifact_checksums or {})
        plan_artifact_checksums[stored.ref.artifact_id] = stored.ref.checksum
        session.add(MigrationPlanModel(
            id=plan_id,
            run_id=run.id,
            idempotency_key=idempotency_key,
            request_checksum=stored.ref.checksum,
            actor="transformation-reexecution",
            correlation_id=idempotency_key,
            status="approved_for_execution",
            version=replacement_version,
            plan=rebuilt_plan.model_dump(mode="json"),
            checksum=rebuilt_plan.checksum,
            artifact_ids=plan_artifact_ids,
            artifact_checksums=plan_artifact_checksums,
            state_version=continuation.state_version + 1,
            event_sequence=0,
            created_at=created_at,
            updated_at=created_at,
        ))
        replacement = StageExecutionPlanModel(
            id=stage_id,
            run_id=run.id,
            migration_plan_id=plan_id,
            stage_id=continuation.current_stage_id,
            idempotency_key=idempotency_key,
            request_checksum=stored.ref.checksum,
            actor="transformation-reexecution",
            correlation_id=idempotency_key,
            status="approved_for_execution",
            version=replacement_version,
            stage_plan=rebuilt.model_dump(mode="json"),
            checksum=rebuilt.checksum,
            artifact_ids=[stored.ref.artifact_id],
            artifact_checksums={stored.ref.artifact_id: stored.ref.checksum},
            state_version=continuation.state_version + 1,
            event_sequence=0,
            created_at=created_at,
            updated_at=created_at,
        )
        session.add(replacement)
        session.add(BuildSystemDecisionModel(
            id="decision-" + hashlib.sha256(stage_id.encode()).hexdigest()[:12],
            run_id=run.id,
            stage_plan_id=stage_id,
            decision_id=rebuilt.build_system_decision.decision_id,
            decision=rebuilt.build_system_decision.model_dump(mode="json"),
            checksum=rebuilt.build_system_decision.checksum,
            created_at=created_at,
        ))
        pointer = session.scalar(select(ActivePlanVersionModel).where(
            ActivePlanVersionModel.run_id == run.id,
            ActivePlanVersionModel.scope == continuation.current_stage_id,
        ))
        if pointer is None:
            raise TransformationContinuationError("STAGE_REEXECUTION_CONTEXT_MISSING", "Active stage plan pointer is missing")
        migration_pointer = session.scalar(select(ActivePlanVersionModel).where(
            ActivePlanVersionModel.run_id == run.id,
            ActivePlanVersionModel.scope == "migration",
        ))
        if migration_pointer is None:
            raise TransformationContinuationError("STAGE_REEXECUTION_CONTEXT_MISSING", "Active migration plan pointer is missing")
        migration_pointer.migration_plan_id = plan_id
        migration_pointer.stage_plan_id = stage_id
        migration_pointer.version = replacement_version
        migration_pointer.state_version = continuation.state_version + 1
        migration_pointer.updated_at = created_at
        pointer.migration_plan_id = plan_id
        pointer.stage_plan_id = stage_id
        pointer.version = replacement_version
        pointer.state_version = continuation.state_version + 1
        pointer.updated_at = created_at
        continuation.plan_id = plan_id
        continuation.plan_checksum = rebuilt_plan.checksum
        continuation.stage_plan_id = stage_id
        continuation.stage_plan_checksum = rebuilt.checksum
        continuation.status = TransformationStatus.QUEUED.value
        continuation.current_node = "create_g07"
        continuation.last_error_code = None
        continuation.last_error_message = None
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.wake_sequence += 1
        continuation.state_version += 1
        continuation.updated_at = created_at
        append_continuation_event(
            session,
            continuation,
            event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_RESUMED,
            key=f"reexecute:{idempotency_key}",
            reason="blocked stage re-execution rebuilt its exact target cohort and returned to G07",
            payload={"stage_plan_id": stage_id, "artifact_id": stored.ref.artifact_id},
            occurred_at=created_at,
            actor="control-tower",
        )
        return rebuilt

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
            .order_by(StageWorkspaceBindingModel.created_at.desc())
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
