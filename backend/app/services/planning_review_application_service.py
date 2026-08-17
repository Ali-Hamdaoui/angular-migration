"""Application contracts for S2-F07-I01 Planning review and G06."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.domain.command import ANGULAR_UPDATE_V4_RENDERER
from app.domain.contracts import AgentKind
from app.domain.planning import (
    APPROVED_BUILDERS,
    APPROVED_CATALOGUE_VERSIONS,
    APPROVED_RECOVERY_POLICIES,
    APPROVED_REPAIR_POLICIES,
    APPROVED_VALIDATION_POLICIES,
    BuildSystemDecision,
    MigrationPlan,
    StageExecutionPlan,
    checksum_model,
)
from app.domain.planning_review import (
    G06Decision,
    G06DecisionRequest,
    G06DecisionResult,
    G06Gate,
    PlanRevisionRequest,
    PlanRevisionResult,
    PlanVersionDiff,
    PlanningExplanationRequest,
    PlanningNarrative,
    PlanningPackage,
    PlanningReview,
    PlanningReviewDecision,
    PlanningReviewOutcome,
)
from app.llm_gateway import AzureGatewayError, LlmContextSegment, LlmRequest, LlmRole, LlmTaskType, PromptSchemaRegistry


class PlanningReviewApplicationError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422, details: dict[str, Any] | None = None) -> None:
        self.code, self.message, self.status_code = code, message, status_code
        self.details = details or {}
        super().__init__(message)


def _safe_gateway_failure_details(error: Exception, *, stage: str) -> dict[str, Any]:
    """Return bounded gateway metadata without persisting provider payloads."""
    if isinstance(error, AzureGatewayError):
        code = getattr(error.code, "value", error.code)
        return {
            "failure_code": code,
            "failure_stage": error.failure_stage or stage,
            "failure_subtype": error.failure_subtype or "LLM_GATEWAY_FAILED",
            "retryable": bool(error.retryable),
            "provider_http_status": error.provider_status,
            "provider_error_code": error.provider_code,
            "provider_request_id": error.provider_request_id,
            "transport_started": bool(error.transport_started),
        }
    return {
        "failure_code": "PLANNING_GATEWAY_ERROR",
        "failure_stage": stage,
        "failure_subtype": "UNCLASSIFIED_GATEWAY_FAILURE",
        "retryable": False,
        "provider_http_status": None,
        "provider_error_code": None,
        "provider_request_id": None,
        "transport_started": False,
    }


class PlanningGatewayNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=12000)
    rationale: list[str] = Field(default_factory=list, max_length=64)
    risks: list[str] = Field(default_factory=list, max_length=64)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=64)
    deterministic_plan_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class PlanningGatewayReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: PlanningReviewDecision
    notes: list[str] = Field(default_factory=list, max_length=64)
    policy_concerns: list[str] = Field(default_factory=list, max_length=64)
    confidence: str = Field(min_length=1, max_length=64)
    deterministic_plan_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    proposer_output_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class ApprovalStaleMarker(Protocol):
    def __call__(self, run_id: str, plan_version: int, reason: str) -> tuple[str, ...]: ...


class PlanningAgentService:
    schema_name = "planning_narrative_v1"
    reviewer_schema_name = "planning_review_v1"
    prompt_name = "planning_agent_v1"
    reviewer_prompt_name = "planning_reviewer_v1"

    def __init__(self, *, gateway: Any, max_context_bytes: int = 200_000, max_revisions: int = 1) -> None:
        self.gateway = gateway
        self.max_context_bytes = max_context_bytes
        self.max_revisions = max_revisions
        self.registry = PromptSchemaRegistry(version="planning-schema-registry-v1")
        self.registry.register(self.schema_name, PlanningGatewayNarrative)
        self.registry.register(self.reviewer_schema_name, PlanningGatewayReview)

    def explain(self, request: PlanningExplanationRequest) -> PlanningReviewOutcome:
        self._validate_plan_pair(request.plan, request.stage_plan, request.run_id, request.plan_version)
        deterministic_checksum = _deterministic_plan_checksum(request.plan, request.stage_plan)
        context = [
            LlmContextSegment(
                segment_id="migration-plan",
                label="deterministic migration plan",
                content=_json(request.plan),
                untrusted=False,
            ),
            LlmContextSegment(
                segment_id="stage-plan",
                label="deterministic stage plan",
                content=_json(request.stage_plan),
                untrusted=False,
            ),
            LlmContextSegment(
                segment_id="deterministic-plan-binding",
                label="deterministic plan checksum binding",
                content=_json({"deterministic_plan_checksum": deterministic_checksum}),
                untrusted=False,
            ),
        ]
        if sum(len(item.content.encode()) for item in context) > self.max_context_bytes:
            raise PlanningReviewApplicationError(
                "PLANNING_CONTEXT_TOO_LARGE", "Planning input exceeds the configured context limit.", 422
            )
        response, narrative = self._propose(request, context, deterministic_checksum, 0)
        proposer_checksum = _checksum(narrative.model_dump(mode="json"))
        reviewer_response, review = self._review(
            request, context, deterministic_checksum, narrative, proposer_checksum, 0
        )
        revision_count = 0
        while review.decision is PlanningReviewDecision.REQUEST_REVISION and revision_count < self.max_revisions:
            revision_count += 1
            response, narrative = self._propose(request, context, deterministic_checksum, revision_count, review.notes)
            proposer_checksum = _checksum(narrative.model_dump(mode="json"))
            reviewer_response, review = self._review(
                request, context, deterministic_checksum, narrative, proposer_checksum, revision_count
            )
        values = dict(
            run_id=request.run_id,
            plan_version=request.plan_version,
            artifact_set_checksum=request.artifact_set_checksum,
            deterministic_plan_checksum=deterministic_checksum,
            plan_checksum=request.plan["checksum"],
            stage_plan_checksum=request.stage_plan["checksum"],
            narrative=narrative,
            proposer_output_checksum=proposer_checksum,
            reviewer=review,
            reviewer_output_checksum=_checksum(review.model_dump(mode="json")),
            usage=response.usage.model_dump(mode="json"),
            reviewer_usage=reviewer_response.usage.model_dump(mode="json"),
            revision_count=revision_count,
            workspace_fingerprint=request.workspace_fingerprint,
        )
        package = PlanningPackage(**values) if review.decision is PlanningReviewDecision.ACCEPT else None
        return PlanningReviewOutcome(
            **values,
            decision=review.decision,
            package=package,
        )

    @staticmethod
    def _validate_plan_pair(
        plan_value: dict[str, Any], stage_value: dict[str, Any], run_id: str, plan_version: int
    ) -> None:
        try:
            plan = MigrationPlan.model_validate(plan_value)
            stage = StageExecutionPlan.model_validate(stage_value)
        except Exception as exc:
            raise PlanningReviewApplicationError(
                "INVALID_PLAN_CONTRACT", "The current deterministic plan is invalid.", 422
            ) from exc
        if plan.run_id != run_id or plan.version != plan_version or stage.plan_version != plan.version:
            raise PlanningReviewApplicationError(
                "PLAN_BINDING_MISMATCH", "The migration and stage plans are not consistently bound.", 409
            )

    def _propose(self, request, context, checksum, revision, notes=None):
        if notes:
            context = [
                *context,
                LlmContextSegment(
                    segment_id=f"review-notes-{revision}",
                    label="planning reviewer notes",
                    content=_json(notes),
                    untrusted=False,
                ),
            ]
        try:
            response = self.gateway.complete(
                LlmRequest(
                    request_id=f"planning-{request.idempotency_key}-proposer-{revision}",
                    run_id=request.run_id,
                    agent_kind=AgentKind.PLANNING,
                    task_type=LlmTaskType.PLAN_RATIONALE,
                    role=LlmRole.PHASE_PROPOSER,
                    prompt_name=self.prompt_name,
                    system_policy="Explain only the deterministic migration plan. Copy deterministic_plan_checksum exactly from the trusted deterministic-plan-binding context. Never calculate or change checksum bindings, commands, versions, approvals, or executable truth.",
                    context=context,
                    response_schema=self.schema_name,
                    max_output_tokens=2048,
                )
            )
            narrative = PlanningNarrative.model_validate(
                self.registry.validate(self.schema_name, response.structured_output)
            )
        except Exception as exc:
            raise PlanningReviewApplicationError(
                "PLANNING_PROPOSER_FAILED", "The Planning proposer failed; G06 remains unavailable.", 503,
                _safe_gateway_failure_details(exc, stage="phase_proposer"),
            ) from exc
        if narrative.deterministic_plan_checksum != checksum:
            raise PlanningReviewApplicationError(
                "PLANNING_INPUT_CHECKSUM_MISMATCH", "Planning output is not bound to the deterministic plan.", 502
            )
        return response, narrative

    def _review(self, request, context, checksum, narrative, proposer_checksum, revision):
        review_context = [
            *context,
            LlmContextSegment(
                segment_id=f"proposer-output-{revision}",
                label="planning proposer output",
                content=_json(narrative.model_dump(mode="json")),
                untrusted=True,
            ),
            LlmContextSegment(
                segment_id="proposer-output-binding",
                label="planning proposer checksum binding",
                content=_json({"proposer_output_checksum": proposer_checksum}),
                untrusted=False,
            ),
        ]
        try:
            response = self.gateway.complete(
                LlmRequest(
                    request_id=f"planning-{request.idempotency_key}-reviewer-{revision}",
                    run_id=request.run_id,
                    agent_kind=AgentKind.PLANNING,
                    task_type=LlmTaskType.PLANNING_REVIEW,
                    role=LlmRole.PHASE_REVIEWER,
                    prompt_name=self.reviewer_prompt_name,
                    system_policy=(
                        "Review only the bounded Planning explanation. Accept when the explanation accurately "
                        "describes the deterministic plan, makes no unsupported claim, and explicitly identifies "
                        "its material risks or unknowns. Do not request unavailable external operational proof; "
                        "treat registry availability, test coverage, human workflow, and recovery exercises as "
                        "documented risks or later governed validation when the deterministic plan does not claim "
                        "they are already proven. Request revision only for an in-scope inaccuracy, omission, or "
                        "contradiction in the explanation. Copy deterministic_plan_checksum and "
                        "proposer_output_checksum exactly from their trusted binding contexts. Never calculate or "
                        "change checksum bindings, commands, versions, patches, or approvals."
                    ),
                    context=review_context,
                    response_schema=self.reviewer_schema_name,
                    max_output_tokens=1024,
                )
            )
            review = PlanningReview.model_validate(
                self.registry.validate(self.reviewer_schema_name, response.structured_output)
            )
        except Exception as exc:
            raise PlanningReviewApplicationError(
                "PLANNING_REVIEW_FAILED",
                "The Planning reviewer failed or returned invalid output; G06 remains unavailable.",
                503,
                _safe_gateway_failure_details(exc, stage="phase_reviewer"),
            ) from exc
        if review.deterministic_plan_checksum != checksum or review.proposer_output_checksum != proposer_checksum:
            raise PlanningReviewApplicationError(
                "PLANNING_REVIEW_CHECKSUM_MISMATCH",
                "The Planning review is not bound to the current deterministic plan and proposer output.",
                502,
            )
        return response, review


class PlanRevisionService:
    gate_version = "g06-v1"

    def __init__(
        self,
        *,
        state_version_reader: Callable[[str], int] | None = None,
        stale_approval_marker: ApprovalStaleMarker | None = None,
    ) -> None:
        self._read_state_version = state_version_reader
        self._mark_stale = stale_approval_marker or (lambda _run_id, _version, _reason: ())
        self._revisions: dict[tuple[str, str], tuple[str, PlanRevisionResult]] = {}
        self._decisions: dict[tuple[str, str], tuple[str, G06DecisionResult]] = {}

    def revise(self, request: PlanRevisionRequest) -> PlanRevisionResult:
        payload_checksum = _checksum(request.model_dump(mode="json"))
        key = (request.run_id, request.idempotency_key)
        existing = self._revisions.get(key)
        if existing:
            if existing[0] != payload_checksum:
                raise PlanningReviewApplicationError(
                    "IDEMPOTENCY_PAYLOAD_MISMATCH",
                    "The idempotency key was already used with a different payload.",
                    409,
                )
            return existing[1].model_copy(update={"idempotent_replay": True})
        self._require_state(request.run_id, request.expected_state_version)
        try:
            plan = MigrationPlan.model_validate(request.plan)
            stage = StageExecutionPlan.model_validate(request.stage_plan)
        except Exception as exc:
            raise PlanningReviewApplicationError(
                "INVALID_PLAN_CONTRACT", "The current deterministic plan is invalid.", 422
            ) from exc
        if (
            plan.run_id != request.run_id
            or stage.plan_version != plan.version
            or stage.checksum != request.stage_plan.get("checksum")
            or plan.checksum != checksum_model(plan)
            or stage.checksum != checksum_model(stage)
        ):
            raise PlanningReviewApplicationError(
                "PLAN_BINDING_MISMATCH", "The migration and stage plans are not consistently bound.", 409
            )
        new_plan, new_stage = self._rebuild(plan, stage, request.changes)
        changes = {field.value: getattr(request.changes, field.value) for field in request.changes.changed_fields}
        diff_payload = {
            "from_version": plan.version,
            "to_version": new_plan.version,
            "changed_fields": [field.value for field in request.changes.changed_fields],
            "changes": changes,
        }
        diff = PlanVersionDiff(**diff_payload, checksum=_checksum(diff_payload))
        stale = self._mark_stale(request.run_id, plan.version, "migration plan revision created")
        result = PlanRevisionResult(
            run_id=request.run_id,
            plan=new_plan.model_dump(mode="json"),
            stage_plan=new_stage.model_dump(mode="json"),
            plan_checksum=new_plan.checksum,
            stage_plan_checksum=new_stage.checksum,
            diff=diff,
            stale_approval_ids=tuple(stale),
            state_version=request.expected_state_version + 1,
        )
        self._revisions[key] = (payload_checksum, result)
        return result

    def _rebuild(
        self, plan: MigrationPlan, stage: StageExecutionPlan, changes
    ) -> tuple[MigrationPlan, StageExecutionPlan]:
        version = plan.version + 1
        plan_values = plan.model_dump(mode="python", exclude={"checksum", "version", "plan_id"})
        stage_values = stage.model_dump(mode="python", exclude={"checksum", "plan_version", "stage_plan_id"})
        if changes.catalogue_version is not None:
            if changes.catalogue_version not in APPROVED_CATALOGUE_VERSIONS:
                raise PlanningReviewApplicationError("UNAPPROVED_CATALOGUE", "The catalogue is not approved.", 409)
            plan_values["catalogue_version"] = changes.catalogue_version
        if changes.execution_profile_id is not None:
            if not changes.execution_profile_id.strip():
                raise PlanningReviewApplicationError("UNAPPROVED_EXECUTION_PROFILE", "The execution profile is not approved.", 409)
            stage_values["execution_profile_id"] = changes.execution_profile_id
        commands = dict(stage_values["commands"])
        update = dict(commands["angular_update"][0])
        definition = ANGULAR_UPDATE_V4_RENDERER
        target_cli_exact = changes.target_cli_exact or stage.target_cli_exact
        stage_values["target_cli_exact"] = target_cli_exact
        update["template_version"] = 4
        update["template_id"] = definition.template_id
        update["parameter_bindings"] = {
            "target_cli_exact": target_cli_exact,
            "target_exact": stage.target_exact,
        }
        update["arguments"] = definition.render_arguments(update["parameter_bindings"])
        commands["angular_update"] = (update,)
        stage_values["commands"] = commands
        if changes.validation_policy_id is not None:
            if changes.validation_policy_id not in APPROVED_VALIDATION_POLICIES:
                raise PlanningReviewApplicationError("UNAPPROVED_VALIDATION_POLICY", "The validation policy is not approved.", 409)
            stage_values["validation_policy"]["policy_id"] = changes.validation_policy_id
        if changes.recovery_policy_id is not None:
            if changes.recovery_policy_id not in APPROVED_RECOVERY_POLICIES:
                raise PlanningReviewApplicationError("UNAPPROVED_RECOVERY_POLICY", "The recovery policy is not approved.", 409)
            stage_values["recovery_policy"]["policy_id"] = changes.recovery_policy_id
        if changes.repair_policy_id is not None:
            if changes.repair_policy_id not in APPROVED_REPAIR_POLICIES:
                raise PlanningReviewApplicationError("UNAPPROVED_REPAIR_POLICY", "The repair policy is not approved.", 409)
            plan_values["repair_policy"]["policy_id"] = changes.repair_policy_id
            stage_values["repair_policy"]["policy_id"] = changes.repair_policy_id
        if changes.builder is not None:
            if changes.builder not in APPROVED_BUILDERS:
                raise PlanningReviewApplicationError(
                    "UNSUPPORTED_BUILD_SYSTEM",
                    "Unsupported custom builder cannot be introduced by a plan revision.",
                    409,
                )
            decision = stage.build_system_decision.model_copy(
                update={
                    "builder": changes.builder,
                    "rationale": "Preserve the approved builder decision for the revised plan.",
                }
            )
            stage_values["build_system_decision"] = decision
        current_decision = stage_values["build_system_decision"]
        if not isinstance(current_decision, BuildSystemDecision):
            current_decision = BuildSystemDecision.model_validate(current_decision)
        stage_values["build_system_decision"] = BuildSystemDecision.create(
            decision_id=f"builder-{plan.run_id}-{stage.stage_id}-v{version}",
            builder=current_decision.builder,
            action=current_decision.action,
            rationale=current_decision.rationale,
        )
        revised_plan = MigrationPlan(
            **plan_values, plan_id=f"plan-{plan.run_id}-v{version}", version=version, checksum="sha256:" + "0" * 64
        )
        revised_plan = revised_plan.model_copy(update={"checksum": checksum_model(revised_plan)})
        revised_stage = StageExecutionPlan(
            **stage_values,
            stage_plan_id=f"stage-plan-{plan.run_id}-{stage.stage_id}-v{version}",
            plan_version=version,
            checksum="sha256:" + "0" * 64,
        )
        return revised_plan, revised_stage.model_copy(update={"checksum": checksum_model(revised_stage)})

    def decide_g06(self, gate: G06Gate, package: PlanningPackage, request: G06DecisionRequest) -> G06DecisionResult:
        payload_checksum = _checksum(request.model_dump(mode="json"))
        key = (gate.run_id, request.idempotency_key)
        existing = self._decisions.get(key)
        if existing:
            if existing[0] != payload_checksum:
                raise PlanningReviewApplicationError(
                    "IDEMPOTENCY_PAYLOAD_MISMATCH",
                    "The idempotency key was already used with a different payload.",
                    409,
                )
            return existing[1].model_copy(update={"idempotent_replay": True})
        if request.expected_state_version != gate.state_version:
            raise PlanningReviewApplicationError("STALE_STATE_VERSION", "The run state version is stale.", 409)
        if gate.status != "pending":
            raise PlanningReviewApplicationError("G06_NOT_PENDING", "The G06 gate is no longer pending.", 409)
        if package.review_status != "accepted":
            raise PlanningReviewApplicationError(
                "PLANNING_REVIEW_REQUIRED", "An accepted Planning review is required before G06.", 409
            )
        if (
            request.gate_version != gate.gate_version
            or request.gate_version != self.gate_version
            or request.package_checksum is not None
            and request.package_checksum != gate.package_checksum
            or request.artifact_set_checksum != gate.artifact_set_checksum
            or request.plan_checksum != gate.plan_checksum
            or request.stage_plan_checksum != gate.stage_plan_checksum
            or request.workspace_fingerprint != gate.workspace_fingerprint
        ):
            raise PlanningReviewApplicationError("STALE_G06_BINDING", "The G06 package binding is stale.", 409)
        if package.plan_checksum != gate.plan_checksum or package.stage_plan_checksum != gate.stage_plan_checksum:
            raise PlanningReviewApplicationError(
                "PLAN_CHECKSUM_MISMATCH", "The Planning package is not bound to the active G06 plan.", 409
            )
        if (
            request.decision == G06Decision.APPROVE_WITH_COMMENT
            and not request.comment
            or request.comment is not None
            and not request.comment.strip()
        ):
            raise PlanningReviewApplicationError(
                "G06_COMMENT_REQUIRED", "An approval with comment requires a non-empty comment.", 422
            )
        accepted = request.decision in {G06Decision.APPROVE, G06Decision.APPROVE_WITH_COMMENT}
        result = G06DecisionResult(
            run_id=gate.run_id,
            decision=request.decision,
            accepted=accepted,
            status="approved" if accepted else request.decision.value,
            gate_version=gate.gate_version,
            artifact_set_checksum=gate.artifact_set_checksum,
            plan_checksum=gate.plan_checksum,
            stage_plan_checksum=gate.stage_plan_checksum,
            state_version=request.expected_state_version + 1,
        )
        self._decisions[key] = (payload_checksum, result)
        return result

    def require_approved_g06(
        self,
        gate: G06Gate,
        *,
        state_version: int,
        artifact_set_checksum: str,
        plan_checksum: str,
        stage_plan_checksum: str,
        workspace_fingerprint: str | None,
    ) -> None:
        if gate.status != "approved":
            raise PlanningReviewApplicationError(
                "G06_APPROVAL_REQUIRED", "An approved current G06 gate is required before stage start.", 409
            )
        if (
            gate.state_version != state_version
            or gate.artifact_set_checksum != artifact_set_checksum
            or gate.plan_checksum != plan_checksum
            or gate.stage_plan_checksum != stage_plan_checksum
            or gate.workspace_fingerprint != workspace_fingerprint
        ):
            raise PlanningReviewApplicationError("G06_STALE", "The approved G06 binding is stale.", 409)

    def _require_state(self, run_id: str, expected: int) -> None:
        if self._read_state_version is not None and self._read_state_version(run_id) != expected:
            raise PlanningReviewApplicationError("STALE_STATE_VERSION", "The run state version is stale.", 409)


def _deterministic_plan_checksum(plan: dict[str, Any], stage_plan: dict[str, Any]) -> str:
    return _checksum({"plan": plan, "stage_plan": stage_plan})


def _checksum(value: object) -> str:
    return (
        "sha256:"
        + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    )


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
