from __future__ import annotations

import json

import pytest

from app.domain.contracts import AgentKind
from app.domain.planning import PlanGenerationRequest
from app.domain.planning_review import (
    G06Decision,
    G06DecisionRequest,
    G06Gate,
    PlanRevisionChanges,
    PlanRevisionRequest,
    PlanningExplanationRequest,
    PlanningReviewDecision,
)
from app.llm_gateway import AzureGatewayError, LlmRole, LlmTaskType, LlmResponse, PromptRedactionResult
from app.llm_gateway.azure_gateway import PromptRegistry
from app.llm_gateway.mock_gateway import build_usage_record
from app.services.planning_application_service import PlanningApplicationService
from app.services.planning_review_application_service import (
    PlanRevisionService,
    PlanningAgentService,
    PlanningReviewApplicationError,
)


def _generation():
    request = PlanGenerationRequest(
        run_id="run-1",
        expected_state_version=4,
        idempotency_key="plan-1",
        actor="operator",
        source_exact="18.2.13",
        source_family="angular-18.x",
        target_family="angular-21.x",
        catalogue_version="catalog-v1",
        input_fingerprint="sha256:" + "1" * 64,
        execution_profile_id="profile-node22-npm10",
        builder="@angular-devkit/build-angular:application",
        target_cli_exact="19.2.0",
        stage_route=(
            ("angular-18.x", "angular-19.x", "stage-18-to-19", "19.2.0"),
            ("angular-19.x", "angular-20.x", "stage-19-to-20", "20.0.0"),
            ("angular-20.x", "angular-21.x", "stage-20-to-21", "21.0.0"),
        ),
    )
    return PlanningApplicationService().generate(request)


def test_default_registry_authorizes_planning_prompt_tasks():
    registry = PromptRegistry.defaults()

    assert registry.get("planning_agent_v1", LlmTaskType.PLAN_RATIONALE).version == "prompt-planning-agent-v1"
    assert registry.get("planning_reviewer_v1", LlmTaskType.PLANNING_REVIEW).version == "prompt-planning-reviewer-v1"


def _revision_request(result, **changes):
    return PlanRevisionRequest(
        run_id="run-1",
        expected_state_version=4,
        idempotency_key="revision-1",
        actor="operator",
        plan=result.plan.model_dump(mode="json"),
        stage_plan=result.first_stage_plan.model_dump(mode="json"),
        changes=PlanRevisionChanges(**changes),
        artifact_set_checksum="sha256:" + "2" * 64,
    )


def test_revision_rebuilds_immutable_version_and_marks_dependents_stale():
    result = _generation()
    marked = []
    service = PlanRevisionService(
        stale_approval_marker=lambda run_id, version, reason: marked.append((run_id, version, reason)) or ("g06-1",)
    )

    revised = service.revise(_revision_request(result, execution_profile_id="profile-node23-npm10"))

    assert revised.plan["version"] == 2
    assert revised.plan_checksum != result.plan.checksum
    assert revised.stage_plan["execution_profile_id"] == "profile-node23-npm10"
    assert revised.diff.changed_fields == ("execution_profile_id",)
    assert revised.stale_approval_ids == ("g06-1",)
    assert marked[0][1] == 1


def test_revision_is_idempotent_and_rejects_payload_reuse():
    result = _generation()
    service = PlanRevisionService()
    request = _revision_request(result, catalogue_version="catalog-v2")

    first = service.revise(request)
    replay = service.revise(request)
    assert replay.idempotent_replay is True
    assert replay.plan_checksum == first.plan_checksum

    with pytest.raises(PlanningReviewApplicationError) as error:
        service.revise(request.model_copy(update={"changes": PlanRevisionChanges(recovery_policy_id="recovery-v2")}))
    assert error.value.code == "IDEMPOTENCY_PAYLOAD_MISMATCH"


