from pathlib import Path

import pytest

from app.domain.analysis import AnalysisRequest, G04Decision, G04DecisionRequest
from app.domain.contracts import AgentKind
from app.llm_gateway import AzureGatewayError, LlmFailureCode, LlmResponse, LlmRole, LlmTaskType, PromptRedactionResult, build_usage_record
from app.services.analysis_application_service import AnalysisAgentService, AnalysisApplicationError, AnalysisArtifact


def _request(checksum: str, *, version: int = 1) -> AnalysisRequest:
    return AnalysisRequest(
        run_id="run-1",
        expected_state_version=version,
        idempotency_key="analysis-1",
        actor="operator",
        prerequisite_artifacts=[{"artifact_id": "artifact-findings", "checksum": checksum}],
        workspace_fingerprint="sha256:" + "1" * 64,
    )


class FakeGateway:
    def __init__(self, output_factory=None, failure=None):
        self.output_factory = output_factory
        self.failure = failure
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        if self.failure:
            raise self.failure
        output = self.output_factory(request)
        usage = build_usage_record(
            run_id=request.run_id,
            stage_id=None,
            agent_kind=AgentKind.ANALYSIS,
            task_type=LlmTaskType.ANALYSIS_SUMMARY,
            model_deployment_alias="azure-openai",
            input_tokens=10,
            output_tokens=15,
            input_price_per_million=0.25,
            output_price_per_million=2.0,
        )
        return LlmResponse(
            response_id="response-1",
            request_id=request.request_id,
            run_id=request.run_id,
            agent_kind=AgentKind.ANALYSIS,
            task_type=LlmTaskType.ANALYSIS_SUMMARY,
            model_deployment_alias="azure-openai",
            status="completed",
            summary="validated",
            structured_output=output,
            usage=usage,
            redaction=PromptRedactionResult(redacted_text="safe", redaction_count=0),
            role=LlmRole.PHASE_PROPOSER,
            prompt_version="prompt-analysis-agent-v1",
            schema_version="analysis-schema-registry-v1",
            pricing_version="test-pricing-v1",
        )


def test_generate_is_bound_to_registered_deterministic_artifact_and_preserves_fact_authority():
    content = '{"findings":[{"id":"builder-1","severity":"high"}]}'
    checksum = "sha256:" + "a" * 64
    request = _request(checksum)
    gateway = FakeGateway(lambda gateway_request: {
        "summary": "The builder finding needs review.",
        "risk_groups": [{"name": "builder", "finding_ids": ["builder-1"]}],
        "unresolved_questions": [],
        "evidence_confidence": "high",
        "recommended_next_action": "Review compatibility evidence",
        "deterministic_input_checksum": request.artifact_set_checksum,
    } if gateway_request.task_type is LlmTaskType.ANALYSIS_SUMMARY else {
        "decision": "accept", "notes": ["Evidence is bounded."], "risks": [], "policy_concerns": [], "confidence": "high", "deterministic_input_checksum": request.artifact_set_checksum, "proposer_output_checksum": "sha256:" + "0" * 64,
    })
    service = AnalysisAgentService(
        gateway=gateway,
        artifact_reader=lambda artifact_id: AnalysisArtifact(artifact_id, checksum, content),
    )

    # Supply the reviewer checksum after observing the proposer payload.
    original = gateway.output_factory
    def output(request_to_gateway):
        value = original(request_to_gateway)
        if request_to_gateway.task_type is LlmTaskType.ANALYSIS_REVIEW:
            proposer = request_to_gateway.context[-1].content
            value["proposer_output_checksum"] = "sha256:" + __import__("hashlib").sha256(proposer.encode()).hexdigest() if False else service._checksum(__import__("json").loads(proposer))
        return value
    gateway.output_factory = output
    package = service.generate(request)

    assert package.artifact_set_checksum == request.artifact_set_checksum
    assert package.narrative.deterministic_input_checksum == request.artifact_set_checksum
    assert gateway.requests[0].context[0].untrusted is True
    assert gateway.requests[0].task_type is LlmTaskType.ANALYSIS_SUMMARY


def test_generate_rejects_checksum_mismatch_before_provider_call():
    request = _request("sha256:" + "a" * 64)
    gateway = FakeGateway(lambda _: {})
    service = AnalysisAgentService(
        gateway=gateway,
        artifact_reader=lambda artifact_id: AnalysisArtifact(artifact_id, "sha256:" + "b" * 64, "{}"),
    )

    with pytest.raises(AnalysisApplicationError) as error:
        service.generate(request)

    assert error.value.code == "PREREQUISITE_ARTIFACT_CHECKSUM_MISMATCH"
    assert gateway.requests == []


