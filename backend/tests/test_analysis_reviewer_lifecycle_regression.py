from app.domain.contracts import AgentKind
from app.llm_gateway import LlmResponse, LlmRole, LlmTaskType, PromptRedactionResult, build_usage_record
from app.services.analysis_application_service import AnalysisAgentService, AnalysisArtifact

from backend.tests.test_analysis_evidence_persistence_api_s2_f04_i02 import setup


class RecordingGateway:
    def __init__(self, service):
        self.service = service
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        usage = build_usage_record(
            run_id=request.run_id,
            stage_id=None,
            agent_kind=AgentKind.ANALYSIS,
            task_type=request.task_type,
            model_deployment_alias="azure-openai",
            input_tokens=10,
            output_tokens=15,
            input_price_per_million=0.25,
            output_price_per_million=2.0,
        )
        if request.task_type is LlmTaskType.ANALYSIS_SUMMARY:
            structured = {
                "summary": "The deterministic findings require compatibility review.",
                "risk_groups": [],
                "unresolved_questions": [],
                "evidence_confidence": "high",
                "recommended_next_action": "Review compatibility evidence",
            }
        else:
            import json

            proposer = json.loads(request.context[-1].content)
            structured = {
                "decision": "accept",
                "notes": ["Evidence is bounded."],
                "risks": [],
                "policy_concerns": [],
                "confidence": "high",
                "proposer_output_checksum": self.service._checksum(proposer),
            }
        return LlmResponse(
            response_id=f"response-{len(self.requests)}",
            request_id=request.request_id,
            run_id=request.run_id,
            agent_kind=AgentKind.ANALYSIS,
            task_type=request.task_type,
            model_deployment_alias="azure-openai",
            status="completed",
            summary="validated",
            structured_output=structured,
            usage=usage,
            redaction=PromptRedactionResult(redacted_text="safe", redaction_count=0),
            role=request.role,
            prompt_version="analysis-agent-test-v1",
            schema_version="analysis-schema-registry-v1",
            pricing_version="test-pricing-v1",
        )


def test_real_analysis_service_persists_reviewer_lifecycle_and_g04(tmp_path):
    # This deliberately uses the real agent and real service hooks.  Before the
    # fix, the desired assertions fail because the reviewer hook raises
    # UnboundLocalError before the second gateway call.
    gateway_holder = {}

    def make_agent(request=None):
        gateway = gateway_holder["gateway"]
        return AnalysisAgentService(
            gateway=gateway,
            artifact_reader=lambda artifact_id: AnalysisArtifact(
                artifact_id,
                "sha256:" + "a" * 64,
                '{"finding":"builder"}',
            ),
        )

    # setup() owns the real SQLite session scope and artifact store; replace its
    # default fake agent with a real AnalysisAgentService after setup creates the
    # request and database.
    service, payload, sessions, source = setup(tmp_path, agent=None)
    real_agent = AnalysisAgentService(
        gateway=None,  # assigned below after the service exists
        artifact_reader=lambda artifact_id: AnalysisArtifact(
            artifact_id, source.ref.checksum, '{"finding":"builder"}'
        ),
    )
    gateway = RecordingGateway(real_agent)
    real_agent.gateway = gateway
    gateway_holder["gateway"] = gateway
    service.analysis_agent = real_agent

    result = service.generate("run-1", payload, "operator")

    assert result.status == "completed", {
        "status": result.status,
        "error_code": result.error_code,
        "cause_code": result.cause_code,
        "failure_subtype": result.failure_subtype,
        "failure_stage": result.failure_stage,
        "failed_invocation_id": result.failed_invocation_id,
        "gateway_calls": len(gateway.requests),
    }
    assert result.gate_status == "pending"
    assert result.failed_invocation_id is None
    assert len(gateway.requests) == 2
    with sessions() as session:
        from app.repositories.models import LlmInvocationModel, WorkflowEventModel

        invocations = session.query(LlmInvocationModel).filter_by(run_id="run-1").all()
        assert len(invocations) == 2
        assert {invocation.role for invocation in invocations} == {"phase_proposer", "phase_reviewer"}
        events = [event.event_type for event in session.query(WorkflowEventModel).order_by(WorkflowEventModel.sequence)]
        assert events == [
            "ANALYSIS_AGENT_STARTED",
            "LLM_INVOCATION_STARTED",
            "LLM_INVOCATION_COMPLETED",
            "ANALYSIS_AGENT_COMPLETED",
            "ANALYSIS_REVIEWER_STARTED",
            "LLM_INVOCATION_STARTED",
            "LLM_INVOCATION_COMPLETED",
            "ANALYSIS_REVIEWER_COMPLETED",
            "G04_CREATED",
        ]
