"""Application service for repair proposals and the G10 human-apply gate.

Handles creation, retrieval, and G10 decision lifecycle for repair proposals.
Does NOT implement patch application — that is owned by a downstream issue.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from app.domain.contracts import WorkflowEventType
from app.domain.repair_proposal import (
    G10ApprovalPackage,
    G10ApprovalPackageBuilder,
    G10ApprovalService,
    G10Decision,
    G10DecisionRequest,
    G10DecisionResult,
    G10Status,
    ProposalStatus,
    RepairProposal,
)
from app.repositories.models import MigrationRunModel, RepairProposalModel
from app.repositories.session import session_scope
from app.state.transition_service import StateTransitionService, TransitionRequest


class RepairProposalApplicationError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class RepairProposalService:
    """Persist, retrieve, and manage repair proposals with G10 gate binding."""

    GATE_VERSION = "g10-v1"

    def __init__(self, *, session_scope_factory=session_scope, now_provider=None) -> None:
        self._scope = session_scope_factory
        self._now = now_provider or (lambda: datetime.now(UTC))

    def get(self, run_id: str, proposal_id: str) -> RepairProposalModel | None:
        """Retrieve a persisted repair proposal by run + proposal ID."""
        with self._scope() as session:
            record = session.scalar(
                select(RepairProposalModel)
                .where(RepairProposalModel.run_id == run_id)
                .where(RepairProposalModel.proposal_id == proposal_id)
                .order_by(RepairProposalModel.created_at.desc())
            )
            return record

    def persist(
        self,
        run_id: str,
        proposal: RepairProposal,
        *,
        actor: str,
        idempotency_key: str,
        repair_attempt_id: str,
        lineage_checksum: str,
        expected_state_version: int,
    ) -> RepairProposalModel:
        """Persist an accepted/reviewed repair proposal (idempotent).

        Creates the proposal record and transitions the run state.
        Returns the persisted model.
        """
        now = self._now()
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise RepairProposalApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)

            # Idempotency check
            existing = session.scalar(
                select(RepairProposalModel)
                .where(RepairProposalModel.run_id == run_id)
                .where(RepairProposalModel.proposal_id == proposal.proposal_id)
            )
            if existing is not None:
                return existing

            if run.state_version != expected_state_version:
                raise RepairProposalApplicationError("STALE_STATE_VERSION", "The run state version is stale.", status_code=409)

            # Create the G10 gate binding checksums
            g10_package = G10ApprovalPackageBuilder().build(
                proposal_id=proposal.proposal_id,
                review_id=f"review-{proposal.proposal_id}",
                lineage_checksum=lineage_checksum,
                diff_checksum=proposal.diff_checksum,
                workspace_fingerprint=proposal.workspace_fingerprint,
            )

            # Emit REPAIR_PROPOSAL_READY event
            transition = StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run.id,
                expected_state_version=run.state_version,
                idempotency_key=f"{idempotency_key}:ready",
                event_type=WorkflowEventType.REPAIR_PROPOSAL_READY,
                actor=actor,
                reason="Repair proposal ready for G10 human review",
                occurred_at=now,
                payload={
                    "proposal_id": proposal.proposal_id,
                    "diff_checksum": proposal.diff_checksum,
                    "workspace_fingerprint": proposal.workspace_fingerprint,
                    "lineage_checksum": lineage_checksum,
                    "g10_approval_id": g10_package.approval_id,
                },
            ))

            record = RepairProposalModel(
                id=f"rp-{uuid4().hex[:12]}",
                run_id=run.id,
                repair_attempt_id=repair_attempt_id,
                proposal_id=proposal.proposal_id,
                status=proposal.status.value,
                diff_checksum=proposal.diff_checksum,
                workspace_fingerprint=proposal.workspace_fingerprint,
                lineage_checksum=lineage_checksum,
                g10_status=G10Status.PENDING.value,
                idempotency_key=idempotency_key,
                actor=actor,
                state_version=transition.next_state_version,
                event_sequence=transition.event_sequence,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            session.flush()
            return record


class G10DecisionService:
    """Handle the G10 human apply/reject gate lifecycle."""

    GATE_ID = "G10"
    GATE_VERSION = "g10-v1"

    def __init__(self, *, session_scope_factory=session_scope, now_provider=None) -> None:
        self._scope = session_scope_factory
        self._now = now_provider or (lambda: datetime.now(UTC))
        self._domain_service = G10ApprovalService()

    def decide(
        self,
        run_id: str,
        request: G10DecisionRequest,
    ) -> G10DecisionResult:
        """Process a G10 human decision on a repair proposal.

        Validates state version, checksum binding, lineage integrity,
        and idempotency before accepting the decision.
        """
        now = self._now()
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise RepairProposalApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)

            # Idempotency — check if this exact decision was already applied
            existing_event = session.scalar(
                select(RepairProposalModel)
                .where(RepairProposalModel.run_id == run_id)
                .where(RepairProposalModel.idempotency_key == request.idempotency_key)
            )
            if existing_event is not None and existing_event.g10_decision is not None:
                # Replay the original result
                return G10DecisionResult(
                    run_id=run_id,
                    proposal_id=request.proposal_id,
                    decision=G10Decision(existing_event.g10_decision),
                    accepted=existing_event.g10_status in {G10Status.APPROVED.value, G10Status.APPROVED_WITH_COMMENT.value},
                    state_version=existing_event.state_version,
                    gate_version=self.GATE_VERSION,
                )

            if run.state_version != request.expected_state_version:
                raise RepairProposalApplicationError("STALE_STATE_VERSION", "The run state version is stale.", status_code=409)

            # Retrieve the proposal record
            record = session.scalar(
                select(RepairProposalModel)
                .where(RepairProposalModel.run_id == run_id)
                .where(RepairProposalModel.proposal_id == request.proposal_id)
                .order_by(RepairProposalModel.created_at.desc())
            )
            if record is None:
                raise RepairProposalApplicationError("PROPOSAL_NOT_FOUND", "Repair proposal not found.", status_code=404)

            # Check for stale state — reject if already decided
            if record.g10_status != G10Status.PENDING.value:
                raise RepairProposalApplicationError(
                    "G10_ALREADY_DECIDED",
                    f"G10 gate already has status: {record.g10_status}",
                    status_code=409,
                )

            # Build a G10ApprovalPackage from the record for domain validation
            package = G10ApprovalPackage(
                proposal_id=record.proposal_id,
                review_id=f"review-{record.proposal_id}",
                lineage_checksum=record.lineage_checksum,
                diff_checksum=record.diff_checksum,
                workspace_fingerprint=record.workspace_fingerprint,
                g10_status=G10Status(record.g10_status),
            )

            # Domain validation
            result = self._domain_service.decide(package, request, state_version=run.state_version)

            # Determine the event type based on decision outcome
            if result.stale:
                event_type = WorkflowEventType.G10_STALE
            elif result.decision in {G10Decision.APPROVE, G10Decision.APPROVE_WITH_COMMENT}:
                event_type = WorkflowEventType.G10_APPROVED
            else:
                event_type = WorkflowEventType.G10_REJECTED

            # Emit transition
            transition = StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run.id,
                expected_state_version=run.state_version,
                idempotency_key=request.idempotency_key,
                event_type=event_type,
                actor=request.actor,
                reason=result.reason or "G10 decision recorded",
                occurred_at=now,
                payload={
                    "proposal_id": request.proposal_id,
                    "decision": result.decision.value,
                    "accepted": result.accepted,
                    "diff_checksum": request.diff_checksum,
                    "workspace_fingerprint": request.workspace_fingerprint,
                    "lineage_checksum": request.lineage_checksum,
                },
            ))

            # Update the proposal record with G10 decision
            record.g10_status = G10Status.STALE.value if result.stale else result.decision.value
            record.g10_decision = result.decision.value
            record.g10_approval_id = package.approval_id
            record.g10_decided_at = now
            record.g10_actor = request.actor
            record.g10_rationale = request.rationale
            record.state_version = transition.next_state_version
            record.event_sequence = transition.event_sequence
            record.updated_at = now
            session.flush()

            return G10DecisionResult(
                run_id=run_id,
                proposal_id=request.proposal_id,
                decision=result.decision,
                accepted=result.accepted,
                state_version=transition.next_state_version,
                gate_version=self.GATE_VERSION,
                stale=result.stale,
                reason=result.reason,
            )
