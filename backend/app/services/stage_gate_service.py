"""Durable, fingerprint-bound Transformer gate decisions."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.contracts import WorkflowEventType
from app.domain.planning import (
    SUPPORTED_VALIDATION_TARGETS,
    TRANSFORMER_SEMANTIC_VERSION_PROVEN,
    normalize_stage_plan_semantics,
)
from app.domain.transformation import (
    ProvenTransformationNode,
    StageGateDecisionRequest,
    StageGateId,
    TransformationNode,
)
from app.artifact_store import ArtifactNotFoundError, ArtifactStoreError, LocalFilesystemArtifactStore
from app.repositories.models import (
    ArtifactMetadataModel,
    LlmInvocationModel,
    MigrationPlanModel,
    MigrationStageModel,
    MigrationRunModel,
    RepairAttemptModel,
    StageExecutionPlanModel,
    StageGateDecisionModel,
    StageGatePackageModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
    WorkflowEventModel,
)
from app.services.artifact_binding import canonical_artifact_set_checksum
from app.services.repair_application_service import (
    RepairProposal,
    RepairReview,
    _LEGACY_SEMANTIC_RECOVERY_CODES,
    _SEMANTIC_RETRY_CODES,
)
from app.services.repair_lifecycle_service import RepairLifecycleService
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.dependency_repair_preflight_service import (
    DependencyRepairPreflightError,
    DependencyRepairPreflightService,
)
from app.services.transformation_continuation_service import (
    append_continuation_event,
)
from app.state import StateTransitionService


class StageGateError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


_NEXT_NODE = {
    StageGateId.G07.value: TransformationNode.BOOTSTRAP_INSTALL.value,
    StageGateId.G08.value: TransformationNode.FINAL_INSTALL.value,
    StageGateId.G09.value: TransformationNode.CREATE_G12.value,
    StageGateId.G10.value: TransformationNode.APPLY_REPAIR.value,
    StageGateId.G11.value: TransformationNode.CREATE_G09.value,
    StageGateId.G12.value: TransformationNode.SEAL_STAGE.value,
}

_SEMANTIC_RECOVERY_REASON = "semantic retry exhausted recovery requested"
_BOUND_CANDIDATE_RECOVERY_REASON = "deterministic bound candidate recovery requested"


def _gate_successor_node(session: Session, continuation: TransformationContinuationModel, gate_id: str) -> str:
    """Immutable gate successor selected by the persisted graph semantics.

    Legacy plans keep their historical successors.  Proven plans route an
    approved G09 to exact validated-generation promotion instead of directly
    creating G12; G11→CREATE_G09 and G12→SEAL remain for both tables.
    """
    node = _NEXT_NODE[gate_id]
    if gate_id != StageGateId.G09.value or not getattr(continuation, "stage_plan_id", None):
        return node
    plan_row = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
    try:
        semantic_version, _mode, _authorization = normalize_stage_plan_semantics(
            (plan_row.stage_plan if plan_row else None) or {}
        )
    except ValueError as error:
        raise StageGateError(
            getattr(error, "code", "TRANSFORMER_SEMANTIC_VERSION_UNSUPPORTED"), str(error)
        ) from error
    if semantic_version == TRANSFORMER_SEMANTIC_VERSION_PROVEN:
        return ProvenTransformationNode.PROMOTE_VALIDATED.value
    return node


def _canonical_revision_payload(value: object, *, review: bool) -> dict | None:
    """Re-serialize a human-revision lineage payload through its authoritative schema.

    ``request_revision`` embeds the parent proposal/review inside the revision
    context after a pydantic round-trip, which adds optional nested operation
    fields with ``null`` values (for example ``blocking_dependency``,
    ``checkpoint_id``, ``content``, ``failure_type``, ``repair_kind``,
    ``schema_version``, ``strategy``, ``target_state``), while the immutable
    parent artifact stored by ``json.dumps`` omits those keys. Both sides are
    therefore canonicalized with the same model and ``exclude_none=True`` so
    representation-only differences cannot invalidate semantically identical
    lineage. Real semantic drift (changed package/version/operation/content)
    survives the canonicalization and still fails closed.
    """
    if not isinstance(value, dict):
        return None
    model = RepairReview if review else RepairProposal
    return model.model_validate(value).model_dump(mode="json", exclude_none=True)


class StageGateService:
    @staticmethod
    def _current_plan_version(session: Session, continuation: TransformationContinuationModel) -> int:
        plan = session.get(MigrationPlanModel, continuation.plan_id)
        if plan is None or plan.run_id != continuation.run_id:
            raise StageGateError("PLAN_BINDING_MISSING", "Migration plan for the run is missing")
        return plan.version

    def create(
        self,
        session: Session,
        continuation: TransformationContinuationModel,
        *,
        gate_id: str,
        package_artifact_id: str,
        package_checksum: str,
        artifact_set_checksum: str,
        workspace_fingerprint: str,
        now: datetime | None = None,
    ) -> StageGatePackageModel:
        StageGateId(gate_id)
        if gate_id == StageGateId.G10.value:
            self._validate_repair_lineage(
                session,
                continuation,
                package_artifact_id,
                package_checksum,
                artifact_set_checksum=artifact_set_checksum,
            )
            self._validate_dependency_repair_preflight(
                session, continuation, package_artifact_id
            )
        existing = session.scalar(
            select(StageGatePackageModel).where(
                StageGatePackageModel.run_id == continuation.run_id,
                StageGatePackageModel.stage_id == continuation.current_stage_id,
                StageGatePackageModel.gate_id == gate_id,
                StageGatePackageModel.status == "pending",
            )
        )
        if existing is not None:
            if (
                existing.package_checksum != package_checksum
                or existing.workspace_fingerprint != workspace_fingerprint
            ):
                raise StageGateError("GATE_PACKAGE_CONFLICT", "Pending gate package binding changed")
            return existing
        created_at = now or datetime.now(UTC)
        latest = session.scalar(
            select(StageGatePackageModel.gate_version)
            .where(
                StageGatePackageModel.run_id == continuation.run_id,
                StageGatePackageModel.stage_id == continuation.current_stage_id,
                StageGatePackageModel.gate_id == gate_id,
            )
            .order_by(StageGatePackageModel.gate_version.desc())
            .limit(1)
        )
        package = StageGatePackageModel(
            id=f"gate-package-{uuid4().hex[:12]}",
            run_id=continuation.run_id,
            stage_id=continuation.current_stage_id,
            gate_id=gate_id,
            gate_version=(latest or 0) + 1,
            status="pending",
            package_artifact_id=package_artifact_id,
            package_checksum=package_checksum,
            artifact_set_checksum=artifact_set_checksum,
            plan_id=continuation.plan_id,
            plan_version=self._current_plan_version(session, continuation),
            stage_plan_id=continuation.stage_plan_id,
            stage_plan_checksum=continuation.stage_plan_checksum,
            workspace_fingerprint=workspace_fingerprint,
            expected_state_version=continuation.state_version + 1,
            created_at=created_at,
        )
        session.add(package)
        expected_state_version = continuation.state_version
        continuation.status = "waiting_gate"
        continuation.current_node = f"wait_{gate_id.lower()}"
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.state_version += 1
        continuation.updated_at = created_at
        session.flush()
        StateTransitionService(session).append_audit_event(
            run_id=continuation.run_id,
            idempotency_key=f"{package.id}:created",
            event_type=WorkflowEventType[f"{gate_id}_CREATED"],
            actor="transformer",
            reason=f"{gate_id} evidence package created",
            occurred_at=created_at,
            payload={"stage_id": continuation.current_stage_id, "package_checksum": package_checksum},
        )
        append_continuation_event(
            session,
            continuation,
            event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_WAITING,
            key=f"wait:waiting_gate:{expected_state_version}",
            reason=f"continuation waits for {gate_id} decision",
            payload={
                "gate_id": gate_id,
                "expected_state_version": expected_state_version,
            },
            occurred_at=created_at,
        )
        return package

    def decide(
        self,
        session: Session,
        continuation: TransformationContinuationModel,
        gate_id: str,
        request: StageGateDecisionRequest,
        *,
        actor: str,
        observed_workspace_fingerprint: str | None = None,
        now: datetime | None = None,
    ) -> StageGateDecisionModel:
        StageGateId(gate_id)
        checksum = self._checksum(
            {"run_id": continuation.run_id, "gate_id": gate_id, "actor": actor, **request.model_dump(mode="json")}
        )
        existing = session.scalar(
            select(StageGateDecisionModel).where(
                StageGateDecisionModel.run_id == continuation.run_id,
                StageGateDecisionModel.idempotency_key == request.idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_checksum != checksum:
                raise StageGateError("IDEMPOTENCY_PAYLOAD_MISMATCH", "Decision key has a different payload")
            return existing
        review_override_required = False
        package = session.scalar(
            select(StageGatePackageModel)
            .where(
                StageGatePackageModel.run_id == continuation.run_id,
                StageGatePackageModel.stage_id == continuation.current_stage_id,
                StageGatePackageModel.gate_id == gate_id,
                StageGatePackageModel.status == "pending",
            )
            .order_by(StageGatePackageModel.gate_version.desc())
        )
        if package is None:
            raise StageGateError("GATE_NOT_PENDING", f"{gate_id} is not pending")
        plan = session.get(MigrationPlanModel, continuation.plan_id)
        if (
            plan is None
            or plan.run_id != continuation.run_id
            or package.plan_version != plan.version
        ):
            package.status = "stale"
            package.stale_at = now or datetime.now(UTC)
            raise StageGateError("STALE_GATE_BINDING", "Gate package is bound to a stale plan version")
        if gate_id == StageGateId.G10.value:
            self._validate_repair_lineage(
                session,
                continuation,
                package.package_artifact_id,
                package.package_checksum,
                artifact_set_checksum=package.artifact_set_checksum,
            )
        if (
            continuation.state_version != request.expected_state_version
            or package.expected_state_version != request.expected_state_version
        ):
            raise StageGateError("TRANSFORMATION_STATE_CONFLICT", "Transformer state changed; refresh")
        if (
            package.package_checksum != request.package_checksum
            or package.workspace_fingerprint != request.workspace_fingerprint
            or (
                observed_workspace_fingerprint is not None
                and observed_workspace_fingerprint != package.workspace_fingerprint
            )
        ):
            raise StageGateError("STALE_GATE_BINDING", "Gate package or workspace fingerprint is stale")
        decided_at = now or datetime.now(UTC)
        accepted = request.decision == "approve"
        decision = StageGateDecisionModel(
            id=f"gate-decision-{uuid4().hex[:12]}",
            gate_package_id=package.id,
            run_id=continuation.run_id,
            stage_id=continuation.current_stage_id,
            gate_id=gate_id,
            decision=request.decision,
            actor=actor,
            comment=request.comment,
            idempotency_key=request.idempotency_key,
            request_checksum=checksum,
            expected_state_version=request.expected_state_version,
            package_checksum=request.package_checksum,
            workspace_fingerprint=request.workspace_fingerprint,
            accepted=accepted,
            reason_code=None if accepted else request.decision.upper(),
            created_at=decided_at,
        )
        session.add(decision)
        package.status = "approved" if accepted else "rejected"
        expected_state_version = continuation.state_version
        attempt = None
        if accepted:
            if gate_id == StageGateId.G10.value:
                attempt = session.scalar(
                    select(RepairAttemptModel).where(
                        RepairAttemptModel.g10_gate_package_id == package.id,
                        RepairAttemptModel.run_id == continuation.run_id,
                        RepairAttemptModel.stage_id == continuation.current_stage_id,
                    )
                )
                if attempt is None:
                    raise StageGateError(
                        "G10_LINEAGE_STALE", "G10 repair attempt binding is missing"
                    )
                RepairLifecycleService.transition_in_session(
                    session,
                    attempt,
                    "approved_pending_execution",
                    reason="human G10 approval released reviewed repair for execution",
                    actor=actor,
                    now=decided_at,
                )
            elif gate_id == StageGateId.G11.value:
                attempt = session.scalar(
                    select(RepairAttemptModel)
                    .where(
                        RepairAttemptModel.run_id == continuation.run_id,
                        RepairAttemptModel.stage_id == continuation.current_stage_id,
                    )
                    .order_by(RepairAttemptModel.attempt_number.desc())
                )
                if attempt is not None:
                    RepairLifecycleService.transition_in_session(
                        session,
                        attempt,
                        "validation_passed",
                        reason="human G11 approval accepted validated stage",
                        actor=actor,
                        now=decided_at,
                    )
                    attempt.completed_at = decided_at
            continuation.status = "queued"
            continuation.current_node = self._gate_successor_node(session, continuation, gate_id)
            continuation.wake_sequence += 1
        else:
            if gate_id == StageGateId.G11.value:
                attempt = session.scalar(
                    select(RepairAttemptModel)
                    .where(
                        RepairAttemptModel.run_id == continuation.run_id,
                        RepairAttemptModel.stage_id == continuation.current_stage_id,
                    )
                    .order_by(RepairAttemptModel.attempt_number.desc())
                )
                if attempt is not None:
                    RepairLifecycleService.transition_in_session(
                        session,
                        attempt,
                        "validation_failed",
                        reason="human G11 rejection blocked stage validation",
                        actor=actor,
                        now=decided_at,
                    )
                    attempt.completed_at = decided_at
            continuation.status = "blocked"
            continuation.last_error_code = f"{gate_id}_{request.decision.upper()}"
            continuation.last_error_message = request.comment or f"{gate_id} was not approved"
        continuation.state_version += 1
        continuation.updated_at = decided_at
        session.flush()
        if accepted:
            append_continuation_event(
                session,
                continuation,
                event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_RESUMED,
                key=f"gate-accepted:{gate_id}:{package.id}",
                reason=f"{gate_id} approved; continuation requeued",
                payload={
                    "gate_id": gate_id,
                    "package_id": package.id,
                    "expected_state_version": expected_state_version,
                },
                occurred_at=decided_at,
                actor=actor,
            )
        else:
            append_continuation_event(
                session,
                continuation,
                event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_BLOCKED,
                key=f"block:{expected_state_version}:{continuation.last_error_code}",
                reason=continuation.last_error_message,
                payload={
                    "last_error_code": continuation.last_error_code,
                    "expected_state_version": expected_state_version,
                    "reason": request.comment or f"{gate_id} was not approved",
                    "gate_id": gate_id,
                },
                occurred_at=decided_at,
                actor=actor,
            )
        StateTransitionService(session).append_audit_event(
            run_id=continuation.run_id,
            idempotency_key=f"{request.idempotency_key}:event",
            event_type=WorkflowEventType[
                f"{gate_id}_{'APPROVED' if accepted else 'REJECTED'}"
            ],
            actor=actor,
            reason=f"{gate_id} {request.decision}",
            occurred_at=decided_at,
            payload={"stage_id": continuation.current_stage_id, "decision_id": decision.id},
        )
        return decision

    @staticmethod
    def _checksum(value: object) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    @classmethod
    def _validate_recovery_parent_lineage(
        cls,
        session: Session,
        continuation,
        attempt: RepairAttemptModel,
        parent: RepairAttemptModel,
        package: dict[str, object],
    ) -> None:
        """Prove the narrow proposal-less semantic-recovery parent path.

        Ordinary human-revision children still use the proposal/review lineage
        below. This branch is valid only for a parent terminalized by the
        governed semantic-recovery action, with its persisted retry evidence,
        immutable continuation event, and no proposal/review/apply evidence.
        """
        if (
            parent.run_id != attempt.run_id
            or parent.stage_id != attempt.stage_id
            or parent.attempt_number >= attempt.attempt_number
            or parent.status != "superseded"
            or parent.completed_at is None
        ):
            raise StageGateError(
                "REPAIR_PARENT_LINEAGE_INVALID",
                "G10 recovery parent lineage is invalid",
            )
        recovery_event = session.scalars(
            select(WorkflowEventModel).where(
                WorkflowEventModel.run_id == continuation.run_id,
                WorkflowEventModel.event_type
                == WorkflowEventType.TRANSFORMATION_CONTINUATION_RESUMED.value,
            )
        ).all()
        bound_event = next(
            (
                event
                for event in recovery_event
                if event.reason == _BOUND_CANDIDATE_RECOVERY_REASON
                and isinstance(event.payload, dict)
                and event.payload.get("attempt_id") == parent.id
                and event.payload.get("child_attempt_id") == attempt.id
            ),
            None,
        )
        parent_has_proposal_only = (
            parent.proposal_artifact_id is not None
            and parent.proposal_checksum is not None
            and parent.review_artifact_id is None
            and parent.review_checksum is None
            and bound_event is not None
        )
        if any(
            getattr(parent, field)
            for field in (
                "proposal_artifact_id",
                "proposal_checksum",
                "review_artifact_id",
                "review_checksum",
                "reviewer_invocation_id",
                "g10_gate_package_id",
                "apply_ledger_artifact_id",
                "apply_ledger_checksum",
                "validation_summary_artifact_id",
                "validation_summary_checksum",
                "post_fingerprint",
            )
        ) and not parent_has_proposal_only:
            raise StageGateError(
                "REPAIR_PARENT_LINEAGE_INVALID",
                "G10 recovery parent carries post-proposal evidence",
            )
        if parent_has_proposal_only and (
            (bound_event.payload or {}).get("source_proposal_checksum")
            != parent.proposal_checksum
        ):
            raise StageGateError(
                "REPAIR_PARENT_LINEAGE_INVALID",
                "G10 deterministic recovery parent proposal binding is stale",
            )
        if (
            package.get("parent_attempt_id") != parent.id
            or package.get("parent_review_artifact_id") is not None
            or package.get("parent_review_checksum") is not None
            or attempt.parent_review_artifact_id is not None
            or attempt.parent_review_checksum is not None
        ):
            raise StageGateError(
                "REPAIR_PARENT_LINEAGE_INVALID",
                "G10 recovery child carries a parent review reference",
            )
        if bound_event is not None:
            invocation = session.get(LlmInvocationModel, attempt.proposer_invocation_id)
            if (
                invocation is None
                or invocation.status != "completed"
                or invocation.role != "repair_proposer"
                or invocation.task_type != "repair_diagnosis"
                or invocation.deployment_alias != "deterministic-provenance-rebind"
                or (invocation.artifact_checksums or {}).get(attempt.proposal_artifact_id)
                != attempt.proposal_checksum
            ):
                raise StageGateError(
                    "REPAIR_PARENT_LINEAGE_INVALID",
                    "G10 deterministic candidate recovery evidence is stale",
                )
            return
        if not any(
            event.reason == _SEMANTIC_RECOVERY_REASON
            and isinstance(event.payload, dict)
            and event.payload.get("attempt_id") == parent.id
            and event.payload.get("child_attempt_id") == attempt.id
            for event in recovery_event
        ):
            raise StageGateError(
                "REPAIR_PARENT_LINEAGE_INVALID",
                "G10 recovery ancestry event is missing or stale",
            )
        recovered_proposer_id = parent.proposer_invocation_id
        retry_invocation_id = (
            recovered_proposer_id
            if isinstance(recovered_proposer_id, str)
            and ":recovery-" in recovered_proposer_id
            else f"{parent.id}:proposer:semantic-retry-1"
        )
        base_invocation = session.scalar(
            select(LlmInvocationModel).where(
                LlmInvocationModel.run_id == attempt.run_id,
                LlmInvocationModel.stage_id == attempt.stage_id,
                LlmInvocationModel.id == f"{parent.id}:proposer",
                LlmInvocationModel.idempotency_key == f"{parent.id}:proposer",
            )
        )
        retry_invocation = session.scalar(
            select(LlmInvocationModel).where(
                LlmInvocationModel.run_id == attempt.run_id,
                LlmInvocationModel.stage_id == attempt.stage_id,
                LlmInvocationModel.id == retry_invocation_id,
                LlmInvocationModel.idempotency_key
                == retry_invocation_id,
            )
        )
        base_valid = (
            base_invocation is not None
            and (
                base_invocation.status == "failed"
                or (
                    isinstance(recovered_proposer_id, str)
                    and ":recovery-" in recovered_proposer_id
                    and base_invocation.status == "uncertain_abandoned"
                )
            )
        )
        retry_valid = (
            retry_invocation is not None
            and retry_invocation.status == "failed"
            and retry_invocation.failure_code
            in (_SEMANTIC_RETRY_CODES | _LEGACY_SEMANTIC_RECOVERY_CODES)
            and (
                (
                    isinstance(recovered_proposer_id, str)
                    and ":recovery-" in recovered_proposer_id
                    and retry_invocation.failure_stage == "repair_semantics"
                    and retry_invocation.retries >= 0
                )
                or (
                    not isinstance(recovered_proposer_id, str)
                    or ":recovery-" not in recovered_proposer_id
                )
                and retry_invocation.retries == 1
                and retry_invocation.failure_stage == "repair_semantics"
            )
        )
        if (
            not base_valid
            or not retry_valid
        ):
            raise StageGateError(
                "REPAIR_PARENT_LINEAGE_INVALID",
                "G10 recovery semantic-retry evidence is missing or stale",
            )

    @classmethod
    def _validate_repair_lineage(
        cls,
        session: Session,
        continuation,
        package_artifact_id: str,
        package_checksum: str,
        artifact_set_checksum: str | None = None,
        expected_workspace_fingerprint: str | None = None,
    ) -> bool:
        """Verify the G10 envelope and its role artifacts.

        Role authority contract (never weakened):

        - ``failure_evidence`` and ``context_pack`` are PRE-ATTEMPT roles:
          FailureEvidenceService writes them before the RepairAttempt row
          exists, so their envelope ``attempt_id`` is legitimately NULL; a
          non-NULL id must still equal the current attempt.
        - ``proposal`` and ``review`` are ATTEMPT-BOUND roles: their envelope
          ``attempt_id`` must be the exact RepairAttempt id (NULL is rejected).
        - The candidate.diff artifact (``diff_artifact_id`` / ``diff_checksum``)
          is ATTEMPT-BOUND and proposal-bound (its envelope ``input_hashes``
          must reference the attempt's proposal checksum); it must exist, be
          non-empty, and its checksum must match the package binding.
        - Every role still requires the exact run id, stage id, artifact
          identity, and checksum.
        - The four role artifact ids must be distinct: a single artifact id may
          not satisfy two roles, and role-specific content checks always run
          per role.
        - When ``artifact_set_checksum`` is supplied, the canonical set checksum
          over (failure evidence, context pack, proposal, review, envelope)
          must match it.
        - A CHILD attempt (``parent_attempt_id`` set) must additionally prove
          the reviewer request-changes lineage: the package must reference the
          parent attempt and the parent's persisted request_changes review
          artifact (id + checksum), the parent row must be a real earlier
          attempt of the same run/stage, and the parent's review artifact must
          be a checksum-bound, attempt-bound envelope whose content decision is
          ``request_changes``. The revision context's embedded parent
          proposal/review are compared SEMANTICALLY after canonicalization
          through the authoritative RepairProposal/RepairReview schemas (None
          values excluded), so representation-only null-key differences cannot
          invalidate legitimate lineage while real semantic drift still fails.
          Any deviation fails closed with ``REPAIR_PARENT_LINEAGE_INVALID``. A
          fresh attempt must not carry parent review references at all.
        """
        session.flush()
        metadata = session.get(ArtifactMetadataModel, "metadata-" + package_artifact_id)
        run = session.get(MigrationRunModel, continuation.run_id)
        if metadata is None or run is None or metadata.run_id != continuation.run_id or metadata.checksum != package_checksum:
            raise StageGateError("G10_LINEAGE_STALE", "G10 package artifact binding is invalid")
        try:
            store = LocalFilesystemArtifactStore(Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root))
            stored_package = store.read_artifact(continuation.run_id, metadata.relative_path)
            if (
                stored_package.ref.artifact_id != package_artifact_id
                or stored_package.ref.checksum != package_checksum
                or stored_package.envelope is None
                or stored_package.envelope.run_id != continuation.run_id
                or stored_package.envelope.stage_id != continuation.current_stage_id
            ):
                raise StageGateError("G10_LINEAGE_STALE", "G10 package envelope binding is invalid")
            package = json.loads(stored_package.content)
        except (ArtifactNotFoundError, ArtifactStoreError, OSError, ValueError, TypeError) as error:
            raise StageGateError("G10_LINEAGE_STALE", "G10 package artifact cannot be verified") from error
        if package.get("gate_id") != StageGateId.G10.value or package.get("run_id") != continuation.run_id or package.get("stage_id") != continuation.current_stage_id:
            raise StageGateError("G10_LINEAGE_STALE", "G10 package scope is invalid")
        review_override_required = package.get("review_override_required")
        if not isinstance(review_override_required, bool):
            raise StageGateError("G10_LINEAGE_STALE", "G10 review override binding is missing")
        attempt = session.scalar(
            select(RepairAttemptModel).where(
                RepairAttemptModel.id == package.get("repair_attempt_id"),
                RepairAttemptModel.run_id == continuation.run_id,
                RepairAttemptModel.stage_id == continuation.current_stage_id,
            )
        )
        binding = session.scalar(
            select(StageWorkspaceBindingModel).where(
                StageWorkspaceBindingModel.id == package.get("workspace_binding_id"),
                StageWorkspaceBindingModel.run_id == continuation.run_id,
                StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                StageWorkspaceBindingModel.active.is_(True),
            )
        )
        stage_plan = session.scalar(
            select(StageExecutionPlanModel).where(
                StageExecutionPlanModel.id == continuation.stage_plan_id,
                StageExecutionPlanModel.run_id == continuation.run_id,
                StageExecutionPlanModel.stage_id == continuation.current_stage_id,
                StageExecutionPlanModel.checksum == continuation.stage_plan_checksum,
            )
        )
        if attempt is None or binding is None or stage_plan is None or attempt.status not in {
            "review_accepted", "request_changes", "waiting_g10",
            "approved_pending_execution", "applying", "executing", "applied",
            "applied_verified", "migration_retried", "validation_passed",
        }:
            raise StageGateError("G10_LINEAGE_STALE", "G10 repair attempt is not in a controlled apply state")
        if stored_package.envelope.attempt_id != attempt.id:
            raise StageGateError("G10_LINEAGE_STALE", "G10 package attempt binding is stale")
        parent_proposal_payload = None
        parent_review_payload = None
        parent = None
        recovery_parent = False
        correction_parent = False
        if attempt.parent_attempt_id is not None:
            parent = session.get(RepairAttemptModel, attempt.parent_attempt_id)
            if (
                parent is None
                or parent.run_id != attempt.run_id
                or parent.stage_id != attempt.stage_id
                or parent.attempt_number >= attempt.attempt_number
            ):
                raise StageGateError(
                    "REPAIR_PARENT_LINEAGE_INVALID",
                    "G10 child repair parent lineage is invalid",
                )
            if str(attempt.diagnosis or "").startswith("validation correction;"):
                if (
                    package.get("parent_attempt_id") != parent.id
                    or package.get("parent_review_artifact_id") is not None
                    or package.get("parent_review_checksum") is not None
                    or parent.apply_ledger_artifact_id is None
                    or parent.apply_ledger_checksum is None
                    or parent.post_fingerprint is None
                ):
                    raise StageGateError(
                        "REPAIR_PARENT_LINEAGE_INVALID",
                        "G10 validation-correction parent lineage is invalid",
                    )
                correction_parent = True
            elif parent.review_artifact_id is None and parent.review_checksum is None:
                cls._validate_recovery_parent_lineage(
                    session, continuation, attempt, parent, package
                )
                recovery_parent = True
            else:
                if (
                    package.get("parent_attempt_id") != parent.id
                    or package.get("parent_review_artifact_id") != parent.review_artifact_id
                    or package.get("parent_review_checksum") != parent.review_checksum
                ):
                    raise StageGateError(
                        "REPAIR_PARENT_LINEAGE_INVALID",
                        "G10 parent review reference does not match authoritative state",
                    )
                parent_metadata = session.get(
                    ArtifactMetadataModel, "metadata-" + str(parent.review_artifact_id)
                )
                parent_proposal_metadata = session.get(
                    ArtifactMetadataModel, "metadata-" + str(parent.proposal_artifact_id)
                )
                if (
                    parent_metadata is None
                    or parent_proposal_metadata is None
                    or parent_metadata.run_id != continuation.run_id
                    or parent_proposal_metadata.run_id != continuation.run_id
                    or parent_metadata.stage_id != continuation.current_stage_id
                    or parent_proposal_metadata.stage_id != continuation.current_stage_id
                    or parent_metadata.checksum != parent.review_checksum
                    or parent_proposal_metadata.checksum != parent.proposal_checksum
                ):
                    raise StageGateError(
                        "REPAIR_PARENT_LINEAGE_INVALID",
                        "G10 parent review artifact binding is invalid",
                    )
                try:
                    stored_parent_review = store.read_artifact(
                        continuation.run_id, parent_metadata.relative_path
                    )
                    stored_parent_proposal = store.read_artifact(
                        continuation.run_id, parent_proposal_metadata.relative_path
                    )
                    if (
                        stored_parent_review.ref.artifact_id != parent.review_artifact_id
                        or stored_parent_review.ref.checksum != parent.review_checksum
                        or stored_parent_proposal.ref.artifact_id != parent.proposal_artifact_id
                        or stored_parent_proposal.ref.checksum != parent.proposal_checksum
                    ):
                        raise StageGateError(
                            "REPAIR_PARENT_LINEAGE_INVALID",
                            "G10 parent review artifact identity changed",
                        )
                    parent_review_payload = json.loads(stored_parent_review.content)
                    parent_proposal_payload = json.loads(stored_parent_proposal.content)
                except (ArtifactNotFoundError, ArtifactStoreError, OSError, ValueError, TypeError) as error:
                    raise StageGateError(
                        "REPAIR_PARENT_LINEAGE_INVALID",
                        "G10 parent review artifact cannot be verified",
                    ) from error
                parent_envelope = stored_parent_review.envelope
                parent_proposal_envelope = stored_parent_proposal.envelope
                if (
                    parent_envelope is None
                    or parent_proposal_envelope is None
                    or parent_envelope.run_id != continuation.run_id
                    or parent_proposal_envelope.run_id != continuation.run_id
                    or parent_envelope.stage_id != continuation.current_stage_id
                    or parent_proposal_envelope.stage_id != continuation.current_stage_id
                    or parent_envelope.attempt_id != parent.id
                    or parent_proposal_envelope.attempt_id != parent.id
                    or parent_review_payload.get("decision") not in {"request_changes", "accept"}
                ):
                    raise StageGateError(
                        "REPAIR_PARENT_LINEAGE_INVALID",
                        "G10 parent review lineage is not revisable",
                    )
        elif (
            package.get("parent_attempt_id") is not None
            or package.get("parent_review_artifact_id") is not None
            or package.get("parent_review_checksum") is not None
        ):
            raise StageGateError(
                "REPAIR_PARENT_LINEAGE_INVALID",
                "G10 package carries a parent review reference without a parent attempt",
            )
        diff_metadata = session.scalar(
            select(ArtifactMetadataModel).where(
                ArtifactMetadataModel.run_id == continuation.run_id,
                ArtifactMetadataModel.stage_id == continuation.current_stage_id,
                ArtifactMetadataModel.relative_path.like(
                    f"05_repairs/attempt-{attempt.id}/candidate%.diff"
                ),
            )
            .order_by(ArtifactMetadataModel.created_at.desc())
            .limit(1)
        )
        if diff_metadata is None:
            raise StageGateError("G10_LINEAGE_STALE", "G10 candidate diff artifact is missing")
        try:
            stored_diff = store.read_artifact(continuation.run_id, diff_metadata.relative_path)
        except (ArtifactNotFoundError, ArtifactStoreError, OSError) as error:
            raise StageGateError(
                "G10_LINEAGE_STALE", "G10 candidate diff artifact cannot be verified"
            ) from error
        diff_artifact_id = diff_metadata.id.removeprefix("metadata-")
        if (
            stored_diff.ref.artifact_id != diff_artifact_id
            or stored_diff.ref.checksum != diff_metadata.checksum
            or stored_diff.envelope is None
            or stored_diff.envelope.run_id != continuation.run_id
            or stored_diff.envelope.stage_id != continuation.current_stage_id
            or stored_diff.envelope.attempt_id != attempt.id
            or stored_diff.envelope.input_hashes.get("proposal") != attempt.proposal_checksum
        ):
            raise StageGateError("G10_LINEAGE_STALE", "G10 candidate diff binding is invalid")
        if not stored_diff.content.strip():
            raise StageGateError("G10_LINEAGE_STALE", "G10 candidate diff is empty")
        plan = session.get(MigrationPlanModel, continuation.plan_id)
        if plan is None or plan.run_id != continuation.run_id:
            raise StageGateError("G10_LINEAGE_STALE", "G10 package plan binding is missing")
        expected = {
            "plan_version": plan.version,
            "failure_evidence_checksum": attempt.failure_evidence_checksum,
            "context_pack_checksum": attempt.context_pack_checksum,
            "proposal_artifact_id": attempt.proposal_artifact_id,
            "proposal_checksum": attempt.proposal_checksum,
            "review_artifact_id": attempt.review_artifact_id,
            "review_checksum": attempt.review_checksum,
            "proposer_invocation_id": attempt.proposer_invocation_id,
            "reviewer_invocation_id": attempt.reviewer_invocation_id,
            "workspace_fingerprint": expected_workspace_fingerprint or binding.workspace_fingerprint,
            "stage_plan_checksum": stage_plan.checksum,
            "risk_level": attempt.risk_level,
            "validation_targets": attempt.validation_targets,
            "diff_artifact_id": diff_artifact_id,
            "diff_checksum": diff_metadata.checksum,
        }
        if any(package.get(key) != value for key, value in expected.items()):
            raise StageGateError("G10_LINEAGE_STALE", "G10 inner lineage does not match authoritative state")
        try:
            live = StageSandboxCopier.fingerprint(Path(binding.workspace_path))
        except OSError as error:
            raise StageGateError("G10_LINEAGE_STALE", "G10 workspace is unavailable") from error
        if live != binding.workspace_fingerprint or package.get("workspace_path") != binding.workspace_path:
            raise StageGateError("G10_LINEAGE_STALE", "G10 workspace binding is stale")
        lineage_payload = {key: value for key, value in package.items() if key != "backend_lineage_checksum"}
        if package.get("backend_lineage_checksum") != cls._checksum(lineage_payload):
            raise StageGateError("G10_LINEAGE_STALE", "G10 backend lineage checksum is invalid")
        role_specs = (
            ("failure_evidence", attempt.failure_evidence_artifact_id, attempt.failure_evidence_checksum),
            ("context_pack", attempt.context_pack_artifact_id, attempt.context_pack_checksum),
            ("proposal", attempt.proposal_artifact_id, attempt.proposal_checksum),
            ("review", attempt.review_artifact_id, attempt.review_checksum),
        )
        role_ids = [artifact_id for _role, artifact_id, _checksum in role_specs]
        if any(item is None for item in role_ids):
            raise StageGateError("G10_LINEAGE_STALE", "G10 repair artifact lineage is missing")
        if len(set(role_ids)) != len(role_ids):
            raise StageGateError("G10_LINEAGE_STALE", "G10 repair artifact roles are not distinct")
        if artifact_set_checksum is not None:
            try:
                computed_set = canonical_artifact_set_checksum(
                    [
                        {"artifact_id": attempt.failure_evidence_artifact_id, "checksum": attempt.failure_evidence_checksum},
                        {"artifact_id": attempt.context_pack_artifact_id, "checksum": attempt.context_pack_checksum},
                        {"artifact_id": attempt.proposal_artifact_id, "checksum": attempt.proposal_checksum},
                        {"artifact_id": attempt.review_artifact_id, "checksum": attempt.review_checksum},
                        {"artifact_id": package_artifact_id, "checksum": package_checksum},
                    ]
                )
            except ValueError as error:
                raise StageGateError("G10_LINEAGE_STALE", "G10 artifact set checksum is invalid") from error
            if computed_set != artifact_set_checksum:
                raise StageGateError("G10_LINEAGE_STALE", "G10 artifact set checksum is invalid")
        for role, artifact_id, checksum in role_specs:
            pre_attempt = role in {"failure_evidence", "context_pack"}
            artifact = session.get(ArtifactMetadataModel, "metadata-" + str(artifact_id))
            if artifact is None or artifact.run_id != continuation.run_id or artifact.checksum != checksum:
                raise StageGateError("G10_LINEAGE_STALE", "G10 repair artifact lineage is missing")
            try:
                stored_artifact = store.read_artifact(continuation.run_id, artifact.relative_path)
                if stored_artifact.ref.artifact_id != artifact_id or stored_artifact.ref.checksum != checksum:
                    raise StageGateError("G10_LINEAGE_STALE", "G10 repair artifact identity changed")
                payload = json.loads(stored_artifact.content)
            except (ArtifactNotFoundError, ArtifactStoreError, OSError, ValueError, TypeError) as error:
                raise StageGateError("G10_LINEAGE_STALE", "G10 repair artifact cannot be verified") from error
            envelope = stored_artifact.envelope
            if (
                envelope is None
                or envelope.run_id != continuation.run_id
                or envelope.stage_id != continuation.current_stage_id
                or (
                    envelope.attempt_id not in (None, attempt.id)
                    if pre_attempt
                    else envelope.attempt_id != attempt.id
                )
            ):
                raise StageGateError("G10_LINEAGE_STALE", "G10 repair artifact envelope binding is stale")
            if role == "proposal":
                if payload.get("failure_evidence_checksum") != attempt.failure_evidence_checksum or payload.get("context_pack_checksum") != attempt.context_pack_checksum:
                    raise StageGateError("G10_LINEAGE_STALE", "G10 proposal evidence lineage is stale")
                targets = list(attempt.validation_targets or [])
                normalized = list(dict.fromkeys(target.strip().lower() for target in targets))
                if normalized != targets or normalized != list(package.get("validation_targets") or []) or not normalized or any(target not in SUPPORTED_VALIDATION_TARGETS for target in normalized):
                    raise StageGateError("G10_LINEAGE_STALE", "G10 validation targets are not backend-authorized")
            elif (
                role == "context_pack"
                and attempt.parent_attempt_id is not None
                and not correction_parent
            ):
                revision = payload.get("human_revision")
                if recovery_parent:
                    revision_valid = (
                        revision is None
                        or (
                            isinstance(revision, dict)
                            and bool(str(revision.get("instruction") or "").strip())
                        )
                    )
                    recovered_from = (
                        envelope.input_hashes.get("recovered_from")
                        or envelope.input_hashes.get("parent_context")
                    )
                    if (
                        not revision_valid
                        or not envelope.input_hashes
                        or recovered_from != parent.context_pack_checksum
                    ):
                        raise StageGateError(
                            "REPAIR_PARENT_LINEAGE_INVALID",
                            "G10 recovery context lineage is incomplete or stale",
                        )
                    parent_context_metadata = session.get(
                        ArtifactMetadataModel,
                        "metadata-" + str(parent.context_pack_artifact_id),
                    )
                    try:
                        if (
                            parent_context_metadata is None
                            or parent_context_metadata.run_id != continuation.run_id
                            or parent_context_metadata.stage_id != continuation.current_stage_id
                            or parent_context_metadata.checksum != parent.context_pack_checksum
                        ):
                            raise StageGateError(
                                "REPAIR_PARENT_LINEAGE_INVALID",
                                "G10 recovery parent context binding is invalid",
                            )
                        stored_parent_context = store.read_artifact(
                            continuation.run_id, parent_context_metadata.relative_path
                        )
                        if (
                            stored_parent_context.ref.artifact_id
                            != parent.context_pack_artifact_id
                            or stored_parent_context.ref.checksum
                            != parent.context_pack_checksum
                            or stored_parent_context.envelope is None
                            or stored_parent_context.envelope.run_id
                            != continuation.run_id
                            or stored_parent_context.envelope.stage_id
                            != continuation.current_stage_id
                        ):
                            raise StageGateError(
                                "REPAIR_PARENT_LINEAGE_INVALID",
                                "G10 recovery parent context identity changed",
                            )
                        parent_context_payload = json.loads(stored_parent_context.content)
                    except (ArtifactNotFoundError, ArtifactStoreError, OSError, ValueError, TypeError) as error:
                        raise StageGateError(
                            "REPAIR_PARENT_LINEAGE_INVALID",
                            "G10 recovery parent context cannot be verified",
                        ) from error
                    parent_revision = (
                        parent_context_payload.get("human_revision")
                        if isinstance(parent_context_payload, dict)
                        else None
                    )
                    if (
                        not isinstance(parent_context_payload, dict)
                        or parent_revision != revision
                    ):
                        raise StageGateError(
                            "REPAIR_PARENT_LINEAGE_INVALID",
                            "G10 recovery human revision context is incomplete or stale",
                        )
                else:
                    if (
                        not isinstance(revision, dict)
                        or not str(revision.get("instruction") or "").strip()
                        or revision.get("parent_attempt_id") != attempt.parent_attempt_id
                        or revision.get("parent_proposal_id") != parent.proposal_artifact_id
                        or revision.get("parent_proposal_checksum") != parent.proposal_checksum
                    ):
                        raise StageGateError(
                            "REPAIR_PARENT_LINEAGE_INVALID",
                            "G10 human revision context is incomplete or stale",
                        )
                    try:
                        canonical_revision_proposal = _canonical_revision_payload(
                            revision.get("previous_proposal"), review=False
                        )
                        canonical_parent_proposal = _canonical_revision_payload(
                            parent_proposal_payload, review=False
                        )
                        canonical_revision_review = _canonical_revision_payload(
                            revision.get("reviewer_output"), review=True
                        )
                        canonical_parent_review = _canonical_revision_payload(
                            parent_review_payload, review=True
                        )
                    except ValidationError as error:
                        raise StageGateError(
                            "REPAIR_PARENT_LINEAGE_INVALID",
                            "G10 human revision lineage payload is invalid",
                        ) from error
                    if (
                        canonical_revision_proposal is None
                        or canonical_parent_proposal is None
                        or canonical_revision_proposal != canonical_parent_proposal
                        or canonical_revision_review is None
                        or canonical_parent_review is None
                        or canonical_revision_review != canonical_parent_review
                    ):
                        raise StageGateError(
                            "REPAIR_PARENT_LINEAGE_INVALID",
                            "G10 human revision context is incomplete or stale",
                        )
            elif role == "review":
                decision = payload.get("decision")
                if payload.get("proposal_checksum") != attempt.proposal_checksum:
                    raise StageGateError(
                        "G10_LINEAGE_STALE",
                        "G10 review proposal binding is stale",
                    )
                if decision != "accept" or review_override_required:
                    raise StageGateError(
                        "REPAIR_REVIEW_NOT_ACCEPTED",
                        "Reviewer request_changes must be resolved before G10",
                    )
        for invocation_id, role, artifact_id, checksum in (
            (attempt.proposer_invocation_id, "repair_proposer", attempt.proposal_artifact_id, attempt.proposal_checksum),
            (attempt.reviewer_invocation_id, "repair_reviewer", attempt.review_artifact_id, attempt.review_checksum),
        ):
            invocation = session.get(LlmInvocationModel, invocation_id)
            expected_task = "repair_diagnosis" if role == "repair_proposer" else "repair_review"
            if (
                invocation is None
                or invocation.run_id != continuation.run_id
                or invocation.stage_id != continuation.current_stage_id
                or invocation.role != role
                or invocation.task_type != expected_task
                or invocation.status != "completed"
                or not invocation.request_checksum
                or not invocation.prompt_version
                or not invocation.schema_version
                or (invocation.artifact_checksums or {}).get(artifact_id) != checksum
            ):
                raise StageGateError("G10_LINEAGE_STALE", "G10 invocation lineage is invalid")
            prefix = "proposer" if role == "repair_proposer" else "reviewer"
            if any(
                package.get(f"{prefix}_invocation_{field}") != getattr(invocation, field)
                for field in ("request_checksum", "prompt_version", "schema_version")
            ):
                raise StageGateError("G10_LINEAGE_STALE", "G10 invocation provenance is stale")
        return bool(package.get("review_override_required"))

    @staticmethod
    def _validate_dependency_repair_preflight(
        session: Session,
        continuation: TransformationContinuationModel,
        package_artifact_id: str,
    ) -> None:
        metadata = session.get(ArtifactMetadataModel, "metadata-" + package_artifact_id)
        run = session.get(MigrationRunModel, continuation.run_id)
        if metadata is None or run is None or not run.artifact_root:
            raise StageGateError(
                "REPAIR_DEPENDENCY_PREFLIGHT_FAILED",
                "G10 dependency preflight authority is missing",
            )
        try:
            store = LocalFilesystemArtifactStore(
                Path(str(run.artifact_root)).parent,
                fixed_run_root=Path(str(run.artifact_root)),
            )
            package = json.loads(
                store.read_artifact(continuation.run_id, metadata.relative_path).content
            )
        except (ArtifactNotFoundError, ArtifactStoreError, OSError, TypeError, ValueError) as error:
            raise StageGateError(
                "REPAIR_DEPENDENCY_PREFLIGHT_FAILED",
                "G10 package cannot be read",
            ) from error
        attempt = session.get(RepairAttemptModel, package.get("repair_attempt_id"))
        binding = session.scalar(
            select(StageWorkspaceBindingModel).where(
                StageWorkspaceBindingModel.run_id == continuation.run_id,
                StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                StageWorkspaceBindingModel.active.is_(True),
            )
        )
        stage = session.get(MigrationStageModel, continuation.current_stage_id)
        plan = session.get(MigrationPlanModel, continuation.plan_id)
        if attempt is None or binding is None or stage is None or plan is None:
            raise StageGateError(
                "REPAIR_DEPENDENCY_PREFLIGHT_FAILED",
                "G10 dependency preflight authority is missing",
            )
        proposal_metadata = session.get(
            ArtifactMetadataModel, "metadata-" + str(attempt.proposal_artifact_id)
        )
        try:
            proposal = json.loads(
                store.read_artifact(continuation.run_id, proposal_metadata.relative_path).content
            )
            operations = proposal.get("operations") if isinstance(proposal, dict) else None
            if not any(
                isinstance(operation, dict)
                and (
                    operation.get("path") == "package.json"
                    or str(operation.get("operation") or "").startswith("dependency_")
                )
                for operation in (operations if isinstance(operations, list) else [])
            ):
                return
            DependencyRepairPreflightService().validate(
                workspace=Path(binding.workspace_path),
                proposal=proposal,
                source_family=str(stage.source_version_family),
                target_family=str(stage.target_version_family),
                catalogue_version=(plan.plan or {}).get("catalogue_version"),
            )
        except DependencyRepairPreflightError as error:
            raise StageGateError(error.code, error.message) from error
        except (AttributeError, ArtifactNotFoundError, ArtifactStoreError, OSError, TypeError, ValueError) as error:
            raise StageGateError(
                "REPAIR_DEPENDENCY_PREFLIGHT_FAILED",
                "Dependency proposal evidence is invalid",
            ) from error