def test_g04_decision_rejects_stale_package_and_accepts_only_allowed_approval():
    checksum = "sha256:" + "a" * 64
    request = _request(checksum)
    gateway = FakeGateway(lambda gateway_request: {
        "summary": "Review is required.",
        "risk_groups": [],
        "unresolved_questions": ["Confirm private package support"],
        "evidence_confidence": "medium",
        "recommended_next_action": "Review unresolved questions",
        "deterministic_input_checksum": request.artifact_set_checksum,
    } if gateway_request.task_type is LlmTaskType.ANALYSIS_SUMMARY else {
        "decision": "accept", "notes": [], "risks": [], "policy_concerns": [], "confidence": "high", "deterministic_input_checksum": request.artifact_set_checksum, "proposer_output_checksum": service._checksum(__import__("json").loads(gateway_request.context[-1].content)),
    })
    service = AnalysisAgentService(gateway=gateway, artifact_reader=lambda artifact_id: AnalysisArtifact(artifact_id, checksum, "{}"))
    package = service.generate(request)

    result = service.decide_g04(
        request,
        package,
        G04DecisionRequest(
            expected_state_version=1,
            gate_version="g04-v1",
            package_checksum="sha256:" + "b" * 64,
            workspace_fingerprint=request.workspace_fingerprint,
            decision=G04Decision.APPROVE_WITH_COMMENT,
            comment="Proceed with the documented risk.",
        ),
    )
    assert result.accepted is True
    assert result.review_status == "approved"

    with pytest.raises(AnalysisApplicationError) as error:
        service.decide_g04(
            request,
            package,
            G04DecisionRequest(
                expected_state_version=1,
                gate_version="g04-v1",
                package_checksum="sha256:" + "c" * 64,
                workspace_fingerprint="sha256:" + "9" * 64,
                decision=G04Decision.APPROVE,
            ),
        )
    assert error.value.code == "STALE_ANALYSIS_BINDING"


def test_generate_fails_closed_on_provider_failure_and_stale_state():
    checksum = "sha256:" + "a" * 64
    request = _request(checksum)
    provider = AnalysisAgentService(
        gateway=FakeGateway(failure=RuntimeError("provider secret")),
        artifact_reader=lambda artifact_id: AnalysisArtifact(artifact_id, checksum, "{}"),
    )
    with pytest.raises(AnalysisApplicationError) as provider_error:
        provider.generate(request)
    assert provider_error.value.code == "ANALYSIS_PROPOSER_FAILED"

    provider = AnalysisAgentService(
        gateway=FakeGateway(failure=AzureGatewayError(LlmFailureCode.DEPLOYMENT, "deployment failed", provider_status=404, provider_code="DeploymentNotFound")),
        artifact_reader=lambda artifact_id: AnalysisArtifact(artifact_id, checksum, "{}"),
    )
    with pytest.raises(AnalysisApplicationError) as deployment_error:
        provider.generate(request)
    assert deployment_error.value.code == "LLM_DEPLOYMENT_FAILED"
    assert deployment_error.value.status_code == 502
    assert deployment_error.value.details == {"failure_stage": "phase_proposer", "provider_http_status": 404, "provider_error_code": "DeploymentNotFound"}

    stale = AnalysisAgentService(
        gateway=FakeGateway(lambda _: {}),
        artifact_reader=lambda artifact_id: AnalysisArtifact(artifact_id, checksum, "{}"),
        state_version_reader=lambda _: 2,
    )
    with pytest.raises(AnalysisApplicationError) as stale_error:
        stale.generate(request)
    assert stale_error.value.code == "STALE_STATE_VERSION"


def test_reviewer_requests_one_bounded_revision_before_accepting():
    checksum = "sha256:" + "a" * 64
    request = _request(checksum)
    service: AnalysisAgentService
    reviews = 0

    def output(gateway_request):
        nonlocal reviews
        if gateway_request.task_type is LlmTaskType.ANALYSIS_SUMMARY:
            return {"summary": f"Revision {reviews}", "risk_groups": [], "unresolved_questions": [], "evidence_confidence": "high", "recommended_next_action": "Review evidence", "deterministic_input_checksum": request.artifact_set_checksum}
        reviews += 1
        return {"decision": "request_revision" if reviews == 1 else "accept", "notes": ["Clarify evidence."] if reviews == 1 else [], "risks": [], "policy_concerns": [], "confidence": "high", "deterministic_input_checksum": request.artifact_set_checksum, "proposer_output_checksum": service._checksum(__import__("json").loads(gateway_request.context[-1].content))}

    service = AnalysisAgentService(gateway=FakeGateway(output), artifact_reader=lambda artifact_id: AnalysisArtifact(artifact_id, checksum, "{}"), max_revisions=1)
    package = service.generate(request)

    assert package.revision_count == 1
    assert package.reviewer.decision.value == "accept"


def test_reviewer_authoring_field_fails_closed():
    checksum = "sha256:" + "a" * 64
    request = _request(checksum)
    service: AnalysisAgentService

    def output(gateway_request):
        if gateway_request.task_type is LlmTaskType.ANALYSIS_SUMMARY:
            return {"summary": "Bounded evidence.", "risk_groups": [], "unresolved_questions": [], "evidence_confidence": "high", "recommended_next_action": "Review evidence", "deterministic_input_checksum": request.artifact_set_checksum}
        return {"decision": "accept", "confidence": "high", "deterministic_input_checksum": request.artifact_set_checksum, "proposer_output_checksum": service._checksum(__import__("json").loads(gateway_request.context[-1].content)), "patch": "forbidden"}

    service = AnalysisAgentService(gateway=FakeGateway(output), artifact_reader=lambda artifact_id: AnalysisArtifact(artifact_id, checksum, "{}"))
    with pytest.raises(AnalysisApplicationError) as error:
        service.generate(request)
    assert error.value.code == "ANALYSIS_REVIEW_FAILED"