class _PlanningGateway:
    def __init__(self):
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        trusted_bindings = {}
        for segment in request.context:
            if segment.segment_id in {"deterministic-plan-binding", "proposer-output-binding"}:
                trusted_bindings.update(json.loads(segment.content))
        usage = build_usage_record(
            run_id=request.run_id,
            stage_id=None,
            agent_kind=AgentKind.PLANNING,
            task_type=request.task_type,
            model_deployment_alias="test",
            input_tokens=10,
            output_tokens=10,
            input_price_per_million=1,
            output_price_per_million=1,
        )
        if request.task_type is LlmTaskType.PLAN_RATIONALE:
            output = {
                "summary": "The approved plan follows the deterministic adjacent-major route.",
                "rationale": ["Exact versions are retained."],
                "risks": [],
                "unresolved_questions": [],
                "deterministic_plan_checksum": trusted_bindings["deterministic_plan_checksum"],
            }
        else:
            output = {
                "decision": PlanningReviewDecision.ACCEPT.value,
                "notes": [],
                "policy_concerns": [],
                "confidence": "high",
                "deterministic_plan_checksum": trusted_bindings["deterministic_plan_checksum"],
                "proposer_output_checksum": trusted_bindings["proposer_output_checksum"],
            }
        return LlmResponse(
            response_id="response-1",
            request_id=request.request_id,
            run_id=request.run_id,
            agent_kind=AgentKind.PLANNING,
            task_type=request.task_type,
            model_deployment_alias="test",
            status="completed",
            summary="ok",
            structured_output=output,
            usage=usage,
            redaction=PromptRedactionResult(redacted_text="", redaction_count=0),
            role=request.role,
        )


class _TamperingPlanningGateway(_PlanningGateway):
    def __init__(self, tampered_task):
        super().__init__()
        self.tampered_task = tampered_task

    def complete(self, request):
        response = super().complete(request)
        if request.task_type is not self.tampered_task:
            return response
        field = (
            "deterministic_plan_checksum"
            if request.task_type is LlmTaskType.PLAN_RATIONALE
            else "proposer_output_checksum"
        )
        return response.model_copy(
            update={"structured_output": {**response.structured_output, field: "sha256:" + "f" * 64}}
        )


def test_planning_explanation_is_checksum_bound_and_reviewed():
    result = _generation()
    gateway = _PlanningGateway()
    service = PlanningAgentService(gateway=gateway)
    package = service.explain(
        PlanningExplanationRequest(
            run_id="run-1",
            expected_state_version=4,
            idempotency_key="explain-1",
            actor="operator",
            plan=result.plan.model_dump(mode="json"),
            stage_plan=result.first_stage_plan.model_dump(mode="json"),
            artifact_set_checksum="sha256:" + "3" * 64,
            plan_version=1,
        )
    )
    assert package.review_status == "accepted"
    assert package.reviewer.decision is PlanningReviewDecision.ACCEPT
    assert package.plan_checksum == result.plan.checksum
    assert (
        package.deterministic_plan_checksum == "sha256:9157faeca61ada88dcb78b9d9c12cf8a7975e0e1b0c9537163140993b6fae204"
    )
    proposer_binding = next(
        segment for segment in gateway.requests[0].context if segment.segment_id == "deterministic-plan-binding"
    )
    reviewer_plan_binding = next(
        segment for segment in gateway.requests[1].context if segment.segment_id == "deterministic-plan-binding"
    )
    reviewer_output_binding = next(
        segment for segment in gateway.requests[1].context if segment.segment_id == "proposer-output-binding"
    )
    assert json.loads(proposer_binding.content) == {
        "deterministic_plan_checksum": "sha256:9157faeca61ada88dcb78b9d9c12cf8a7975e0e1b0c9537163140993b6fae204"
    }
    assert reviewer_plan_binding.content == proposer_binding.content
    assert json.loads(reviewer_output_binding.content) == {
        "proposer_output_checksum": "sha256:9911327fae31721b3ebfafd45435f53dece81a4583dc0ead56220941001f9305"
    }


@pytest.mark.parametrize(
    ("tampered_task", "expected_code"),
    (
        (LlmTaskType.PLAN_RATIONALE, "PLANNING_INPUT_CHECKSUM_MISMATCH"),
        (LlmTaskType.PLANNING_REVIEW, "PLANNING_REVIEW_CHECKSUM_MISMATCH"),
    ),
)
def test_planning_rejects_changed_trusted_binding_tokens(tampered_task, expected_code):
    result = _generation()
    service = PlanningAgentService(gateway=_TamperingPlanningGateway(tampered_task))

    with pytest.raises(PlanningReviewApplicationError) as error:
        service.explain(
            PlanningExplanationRequest(
                run_id="run-1",
                expected_state_version=4,
                idempotency_key=f"tampered-{tampered_task.value}",
                actor="operator",
                plan=result.plan.model_dump(mode="json"),
                stage_plan=result.first_stage_plan.model_dump(mode="json"),
                artifact_set_checksum="sha256:" + "3" * 64,
                plan_version=1,
            )
        )

    assert error.value.code == expected_code


