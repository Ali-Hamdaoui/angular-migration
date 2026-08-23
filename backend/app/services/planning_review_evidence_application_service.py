"""Transactional S2-F07-I02 persistence, artifact, event, and API service."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, select

from app.api.planning_review_contracts import (
    G06DecisionApiRequest,
    G06DecisionResponse,
    PlanReviewResponse,
)
from app.artifact_store import ArtifactNotFoundError, LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType, RunStatus, WorkflowEventType
from app.domain.planning import MigrationPlan, StageExecutionPlan
from app.domain.planning_review import (
    G06DecisionRequest,
    G06Gate,
    PlanRevisionRequest,
    PlanningExplanationRequest,
    PlanningPackage,
    PlanningReviewDecision,
    PlanningReviewOutcome,
)
from app.repositories.models import (
    ActivePlanVersionModel,
    ArtifactMetadataModel,
    BuildSystemDecisionModel,
    G04ApprovalModel,
    G05ApprovalModel,
    G06ApprovalModel,
    G06DecisionModel,
    LlmInvocationModel,
    MigrationPlanModel,
    MigrationRunModel,
    PlanningJobModel,
    PlanApprovalStaleModel,
    PlanRevisionModel,
    PlanningReviewModel,
    StageExecutionPlanModel,
    UsageCostRecordModel,
)
from app.repositories.session import session_scope
from app.services.planning_job_service import PLANNING_JOB_NONTERMINAL_STATES
from app.services.transformation_continuation_service import TransformationContinuationService
from app.services.planning_review_application_service import (
    PlanRevisionService,
    PlanningAgentService,
    PlanningReviewApplicationError,
)
from app.state.transition_service import (
    StaleStateVersionError,
    StateTransitionService,
    TransitionError,
    TransitionRequest,
)


G06_APPROVAL_NEXT_RUN_STATUS = RunStatus.WAITING_STAGE_PREPARATION


class PlanningReviewEvidenceError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code, self.message, self.status_code = code, message, status_code
        super().__init__(message)


class PlanningReviewEvidenceApplicationService:
    """Persist immutable S2-F07 evidence and append-only G06 decisions."""

    GATE_VERSION = "g06-v1"

    def __init__(
        self, *, scope=session_scope, planning_agent=None, now_provider=None, artifact_store_factory=None
    ) -> None:
        self._scope = scope
        self._planning_agent = planning_agent
        self._now = now_provider or (lambda: datetime.now(UTC))
        self._artifact_store_factory = artifact_store_factory or self._store_for_run

    def revise(self, run_id: str, payload, actor: str) -> PlanReviewResponse:
        request = PlanRevisionRequest(
            run_id=run_id,
            expected_state_version=payload.expected_state_version,
            idempotency_key=payload.idempotency_key,
            actor=actor,
            plan=payload.plan,
            stage_plan=payload.stage_plan,
            changes=payload.changes,
            artifact_set_checksum=payload.artifact_set_checksum,
            prerequisite_artifacts=tuple(payload.prerequisite_artifacts),
            workspace_fingerprint=payload.workspace_fingerprint,
            correlation_id=payload.correlation_id,
        )
        request_checksum = self._checksum(request.model_dump(mode="json"))
        now = self._now()
        with self._scope() as session:
            run = self._authorized_run(session, run_id, actor)
            existing = session.scalar(
                select(PlanRevisionModel).where(
                    PlanRevisionModel.run_id == run_id, PlanRevisionModel.idempotency_key == request.idempotency_key
                )
            )
            if existing:
                if existing.request_checksum != request_checksum:
                    raise PlanningReviewEvidenceError(
                        "IDEMPOTENCY_PAYLOAD_MISMATCH",
                        "The idempotency key was already used with a different payload.",
                        409,
                    )
                return self._revision_response(session, existing, replay=True)
            self._require_state(run, request.expected_state_version)
            self._validate_prerequisites(session, run, request.prerequisite_artifacts)
            active_plan, active_stage = self._active_plan_pair(session, run_id)
            self._require_active_binding(active_plan, active_stage, request.plan, request.stage_plan)
            revision_service = PlanRevisionService()
            try:
                result = revision_service.revise(request)
            except PlanningReviewApplicationError as error:
                raise PlanningReviewEvidenceError(error.code, error.message, error.status_code) from error
            new_plan = MigrationPlan.model_validate(result.plan)
            new_stage = StageExecutionPlan.model_validate(result.stage_plan)
            artifacts = self._write_revision_artifacts(
                session, run, active_plan, new_plan, new_stage, result.diff.model_dump(mode="json"), now
            )
            transition = self._transition(
                session,
                run,
                request.idempotency_key,
                request.expected_state_version,
                WorkflowEventType.PLAN_REVISION_CREATED,
                actor,
                now,
                {"plan_id": new_plan.plan_id, "plan_version": new_plan.version, "artifact_ids": artifacts[0]},
            )
            stale_ids = self._stale_dependent_approvals(
                session,
                run,
                active_plan.version,
                new_plan.version,
                transition.next_state_version,
                transition.event_sequence,
                actor,
                now,
            )
            self._append_stale_events(
                session, run, request.idempotency_key, stale_ids, actor, now, transition.next_state_version
            )
            plan, stage = self._persist_plan_version(
                session,
                run,
                active_plan,
                active_stage,
                new_plan,
                new_stage,
                request,
                request_checksum,
                artifacts,
                transition,
                now,
            )
            revision = PlanRevisionModel(
                id="plan-revision-" + uuid4().hex[:12],
                run_id=run_id,
                idempotency_key=request.idempotency_key,
                request_checksum=request_checksum,
                actor=actor,
                correlation_id=request.correlation_id,
                previous_plan_id=active_plan.id,
                migration_plan_id=plan.id,
                stage_plan_id=stage.id,
                version=new_plan.version,
                status="revised",
                diff=result.diff.model_dump(mode="json"),
                diff_checksum=result.diff.checksum,
                stale_approval_ids=stale_ids,
                artifact_ids=artifacts[0],
                artifact_checksums=artifacts[1],
                state_version=transition.next_state_version,
                event_sequence=transition.event_sequence,
                created_at=now,
                updated_at=now,
            )
            session.add(revision)
            session.flush()
            return self._revision_response(session, revision)

    def explain(self, run_id: str, payload, actor: str) -> PlanReviewResponse:
        request = PlanningExplanationRequest(
            run_id=run_id,
            expected_state_version=payload.expected_state_version,
            idempotency_key=payload.idempotency_key,
            actor=actor,
            plan=payload.plan,
            stage_plan=payload.stage_plan,
            artifact_set_checksum=payload.artifact_set_checksum,
            prerequisite_artifacts=tuple(payload.prerequisite_artifacts),
            workspace_fingerprint=payload.workspace_fingerprint,
            plan_version=payload.plan_version,
            correlation_id=payload.correlation_id,
        )
        request_checksum = self._checksum(request.model_dump(mode="json"))
        now = self._now()
        with self._scope() as session:
            run = self._authorized_run(session, run_id, actor)
            existing = session.scalar(
                select(PlanningReviewModel).where(
                    PlanningReviewModel.run_id == run_id, PlanningReviewModel.idempotency_key == request.idempotency_key
                )
            )
            if existing:
                if existing.request_checksum != request_checksum:
                    raise PlanningReviewEvidenceError(
                        "IDEMPOTENCY_PAYLOAD_MISMATCH",
                        "The idempotency key was already used with a different payload.",
                        409,
                    )
                return self._planning_response(session, existing, replay=True)
            self._require_state(run, request.expected_state_version)
            self._validate_prerequisites(session, run, request.prerequisite_artifacts)
            active_plan, active_stage = self._active_plan_pair(session, run_id)
            self._require_active_binding(active_plan, active_stage, request.plan, request.stage_plan)
            if active_plan.version != request.plan_version:
                raise PlanningReviewEvidenceError(
                    "STALE_PLAN_VERSION", "The requested plan version is no longer active.", 409
                )
            proposer_invocation = self._start_invocation(
                session, run, request, request_checksum, "phase_proposer", "plan_rationale", now
            )
            row = PlanningReviewModel(
                id="planning-review-" + uuid4().hex[:12],
                run_id=run_id,
                idempotency_key=request.idempotency_key,
                request_checksum=request_checksum,
                actor=actor,
                correlation_id=request.correlation_id,
                migration_plan_id=active_plan.id,
                stage_plan_id=active_stage.id,
                plan_version=active_plan.version,
                artifact_set_checksum=request.artifact_set_checksum,
                status="in_progress",
                package=None,
                proposer_output=None,
                reviewer_output=None,
                revision_count=None,
                outcome=None,
                artifact_ids=[],
                artifact_checksums={},
                proposer_invocation_id=proposer_invocation.id,
                reviewer_invocation_id=None,
                error_code=None,
                state_version=run.state_version,
                event_sequence=0,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()

        try:
            outcome = self._review_outcome(self._agent(run_id).explain(request))
        except PlanningReviewApplicationError as error:
            self._mark_planning_failed(run_id, request.idempotency_key, error.code)
            raise PlanningReviewEvidenceError(error.code, error.message, error.status_code) from error
        except Exception as error:
            self._mark_planning_failed(run_id, request.idempotency_key, "PLANNING_DEPENDENCY_FAILED")
            raise PlanningReviewEvidenceError(
                "PLANNING_DEPENDENCY_FAILED", "The Planning dependency failed; G06 remains unavailable.", 503
            ) from error
        if outcome.package is None:
            return self._complete_nonaccepted_review(run_id, request, request_checksum, outcome)
        return self._complete_explanation(run_id, request, request_checksum, outcome.package, outcome)

    def decide_g06(self, run_id: str, payload: G06DecisionApiRequest, actor: str) -> G06DecisionResponse:
        request = G06DecisionRequest(**payload.model_dump(exclude={"correlation_id"}, mode="json"))
        request_checksum = self._checksum({**request.model_dump(mode="json"), "run_id": run_id, "actor": actor})
        now = self._now()
        with self._scope() as session:
            run = self._authorized_run(session, run_id, actor)
            stored_decision = session.scalar(
                select(G06DecisionModel).where(
                    G06DecisionModel.run_id == run_id,
                    G06DecisionModel.idempotency_key == request.idempotency_key,
                )
            )
            if stored_decision:
                if stored_decision.request_checksum != request_checksum:
                    raise PlanningReviewEvidenceError("IDEMPOTENCY_PAYLOAD_MISMATCH", "The idempotency key was already used with a different payload.", 409)
                return G06DecisionResponse(
                    run_id=stored_decision.run_id,
                    gate_version=stored_decision.gate_version,
                    decision=stored_decision.decision,
                    status=stored_decision.status,
                    accepted=stored_decision.status == "approved",
                    package_checksum=stored_decision.package_checksum,
                    artifact_set_checksum=stored_decision.artifact_set_checksum,
                    plan_checksum=stored_decision.plan_checksum,
                    stage_plan_checksum=stored_decision.stage_plan_checksum,
                    state_version=stored_decision.resulting_state_version,
                    event_sequence=run.state_version,
                    idempotent_replay=True,
                )
            existing = session.scalar(
                select(G06ApprovalModel).where(
                    G06ApprovalModel.run_id == run_id, G06ApprovalModel.idempotency_key == request.idempotency_key
                )
            )
            if existing:
                if existing.stale_reason != request_checksum:
                    raise PlanningReviewEvidenceError(
                        "IDEMPOTENCY_PAYLOAD_MISMATCH",
                        "The idempotency key was already used with a different payload.",
                        409,
                    )
                return self._decision_response(existing, replay=True)
            self._require_state(run, request.expected_state_version)
            gate = session.scalar(
                select(G06ApprovalModel)
                .where(G06ApprovalModel.run_id == run_id, G06ApprovalModel.gate_id == "G06")
                .order_by(G06ApprovalModel.state_version.desc(), G06ApprovalModel.created_at.desc())
            )
            if gate is None or gate.status != "pending":
                raise PlanningReviewEvidenceError("G06_NOT_PENDING", "G06 is not available for a decision.", 409)
            active_plan, active_stage = self._active_plan_pair(session, run_id)
            if (
                gate.plan_version != active_plan.version
                or gate.plan_checksum != active_plan.checksum
                or gate.stage_plan_checksum != active_stage.checksum
            ):
                self._mark_gate_stale(session, run, gate, actor, now, "G06 is not bound to the active plan")
                session.commit()
                raise PlanningReviewEvidenceError("STALE_G06_BINDING", "G06 is not bound to the active plan.", 409)
            if (
                request.gate_version != gate.gate_version
                or request.package_checksum != gate.package_checksum
                or request.artifact_set_checksum != gate.artifact_set_checksum
                or request.plan_checksum != gate.plan_checksum
                or request.stage_plan_checksum != gate.stage_plan_checksum
                or (
                    request.workspace_fingerprint is not None
                    and request.workspace_fingerprint != gate.workspace_fingerprint
                )
            ):
                self._mark_gate_stale(session, run, gate, actor, now, "G06 package binding changed")
                session.commit()
                raise PlanningReviewEvidenceError("STALE_G06_BINDING", "The G06 package binding is stale.", 409)
            self._verify_artifacts(
                session,
                run,
                gate.artifact_ids,
                {item: self._artifact_checksum(session, run, item) for item in gate.artifact_ids},
            )
            review = session.scalar(
                select(PlanningReviewModel)
                .where(
                    PlanningReviewModel.run_id == run_id,
                    PlanningReviewModel.status == "completed",
                    PlanningReviewModel.plan_version == gate.plan_version,
                )
                .order_by(PlanningReviewModel.created_at.desc())
            )
            if review is None or not review.package:
                raise PlanningReviewEvidenceError(
                    "PLANNING_REVIEW_NOT_FOUND", "The accepted Planning review was not found.", 409
                )
            package = PlanningPackage.model_validate(review.package)
            gate_contract = G06Gate(
                run_id=run_id,
                gate_version=gate.gate_version,
                status=gate.status,
                artifact_set_checksum=gate.artifact_set_checksum,
                plan_checksum=gate.plan_checksum,
                stage_plan_checksum=gate.stage_plan_checksum,
                package_checksum=gate.package_checksum,
                workspace_fingerprint=gate.workspace_fingerprint,
                state_version=gate.state_version,
            )
            try:
                result = PlanRevisionService().decide_g06(gate_contract, package, request)
            except PlanningReviewApplicationError as error:
                raise PlanningReviewEvidenceError(error.code, error.message, error.status_code) from error
            event_type = {
                "approve": WorkflowEventType.G06_APPROVED,
                "approve_with_comment": WorkflowEventType.G06_APPROVED,
                "request_modification": WorkflowEventType.G06_MODIFICATION_REQUESTED,
                "reject": WorkflowEventType.G06_REJECTED,
            }[request.decision.value]
            transition = self._transition(
                session,
                run,
                request.idempotency_key,
                request.expected_state_version,
                event_type,
                actor,
                now,
                {
                    "package_checksum": gate.package_checksum,
                    "plan_version": gate.plan_version,
                    "decision": request.decision.value,
                },
                next_run_status=G06_APPROVAL_NEXT_RUN_STATUS if request.decision.value in {"approve", "approve_with_comment"} else RunStatus.WAITING_PLAN_APPROVAL,
                next_run_phase="FEASIBILITY_PLANNING",
                next_phase_status="completed" if request.decision.value in {"approve", "approve_with_comment"} else "waiting_approval",
                next_approval_status="approved" if request.decision.value in {"approve", "approve_with_comment"} else "pending",
            )
            if request.decision.value in {"approve", "approve_with_comment"}:
                active_pointer = session.scalar(select(ActivePlanVersionModel).where(ActivePlanVersionModel.run_id == run_id, ActivePlanVersionModel.scope == "migration"))
                if active_pointer is not None:
                    active_pointer.migration_plan_id = active_plan.id
                    active_pointer.stage_plan_id = active_stage.id
                active_plan.status = "approved_for_execution"
                active_plan.state_version = transition.next_state_version
                active_plan.updated_at = now
                active_stage.status = "approved_for_execution"
                active_stage.state_version = transition.next_state_version
                active_stage.updated_at = now
            gate.status = result.status
            gate.decision = request.decision.value
            gate.actor = actor
            gate.comment = request.comment.strip() if request.comment else None
            gate.stale_reason = request_checksum
            gate.state_version = transition.next_state_version
            gate.event_sequence = transition.event_sequence
            gate.updated_at = now
            if request.decision.value in {"approve", "approve_with_comment"}:
                job = session.scalar(select(PlanningJobModel).where(PlanningJobModel.run_id == run_id, PlanningJobModel.status.in_(PLANNING_JOB_NONTERMINAL_STATES)).order_by(PlanningJobModel.created_at.desc()))
                if job is not None:
                    job.status = "completed"
                    job.current_step = "completed"
                    job.state_version = transition.next_state_version
                    job.completed_at = now
                    job.updated_at = now
            session.add(G06DecisionModel(
                id="g06-decision-" + uuid4().hex[:12],
                run_id=run_id,
                gate_id=gate.gate_id,
                gate_version=gate.gate_version,
                idempotency_key=request.idempotency_key,
                request_checksum=request_checksum,
                decision=request.decision.value,
                status=result.status,
                package_checksum=gate.package_checksum,
                artifact_set_checksum=gate.artifact_set_checksum,
                plan_checksum=gate.plan_checksum,
                stage_plan_checksum=gate.stage_plan_checksum,
                expected_state_version=request.expected_state_version,
                resulting_state_version=transition.next_state_version,
                workspace_fingerprint=gate.workspace_fingerprint,
                comment=gate.comment,
                created_at=now,
            ))
            if result.accepted:
                TransformationContinuationService().ensure_created_in_session(
                    session,
                    run_id=run_id,
                    stage_id=active_stage.stage_id,
                    g06_approval_id=gate.id,
                    plan_id=active_plan.id,
                    plan_checksum=active_plan.checksum,
                    stage_plan_id=active_stage.id,
                    stage_plan_checksum=active_stage.checksum,
                    idempotency_key=f"{request.idempotency_key}:transformer",
                    now=now,
                )
            session.flush()
            return self._decision_response(gate)

    def get(self, run_id: str, actor: str) -> PlanReviewResponse | None:
        with self._scope() as session:
            self._authorized_run(session, run_id, actor)
            review = session.scalar(
                select(PlanningReviewModel)
                .where(PlanningReviewModel.run_id == run_id)
                .order_by(PlanningReviewModel.created_at.desc())
            )
            if review is None:
                revision = session.scalar(
                    select(PlanRevisionModel)
                    .where(PlanRevisionModel.run_id == run_id)
                    .order_by(PlanRevisionModel.created_at.desc())
                )
                if revision:
                    return self._revision_response(session, revision)
                try:
                    plan, stage = self._active_plan_pair(session, run_id)
                except PlanningReviewEvidenceError as error:
                    if error.code == "PLAN_NOT_FOUND":
                        return None
                    raise
                return self._bootstrap_response(plan, stage)
            return self._planning_response(session, review)

    def _complete_explanation(self, run_id, request, request_checksum, package, outcome):
        now = self._now()
        with self._scope() as session:
            run = self._authorized_run(session, run_id, request.actor)
            row = session.scalar(
                select(PlanningReviewModel).where(
                    PlanningReviewModel.run_id == run_id, PlanningReviewModel.idempotency_key == request.idempotency_key
                )
            )
            if row is None:
                raise PlanningReviewEvidenceError(
                    "PLANNING_REVIEW_NOT_FOUND", "The Planning review request was not found.", 404
                )
            invocation = session.get(LlmInvocationModel, row.proposer_invocation_id)
            store = self._store_for_run(run)
            artifacts = self._write_explanation_artifacts(session, run, request, package, now)
            completed = self._transition(
                session,
                run,
                request.idempotency_key + ":completed",
                run.state_version,
                WorkflowEventType.PLANNING_AGENT_COMPLETED,
                request.actor,
                now,
                {"artifact_ids": artifacts[0], "plan_version": request.plan_version},
                next_run_status=RunStatus.WAITING_PLAN_APPROVAL,
                next_run_phase="FEASIBILITY_PLANNING",
                next_phase_status="waiting_approval",
                next_approval_status="pending",
            )
            reviewer_invocation = self._completed_invocation(
                run, request, request_checksum, package, "phase_reviewer", "planning_review", completed, now
            )
            session.add(reviewer_invocation)
            self._record_usage(session, run_id, reviewer_invocation.id, package.reviewer_usage, now)
            if invocation:
                invocation.status = "completed"
                invocation.deployment_alias = package.usage.get("model_deployment_alias", "azure-openai")
                invocation.prompt_version = "planning_agent_v1"
                invocation.schema_version = "planning-schema-registry-v1"
                invocation.pricing_version = package.usage.get("pricing_version", "unknown")
                invocation.artifact_ids = artifacts[0]
                invocation.artifact_checksums = artifacts[1]
                invocation.completed_at = now
                invocation.state_version = completed.next_state_version
                invocation.event_sequence = completed.event_sequence
            self._record_usage(
                session, run_id, invocation.id if invocation else reviewer_invocation.id, package.usage, now
            )
            package_json = package.model_dump(mode="json")
            gate_checksum = artifacts[1][artifacts[0][-1]]
            gate_event = StateTransitionService(session).append_audit_event(
                run_id=run_id,
                idempotency_key=request.idempotency_key + ":g06-created",
                event_type=WorkflowEventType.G06_CREATED,
                actor=request.actor,
                reason="G06 created",
                occurred_at=now,
                payload={"package_checksum": gate_checksum, "artifact_set_checksum": package.artifact_set_checksum},
            )
            gate = G06ApprovalModel(
                id="g06-" + uuid4().hex[:12],
                run_id=run_id,
                gate_id="G06",
                gate_version=self.GATE_VERSION,
                idempotency_key="gate:" + request.idempotency_key,
                actor=request.actor,
                status="pending",
                decision=None,
                package_checksum=gate_checksum,
                artifact_set_checksum=package.artifact_set_checksum,
                plan_checksum=package.plan_checksum,
                stage_plan_checksum=package.stage_plan_checksum,
                plan_version=package.plan_version,
                workspace_fingerprint=package.workspace_fingerprint,
                artifact_ids=artifacts[0],
                comment=None,
                stale_reason=None,
                state_version=gate_event.next_state_version,
                event_sequence=gate_event.event_sequence,
                created_at=now,
                updated_at=now,
            )
            session.add(gate)
            job = session.scalar(select(PlanningJobModel).where(PlanningJobModel.run_id == run_id, PlanningJobModel.status.in_(PLANNING_JOB_NONTERMINAL_STATES)).order_by(PlanningJobModel.created_at.desc()))
            if job is not None:
                job.status = "waiting_g06"
                job.current_step = "waiting_g06"
                job.attempt = 0
                job.state_version = completed.next_state_version
                job.updated_at = now
            row.status = "completed"
            row.package = package_json
            row.proposer_output = outcome.narrative.model_dump(mode="json")
            row.reviewer_output = outcome.reviewer.model_dump(mode="json")
            row.revision_count = outcome.revision_count
            row.outcome = outcome.decision.value
            row.artifact_ids = artifacts[0]
            row.artifact_checksums = artifacts[1]
            row.reviewer_invocation_id = reviewer_invocation.id
            row.state_version = completed.next_state_version
            row.event_sequence = completed.event_sequence
            row.updated_at = now
            session.flush()
            return self._planning_response(session, row)

    def _complete_nonaccepted_review(self, run_id, request, request_checksum, outcome):
        now = self._now()
        event_types = {
            PlanningReviewDecision.REQUEST_REVISION: WorkflowEventType.PLANNING_REVIEW_REVISION_REQUIRED,
            PlanningReviewDecision.REJECT: WorkflowEventType.PLANNING_REVIEW_REJECTED,
            PlanningReviewDecision.INSUFFICIENT_CONTEXT: WorkflowEventType.PLANNING_REVIEW_INSUFFICIENT_CONTEXT,
        }
        review_statuses = {
            PlanningReviewDecision.REQUEST_REVISION: "review_revision_required",
            PlanningReviewDecision.REJECT: "review_rejected",
            PlanningReviewDecision.INSUFFICIENT_CONTEXT: "review_insufficient_context",
        }
        with self._scope() as session:
            run = self._authorized_run(session, run_id, request.actor)
            row = session.scalar(
                select(PlanningReviewModel).where(
                    PlanningReviewModel.run_id == run_id,
                    PlanningReviewModel.idempotency_key == request.idempotency_key,
                )
            )
            if row is None:
                raise PlanningReviewEvidenceError(
                    "PLANNING_REVIEW_NOT_FOUND",
                    "The Planning review request was not found.",
                    404,
                )
            artifacts = self._write_review_outcome_artifacts(session, run, request, outcome, now)
            status = review_statuses[outcome.decision]
            completed = self._transition(
                session,
                run,
                request.idempotency_key + ":completed",
                run.state_version,
                event_types[outcome.decision],
                request.actor,
                now,
                {
                    "artifact_ids": artifacts[0],
                    "plan_version": request.plan_version,
                    "review_outcome": outcome.decision.value,
                },
                next_run_status=RunStatus.WAITING_PLAN_APPROVAL,
                next_run_phase="FEASIBILITY_PLANNING",
                next_phase_status="waiting_approval",
                next_approval_status="pending",
            )
            reviewer_invocation = self._completed_invocation(
                run,
                request,
                request_checksum,
                outcome,
                "phase_reviewer",
                "planning_review",
                completed,
                now,
            )
            reviewer_invocation.artifact_ids = artifacts[0]
            reviewer_invocation.artifact_checksums = artifacts[1]
            session.add(reviewer_invocation)
            self._record_usage(session, run_id, reviewer_invocation.id, outcome.reviewer_usage, now)
            invocation = session.get(LlmInvocationModel, row.proposer_invocation_id)
            if invocation:
                invocation.status = "completed"
                invocation.deployment_alias = outcome.usage.get("model_deployment_alias", "azure-openai")
                invocation.prompt_version = "planning_agent_v1"
                invocation.schema_version = "planning-schema-registry-v1"
                invocation.pricing_version = outcome.usage.get("pricing_version", "unknown")
                invocation.artifact_ids = artifacts[0]
                invocation.artifact_checksums = artifacts[1]
                invocation.completed_at = now
                invocation.state_version = completed.next_state_version
                invocation.event_sequence = completed.event_sequence
                self._record_usage(session, run_id, invocation.id, outcome.usage, now)
            row.status = status
            row.package = outcome.model_dump(mode="json", exclude={"package"})
            row.proposer_output = outcome.narrative.model_dump(mode="json")
            row.reviewer_output = outcome.reviewer.model_dump(mode="json")
            row.revision_count = outcome.revision_count
            row.outcome = outcome.decision.value
            row.artifact_ids = artifacts[0]
            row.artifact_checksums = artifacts[1]
            row.reviewer_invocation_id = reviewer_invocation.id
            row.error_code = None
            row.state_version = completed.next_state_version
            row.event_sequence = completed.event_sequence
            row.updated_at = now
            job = session.scalar(
                select(PlanningJobModel)
                .where(
                    PlanningJobModel.run_id == run_id,
                    PlanningJobModel.status.in_(PLANNING_JOB_NONTERMINAL_STATES),
                )
                .order_by(PlanningJobModel.created_at.desc())
            )
            if job is not None:
                job.status = status
                job.current_step = status
                job.attempt = 0
                job.state_version = completed.next_state_version
                job.retryable = False
                job.updated_at = now
            session.flush()
            return self._planning_response(session, row)

    def _write_revision_artifacts(self, session, run, old_plan, plan, stage, diff, now):
        values = {
            f"03_planning/versions/v{plan.version}/migration-plan.json": plan.model_dump(mode="json"),
            f"stages/{stage.stage_id}/versions/v{plan.version}/stage-execution-plan.json": stage.model_dump(
                mode="json"
            ),
            f"03_planning/versions/v{plan.version}/plan-diff.json": diff,
        }
        return self._write_values(session, run, values, plan.checksum, stage.checksum, "s2-f07-i02", now)

    def _write_explanation_artifacts(self, session, run, request, package, now):
        final = {
            "package": package.model_dump(mode="json"),
            "plan_checksum": package.plan_checksum,
            "stage_plan_checksum": package.stage_plan_checksum,
        }
        values = {
            f"03_planning/versions/v{request.plan_version}/planning-input-manifest.json": {
                "artifact_set_checksum": request.artifact_set_checksum,
                "artifact_ids": [item.artifact_id for item in request.prerequisite_artifacts],
                "checksums": {item.artifact_id: item.checksum for item in request.prerequisite_artifacts},
            },
            f"03_planning/versions/v{request.plan_version}/planning-proposer-output.json": package.narrative.model_dump(
                mode="json"
            ),
            f"03_planning/versions/v{request.plan_version}/planning-reviewer-output.json": package.reviewer.model_dump(
                mode="json"
            ),
            f"03_planning/versions/v{request.plan_version}/planning-explanation.json": final,
            f"03_planning/versions/v{request.plan_version}/planning-usage-cost.json": {
                "proposer": package.usage,
                "reviewer": package.reviewer_usage,
            },
            f"03_planning/versions/v{request.plan_version}/g06-package.json": {
                "gate_id": "G06",
                "gate_version": self.GATE_VERSION,
                "package": final,
                "artifact_set_checksum": package.artifact_set_checksum,
            },
        }
        return self._write_values(
            session, run, values, package.plan_checksum, package.stage_plan_checksum, "s2-f07-i02", now
        )

    def _write_review_outcome_artifacts(self, session, run, request, outcome, now):
        final = {
            "outcome": outcome.decision.value,
            "narrative": outcome.narrative.model_dump(mode="json"),
            "reviewer": outcome.reviewer.model_dump(mode="json"),
            "plan_checksum": outcome.plan_checksum,
            "stage_plan_checksum": outcome.stage_plan_checksum,
        }
        values = {
            f"03_planning/versions/v{request.plan_version}/planning-input-manifest.json": {
                "artifact_set_checksum": request.artifact_set_checksum,
                "artifact_ids": [item.artifact_id for item in request.prerequisite_artifacts],
                "checksums": {item.artifact_id: item.checksum for item in request.prerequisite_artifacts},
            },
            f"03_planning/versions/v{request.plan_version}/planning-proposer-output.json": outcome.narrative.model_dump(mode="json"),
            f"03_planning/versions/v{request.plan_version}/planning-reviewer-output.json": outcome.reviewer.model_dump(mode="json"),
            f"03_planning/versions/v{request.plan_version}/planning-explanation.json": final,
            f"03_planning/versions/v{request.plan_version}/planning-usage-cost.json": {
                "proposer": outcome.usage,
                "reviewer": outcome.reviewer_usage,
            },
        }
        return self._write_values(
            session,
            run,
            values,
            outcome.plan_checksum,
            outcome.stage_plan_checksum,
            "s2-f07-i02",
            now,
        )

    @staticmethod
    def _review_outcome(value):
        if isinstance(value, PlanningReviewOutcome):
            return value
        if isinstance(value, PlanningPackage):
            return PlanningReviewOutcome(
                **value.model_dump(exclude={"review_status"}),
                decision=PlanningReviewDecision.ACCEPT,
                package=value,
            )
        raise TypeError("Planning agent returned an unsupported review result")

    def _write_values(self, session, run, values, plan_checksum, stage_checksum, policy_version, now):
        store = self._store_for_run(run)
        ids, checksums = [], {}
        for path, value in values.items():
            stored = store.write_text_artifact(
                run.id,
                path,
                json.dumps(value, sort_keys=True, indent=2),
                ArtifactType.JSON,
                created_by="planning-review-evidence",
                created_at=now,
                input_hashes={"plan": plan_checksum, "stage_plan": stage_checksum},
                policy_version=policy_version,
            )
            ids.append(stored.ref.artifact_id)
            checksums[stored.ref.artifact_id] = stored.ref.checksum
            session.add(
                ArtifactMetadataModel(
                    id="metadata-" + stored.ref.artifact_id,
                    run_id=run.id,
                    # Artifact-store layout segments such as ``03_planning``
                    # are phase folders, not MigrationStage foreign keys.
                    # Only the canonical ``stages/<stage-id>/...`` namespace
                    # may populate relational stage ownership.
                    stage_id=(
                        stored.ref.stage_id
                        if stored.ref.relative_path.startswith("stages/")
                        else None
                    ),
                    artifact_type=stored.ref.artifact_type.value,
                    relative_path=stored.ref.relative_path,
                    checksum=stored.ref.checksum,
                    created_at=now,
                )
            )
        session.flush()
        return ids, checksums

    def _persist_plan_version(
        self, session, run, old_plan, old_stage, plan, stage, request, request_checksum, artifacts, transition, now
    ):
        record = MigrationPlanModel(
            id=plan.plan_id,
            run_id=run.id,
            idempotency_key=request.idempotency_key,
            request_checksum=request_checksum,
            actor=request.actor,
            correlation_id=request.correlation_id,
            status="revised",
            version=plan.version,
            plan=plan.model_dump(mode="json"),
            checksum=plan.checksum,
            artifact_ids=artifacts[0],
            artifact_checksums=artifacts[1],
            state_version=transition.next_state_version,
            event_sequence=transition.event_sequence,
            created_at=now,
            updated_at=now,
        )
        stage_record = StageExecutionPlanModel(
            id=stage.stage_plan_id,
            run_id=run.id,
            migration_plan_id=record.id,
            stage_id=stage.stage_id,
            idempotency_key=request.idempotency_key,
            request_checksum=request_checksum,
            actor=request.actor,
            correlation_id=request.correlation_id,
            status="revised",
            version=plan.version,
            stage_plan=stage.model_dump(mode="json"),
            checksum=stage.checksum,
            artifact_ids=artifacts[0],
            artifact_checksums=artifacts[1],
            state_version=transition.next_state_version,
            event_sequence=transition.event_sequence,
            created_at=now,
            updated_at=now,
        )
        session.add_all([record, stage_record])
        session.flush()
        session.add(
            BuildSystemDecisionModel(
                id="decision-" + uuid4().hex[:12],
                run_id=run.id,
                stage_plan_id=stage_record.id,
                decision_id=stage.build_system_decision.decision_id,
                decision=stage.build_system_decision.model_dump(mode="json"),
                checksum=stage.build_system_decision.checksum,
                created_at=now,
            )
        )
        migration_pointer = session.scalar(
            select(ActivePlanVersionModel).where(
                ActivePlanVersionModel.run_id == run.id, ActivePlanVersionModel.scope == "migration"
            )
        )
        stage_pointer = session.scalar(
            select(ActivePlanVersionModel).where(
                ActivePlanVersionModel.run_id == run.id, ActivePlanVersionModel.scope == stage.stage_id
            )
        )
        if migration_pointer:
            (
                migration_pointer.migration_plan_id,
                migration_pointer.stage_plan_id,
                migration_pointer.version,
                migration_pointer.state_version,
                migration_pointer.updated_at,
            ) = record.id, None, plan.version, transition.next_state_version, now
        if stage_pointer:
            (
                stage_pointer.migration_plan_id,
                stage_pointer.stage_plan_id,
                stage_pointer.version,
                stage_pointer.state_version,
                stage_pointer.updated_at,
            ) = record.id, stage_record.id, plan.version, transition.next_state_version, now
        return record, stage_record

    def _stale_dependent_approvals(
        self, session, run, old_version, new_version, state_version, event_sequence, actor, now
    ):
        stale_ids = []
        candidates = [
            (
                "G04",
                session.scalar(
                    select(G04ApprovalModel)
                    .where(G04ApprovalModel.run_id == run.id, G04ApprovalModel.status == "approved")
                    .order_by(G04ApprovalModel.created_at.desc())
                ),
            ),
            (
                "G05",
                session.scalar(
                    select(G05ApprovalModel)
                    .where(G05ApprovalModel.run_id == run.id, G05ApprovalModel.status == "approved")
                    .order_by(G05ApprovalModel.created_at.desc())
                ),
            ),
            (
                "G06",
                session.scalar(
                    select(G06ApprovalModel)
                    .where(G06ApprovalModel.run_id == run.id, G06ApprovalModel.status.in_(("pending", "approved", "approved_with_comment")))
                    .order_by(G06ApprovalModel.created_at.desc())
                ),
            ),
        ]
        for gate_id, approval in candidates:
            if approval is None:
                continue
            approval.status = "stale"
            approval.stale_reason = "migration plan revision created"
            approval.updated_at = now
            stale_ids.append(approval.id)
            session.add(
                PlanApprovalStaleModel(
                    id="stale-" + uuid4().hex[:12],
                    run_id=run.id,
                    gate_id=gate_id,
                    approval_id=approval.id,
                    previous_plan_version=old_version,
                    new_plan_version=new_version,
                    reason="migration plan revision created",
                    state_version=state_version,
                    event_sequence=event_sequence,
                    created_at=now,
                )
            )
        return stale_ids

    def _append_stale_events(self, session, run, key, stale_ids, actor, now, state_version):
        for index, approval_id in enumerate(stale_ids):
            StateTransitionService(session).append_audit_event(
                run_id=run.id,
                idempotency_key=f"{key}:stale:{index}",
                event_type=WorkflowEventType.APPROVAL_MARKED_STALE,
                actor=actor,
                reason="approval marked stale by plan revision",
                occurred_at=now,
                payload={"approval_id": approval_id, "state_version": state_version},
            )

    def _start_invocation(self, session, run, request, checksum, role, task_type, now):
        invocation = LlmInvocationModel(
            id="llm-invocation-" + uuid4().hex[:12],
            run_id=run.id,
            stage_id=None,
            idempotency_key=request.idempotency_key + ":" + role,
            request_checksum=checksum,
            input_hashes=[request.artifact_set_checksum],
            correlation_id=request.correlation_id or uuid4().hex,
            actor=request.actor,
            role=role,
            task_type=task_type,
            provider="azure_openai",
            deployment_alias="pending",
            prompt_version="planning_agent_v1",
            schema_version="planning-schema-registry-v1",
            pricing_version="unknown",
            stage="planning",
            redacted_summary=None,
            status="in_progress",
            failure_code=None,
            artifact_ids=[],
            artifact_checksums={},
            state_version=run.state_version,
            event_sequence=0,
            retries=0,
            latency_ms=None,
            started_at=now,
            completed_at=None,
            created_at=now,
        )
        session.add(invocation)
        session.flush()
        return invocation

    def _completed_invocation(self, run, request, checksum, package, role, task_type, transition, now):
        usage = package.reviewer_usage if role == "phase_reviewer" else package.usage
        return LlmInvocationModel(
            id="llm-invocation-" + uuid4().hex[:12],
            run_id=run.id,
            stage_id=None,
            idempotency_key=request.idempotency_key + ":" + role,
            request_checksum=checksum,
            input_hashes=[package.artifact_set_checksum, package.proposer_output_checksum],
            correlation_id=request.correlation_id or uuid4().hex,
            actor=request.actor,
            role=role,
            task_type=task_type,
            provider="azure_openai",
            deployment_alias=usage.get("model_deployment_alias", "azure-openai"),
            prompt_version="planning_reviewer_v1",
            schema_version="planning-schema-registry-v1",
            pricing_version=usage.get("pricing_version", "unknown"),
            stage="planning",
            redacted_summary=None,
            status="completed",
            failure_code=None,
            artifact_ids=[],
            artifact_checksums={},
            state_version=transition.next_state_version,
            event_sequence=transition.event_sequence,
            retries=usage.get("retry_count", 0),
            latency_ms=None,
            started_at=now,
            completed_at=now,
            created_at=now,
        )

    def _record_usage(self, session, run_id, invocation_id, usage, now):
        session.add(
            UsageCostRecordModel(
                id="usage-cost-" + uuid4().hex[:12],
                invocation_id=invocation_id,
                run_id=run_id,
                stage_id=None,
                pricing_version=usage.get("pricing_version", "unknown"),
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                input_price_per_million=usage.get("input_price_per_million", 0),
                output_price_per_million=usage.get("output_price_per_million", 0),
                input_cost_usd=usage.get("input_cost_usd", 0),
                output_cost_usd=usage.get("output_cost_usd", 0),
                total_cost_usd=usage.get("total_cost_usd", 0),
                created_at=now,
            )
        )

    def _mark_planning_failed(self, run_id, idempotency_key, code):
        with self._scope() as session:
            row = session.scalar(
                select(PlanningReviewModel).where(
                    PlanningReviewModel.run_id == run_id, PlanningReviewModel.idempotency_key == idempotency_key
                )
            )
            if row:
                row.status, row.error_code, row.updated_at = "failed", code, self._now()
                if row.proposer_invocation_id:
                    invocation = session.get(LlmInvocationModel, row.proposer_invocation_id)
                    if invocation:
                        invocation.status, invocation.failure_code, invocation.completed_at = (
                            "failed",
                            code,
                            self._now(),
                        )

    def _active_plan_pair(self, session, run_id):
        pointer = session.scalar(
            select(ActivePlanVersionModel).where(
                ActivePlanVersionModel.run_id == run_id, ActivePlanVersionModel.scope == "migration"
            )
        )
        if pointer is None:
            raise PlanningReviewEvidenceError("PLAN_NOT_FOUND", "An active migration plan was not found.", 404)
        plan = session.get(MigrationPlanModel, pointer.migration_plan_id)
        stage_pointer = session.scalar(
            select(ActivePlanVersionModel).where(
                ActivePlanVersionModel.run_id == run_id,
                ActivePlanVersionModel.scope != "migration",
                ActivePlanVersionModel.version == pointer.version,
            )
        )
        stage = (
            session.get(StageExecutionPlanModel, stage_pointer.stage_plan_id)
            if stage_pointer
            else session.scalar(
                select(StageExecutionPlanModel)
                .where(StageExecutionPlanModel.migration_plan_id == plan.id)
                .order_by(StageExecutionPlanModel.version.desc())
            )
        )
        if plan is None or stage is None:
            raise PlanningReviewEvidenceError("PLAN_NOT_FOUND", "The active plan evidence is incomplete.", 404)
        return plan, stage

    def _require_active_binding(self, plan, stage, supplied_plan, supplied_stage):
        if (
            supplied_plan.get("checksum") != plan.checksum
            or supplied_stage.get("checksum") != stage.checksum
            or supplied_stage.get("plan_version") != plan.version
        ):
            raise PlanningReviewEvidenceError(
                "STALE_PLAN_BINDING", "The submitted plan is not the active checksum-bound version.", 409
            )

    def _validate_prerequisites(self, session, run, artifacts):
        store = self._store_for_run(run)
        for artifact in artifacts:
            metadata = session.get(ArtifactMetadataModel, "metadata-" + artifact.artifact_id)
            if metadata is None or metadata.run_id != run.id or metadata.checksum != artifact.checksum:
                raise PlanningReviewEvidenceError(
                    "PREREQUISITE_ARTIFACT_CHECKSUM_MISMATCH",
                    "A prerequisite artifact is missing or its checksum does not match.",
                    409,
                )
            try:
                self._verify_stored(store, artifact.artifact_id, artifact.checksum)
            except (ArtifactNotFoundError, OSError, ValueError) as error:
                raise PlanningReviewEvidenceError(
                    "PREREQUISITE_ARTIFACT_UNAVAILABLE", "A prerequisite artifact is unavailable.", 409
                ) from error

    def _verify_artifacts(self, session, run, artifact_ids, checksums):
        store = self._store_for_run(run)
        for artifact_id in artifact_ids:
            metadata = session.get(ArtifactMetadataModel, "metadata-" + artifact_id)
            checksum = checksums.get(artifact_id)
            if metadata is None or metadata.run_id != run.id or metadata.checksum != checksum:
                raise PlanningReviewEvidenceError(
                    "G06_PACKAGE_INTEGRITY_FAILED", "A G06 evidence artifact is missing or changed.", 409
                )
            try:
                self._verify_stored(store, artifact_id, checksum)
            except (ArtifactNotFoundError, OSError, ValueError) as error:
                raise PlanningReviewEvidenceError(
                    "G06_PACKAGE_INTEGRITY_FAILED", "A G06 evidence artifact is missing or changed.", 409
                ) from error

    def _artifact_checksum(self, session, run, artifact_id):
        metadata = session.get(ArtifactMetadataModel, "metadata-" + artifact_id)
        if metadata is None or metadata.run_id != run.id:
            raise PlanningReviewEvidenceError(
                "G06_PACKAGE_INTEGRITY_FAILED", "A G06 evidence artifact is unavailable.", 409
            )
        return metadata.checksum

    @staticmethod
    def _verify_stored(store, artifact_id, checksum):
        stored = store.read_artifact_by_id(artifact_id)
        actual = "sha256:" + hashlib.sha256(stored.content.encode("utf-8")).hexdigest()
        if stored.ref.checksum != checksum or actual != checksum:
            raise ValueError("artifact checksum mismatch")

    def _revision_response(self, session, revision, replay=False):
        plan = session.get(MigrationPlanModel, revision.migration_plan_id)
        stage = session.get(StageExecutionPlanModel, revision.stage_plan_id)
        return PlanReviewResponse(
            run_id=revision.run_id,
            status=revision.status,
            plan=plan.plan if plan else None,
            stage_plan=stage.stage_plan if stage else None,
            plan_checksum=plan.checksum if plan else None,
            stage_plan_checksum=stage.checksum if stage else None,
            diff=revision.diff,
            artifact_ids=revision.artifact_ids,
            artifact_checksums=revision.artifact_checksums,
            artifact_links={item: f"/api/v1/artifacts/{item}" for item in revision.artifact_ids},
            state_version=revision.state_version,
            event_sequence=revision.event_sequence,
            idempotent_replay=replay,
        )

    def _planning_response(self, session, row, replay=False):
        active_plan, active_stage = self._active_plan_pair(session, row.run_id)
        gate = session.scalar(
            select(G06ApprovalModel)
            .where(G06ApprovalModel.run_id == row.run_id, G06ApprovalModel.gate_id == "G06")
            .order_by(G06ApprovalModel.state_version.desc(), G06ApprovalModel.created_at.desc())
        )
        current_checksums = dict(row.artifact_checksums or {})
        current_checksums.update(active_plan.artifact_checksums or {})
        current_checksums.update(active_stage.artifact_checksums or {})
        if gate:
            for artifact_id in gate.artifact_ids or []:
                current_checksums[artifact_id] = self._artifact_checksum(session, session.get(MigrationRunModel, row.run_id), artifact_id)
            self._verify_artifacts(session, session.get(MigrationRunModel, row.run_id), gate.artifact_ids or [], current_checksums)
        aggregate = self._aggregate_artifact_checksum(current_checksums)
        return PlanReviewResponse(
            run_id=row.run_id,
            status=row.status,
            package=row.package,
            plan=active_plan.plan,
            stage_plan=active_stage.stage_plan,
            plan_checksum=active_plan.checksum,
            stage_plan_checksum=active_stage.checksum,
            artifact_ids=sorted(current_checksums),
            artifact_checksums=current_checksums,
            artifact_links={item: f"/api/v1/artifacts/{item}" for item in current_checksums},
            gate_version=gate.gate_version if gate else self.GATE_VERSION,
            gate_status=gate.status if gate else "not_created",
            gate_decision=gate.decision if gate else None,
            package_checksum=gate.package_checksum if gate else None,
            artifact_set_checksum=gate.artifact_set_checksum if gate else None,
            computed_artifact_set_checksum=aggregate,
            state_version=row.state_version,
            event_sequence=row.event_sequence,
            idempotent_replay=replay,
        )

    def _bootstrap_response(self, plan, stage):
        checksums = dict(plan.artifact_checksums or {})
        checksums.update(stage.artifact_checksums or {})
        artifact_ids = sorted(checksums)
        return PlanReviewResponse(
            run_id=plan.run_id,
            status="not_started",
            plan=plan.plan,
            stage_plan=stage.stage_plan,
            plan_checksum=plan.checksum,
            stage_plan_checksum=stage.checksum,
            artifact_ids=artifact_ids,
            artifact_checksums=checksums,
            artifact_links={item: f"/api/v1/artifacts/{item}" for item in artifact_ids},
            gate_version=self.GATE_VERSION,
            gate_status="not_created",
            computed_artifact_set_checksum=self._aggregate_artifact_checksum(checksums),
            state_version=max(plan.state_version, stage.state_version),
            event_sequence=max(plan.event_sequence, stage.event_sequence),
        )

    @staticmethod
    def _aggregate_artifact_checksum(checksums: dict[str, str]) -> str:
        """Canonical checksum of the complete current artifact/checksum map."""
        return "sha256:" + hashlib.sha256(
            json.dumps(dict(sorted(checksums.items())), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _decision_response(row, replay=False):
        from app.domain.planning_review import G06Decision

        return G06DecisionResponse(
            run_id=row.run_id,
            gate_version=row.gate_version,
            decision=G06Decision(row.decision),
            status=row.status,
            accepted=row.status == "approved",
            package_checksum=row.package_checksum,
            artifact_set_checksum=row.artifact_set_checksum,
            plan_checksum=row.plan_checksum,
            stage_plan_checksum=row.stage_plan_checksum,
            state_version=row.state_version,
            event_sequence=row.event_sequence,
            idempotent_replay=replay,
        )

    def _mark_gate_stale(self, session, run, gate, actor, now, reason):
        transition = StateTransitionService(session).append_audit_event(
            run_id=run.id,
            idempotency_key="stale:" + gate.id,
            event_type=WorkflowEventType.G06_STALE,
            actor=actor,
            reason=reason,
            occurred_at=now,
            payload={"gate_version": gate.gate_version},
        )
        gate.status = "stale"
        gate.stale_reason = reason
        gate.state_version = transition.next_state_version
        gate.event_sequence = transition.event_sequence
        gate.updated_at = now

    def _transition(self, session, run, key, expected, event_type, actor, now, payload, **state_changes):
        try:
            return StateTransitionService(session).apply_transition(
                TransitionRequest(
                    run_id=run.id,
                    expected_state_version=expected,
                    idempotency_key=key,
                    event_type=event_type,
                    actor=actor,
                    reason=event_type.value.lower(),
                    occurred_at=now,
                    payload=payload,
                    **state_changes,
                )
            )
        except StaleStateVersionError as error:
            raise PlanningReviewEvidenceError("STALE_STATE_VERSION", "The run state version is stale.", 409) from error
        except TransitionError as error:
            raise PlanningReviewEvidenceError(
                "ILLEGAL_STATE_TRANSITION", "The requested workflow transition is not legal.", 409
            ) from error

    def _authorized_run(self, session, run_id, actor):
        run = session.get(MigrationRunModel, run_id)
        if run is None:
            raise PlanningReviewEvidenceError("RUN_NOT_FOUND", "Migration run does not exist.", 404)
        if run.actor and run.actor != actor:
            raise PlanningReviewEvidenceError(
                "RUN_NOT_AUTHORIZED", "Authenticated actor is not authorized for this run.", 403
            )
        return run

    @staticmethod
    def _require_state(run, expected):
        if run.state_version != expected:
            raise PlanningReviewEvidenceError("STALE_STATE_VERSION", "The run state version is stale.", 409)

    def _agent(self, run_id):
        if self._planning_agent is not None:
            return self._planning_agent
        from app.core.config import get_settings
        from app.llm_gateway.azure_gateway import AzureOpenAILLMGateway, PromptSchemaRegistry
        from app.services.planning_review_application_service import PlanningGatewayNarrative, PlanningGatewayReview

        registry = PromptSchemaRegistry(version=get_settings().llm_schema_registry_version)
        registry.register("planning_narrative_v1", PlanningGatewayNarrative)
        registry.register("planning_review_v1", PlanningGatewayReview)
        return PlanningAgentService(gateway=AzureOpenAILLMGateway(settings=get_settings(), registry=registry))

    @staticmethod
    def _checksum(value):
        return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _store_for_run(run):
        root = Path(run.artifact_root)
        return LocalFilesystemArtifactStore(root, fixed_run_root=root)