def test_planning_proposer_failure_retains_safe_gateway_diagnostics():
    class _FailingGateway:
        def complete(self, request):
            raise AzureGatewayError(
                code="deployment",
                message="deployment failed",
                retryable=True,
                provider_status=503,
                provider_code="ServiceUnavailable",
                provider_request_id="safe-request-1",
                failure_stage="http_response",
                failure_subtype="LLM_RESPONSE_FAILED",
                transport_started=True,
            )

    result = _generation()
    service = PlanningAgentService(gateway=_FailingGateway())

    with pytest.raises(PlanningReviewApplicationError) as error:
        service.explain(
            PlanningExplanationRequest(
                run_id="run-1",
                expected_state_version=4,
                idempotency_key="explain-failure-1",
                actor="operator",
                plan=result.plan.model_dump(mode="json"),
                stage_plan=result.first_stage_plan.model_dump(mode="json"),
                artifact_set_checksum="sha256:" + "3" * 64,
                plan_version=1,
            )
        )

    assert error.value.code == "PLANNING_PROPOSER_FAILED"
    assert error.value.details == {
        "failure_code": "deployment",
        "failure_stage": "http_response",
        "failure_subtype": "LLM_RESPONSE_FAILED",
        "retryable": True,
        "provider_http_status": 503,
        "provider_error_code": "ServiceUnavailable",
        "provider_request_id": "safe-request-1",
        "transport_started": True,
    }


def test_g06_rejects_stale_binding_and_stage_start_without_approval():
    result = _generation()
    service = PlanRevisionService()
    gate = G06Gate(
        run_id="run-1",
        gate_version="g06-v1",
        status="pending",
        artifact_set_checksum="sha256:" + "3" * 64,
        plan_checksum=result.plan.checksum,
        stage_plan_checksum=result.first_stage_plan.checksum,
        state_version=4,
    )
    with pytest.raises(PlanningReviewApplicationError) as error:
        service.require_approved_g06(
            gate,
            state_version=4,
            artifact_set_checksum=gate.artifact_set_checksum,
            plan_checksum=gate.plan_checksum,
            stage_plan_checksum=gate.stage_plan_checksum,
            workspace_fingerprint=None,
        )
    assert error.value.code == "G06_APPROVAL_REQUIRED"


def test_g06_accepts_only_the_current_reviewed_plan_binding():
    result = _generation()
    package = PlanningAgentService(gateway=_PlanningGateway()).explain(
        PlanningExplanationRequest(
            run_id="run-1",
            expected_state_version=4,
            idempotency_key="explain-2",
            actor="operator",
            plan=result.plan.model_dump(mode="json"),
            stage_plan=result.first_stage_plan.model_dump(mode="json"),
            artifact_set_checksum="sha256:" + "3" * 64,
            plan_version=1,
        )
    )
    gate = G06Gate(
        run_id="run-1",
        gate_version="g06-v1",
        status="pending",
        artifact_set_checksum=package.artifact_set_checksum,
        plan_checksum=result.plan.checksum,
        stage_plan_checksum=result.first_stage_plan.checksum,
        state_version=4,
    )
    service = PlanRevisionService()
    decision = service.decide_g06(
        gate,
        package,
        G06DecisionRequest(
            expected_state_version=4,
            idempotency_key="g06-1",
            gate_version="g06-v1",
            artifact_set_checksum=package.artifact_set_checksum,
            plan_checksum=result.plan.checksum,
            stage_plan_checksum=result.first_stage_plan.checksum,
            decision=G06Decision.APPROVE,
        ),
    )
    assert decision.accepted is True
    assert decision.status == "approved"

    with pytest.raises(PlanningReviewApplicationError) as stale:
        service.decide_g06(
            gate,
            package,
            G06DecisionRequest(
                expected_state_version=4,
                idempotency_key="g06-2",
                gate_version="g06-v1",
                artifact_set_checksum=package.artifact_set_checksum,
                plan_checksum="sha256:" + "f" * 64,
                stage_plan_checksum=result.first_stage_plan.checksum,
                decision=G06Decision.APPROVE,
            ),
        )
    assert stale.value.code == "STALE_G06_BINDING"
