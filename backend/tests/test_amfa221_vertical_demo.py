"""Executable isolated AMFA-221 closure demonstration."""

from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
import pytest
import json

from app.api.routes import assistant as assistant_routes
from app.domain.contracts import AgentKind, AssistantMessageRequestDto, WorkflowEventType
from app.llm_gateway import LlmResponse, LlmRole, LlmTaskType, PromptRedactionResult, build_usage_record
from app.main import app
from app.repositories.models import ArtifactMetadataModel, AssistantLifecycleEventModel, AssistantMessageModel, Base, LlmInvocationModel, MigrationRunModel, UsageCostRecordModel, WorkflowEventModel
from app.services.assistant_context_service import AssistantContextService
from app.services.llm_evidence_application_service import LlmEvidenceApplicationService
from app.services.workflow_projection_service import WorkflowProjectionService


@pytest.fixture(autouse=True)
def explicit_test_actor(monkeypatch):
    original_answer = AssistantContextService.answer

    def answer(service, request, correlation_id=None, actor=None):
        return original_answer(service, request, correlation_id=correlation_id, actor=actor or "alice")

    monkeypatch.setattr(AssistantContextService, "answer", answer)
    original_history = AssistantContextService.history

    def history(service, run_id, conversation_id=None, *, actor=None):
        return original_history(service, run_id, conversation_id, actor=actor or "alice")

    monkeypatch.setattr(AssistantContextService, "history", history)
    app.dependency_overrides[assistant_routes.assistant_authenticated_actor] = lambda: "alice"
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def test_lifespan(_app):
        yield

    app.router.lifespan_context = test_lifespan
    yield
    app.dependency_overrides.pop(assistant_routes.assistant_authenticated_actor, None)
    app.router.lifespan_context = original_lifespan


class GovernedFakeProvider:
    def __init__(self, *, fail: bool = False):
        self.calls = 0
        self.fail = fail

    def complete(self, request):
        self.calls += 1
        if self.fail:
            raise RuntimeError("provider unavailable")
        usage = build_usage_record(run_id=request.run_id, stage_id=None, agent_kind=AgentKind.ASSISTANT, task_type=LlmTaskType.ASSISTANT_RESPONSE, model_deployment_alias="isolated-fake", input_tokens=7, output_tokens=5, input_price_per_million=1.0, output_price_per_million=2.0)
        policy = json.loads(request.system_policy)
        intent = policy["selected_intent"]
        capability = policy["selected_capability_key"]
        return LlmResponse(response_id=f"fake-{self.calls}", request_id=request.request_id, run_id=request.run_id, agent_kind=AgentKind.ASSISTANT, task_type=LlmTaskType.ASSISTANT_RESPONSE, model_deployment_alias="isolated-fake", status="completed", summary="safe", structured_output={"answer": "The governed fake answer.", "summary": "The governed fake answer.", "intent": intent, "capability_key": capability, "proof_label": "authoritative_persisted_fact", "citations": [], "missing_information": [], "suggested_follow_ups": [], "next_step_proposals": [], "confidence": "high"}, usage=usage, redaction=PromptRedactionResult(redacted_text="safe", redaction_count=0), role=LlmRole.ASSISTANT, prompt_version="assistant", schema_version="schema", pricing_version="pricing")


def test_amfa221_isolated_restart_replay_vertical_demo(tmp_path):
    db = tmp_path / "isolated.db"
    artifact_root = tmp_path / "artifacts"
    output_root = tmp_path / "output"
    artifact_root.mkdir()
    output_root.mkdir()
    engine = create_engine(f"sqlite:///{db}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def scope():
        with sessions() as session:
            yield session
            session.commit()

    now = datetime.now(UTC)
    with sessions() as session:
        session.add(MigrationRunModel(id="demo-run", status="RUNNING", run_phase="FEASIBILITY_PLANNING", phase_status="running", approval_status="not_required", repair_status="not_required", state_version=1, artifact_root=str(artifact_root), run_root=str(output_root), created_at=now, updated_at=now))
        session.add(WorkflowEventModel(id="raw-event", run_id="demo-run", event_type="G02_CREATED", idempotency_key="raw-event", actor="worker", reason="raw", sequence=1, payload={}, occurred_at=now))
        session.add(ArtifactMetadataModel(id="approved-evidence", run_id="demo-run", stage_id=None, artifact_type="report", relative_path="report/evidence.json", checksum="sha256:approved", owner_reference="demo-run:report", safe_metadata={"approval_status": "approved", "lineage": "demo-run"}, created_at=now))
        session.commit()

    with sessions() as session:
        projection = WorkflowProjectionService().build(session, "demo-run")
        assert projection.run_id == "demo-run"
        assert projection.gate.availability == "unavailable"
        assert projection.remaining_work == ["Reach the next governed workflow owner"]
        assert projection.next_permitted_action.availability == "unavailable"

    provider = GovernedFakeProvider()
    invocation_service = LlmEvidenceApplicationService(session_scope_factory=scope, gateway=provider)
    service = AssistantContextService(session_scope_factory=scope, invocation_service=invocation_service)
    app.dependency_overrides[assistant_routes.get_service] = lambda: service
    original_scope = assistant_routes.session_scope
    assistant_routes.session_scope = scope
    try:
        with TestClient(app) as client:
            first = client.post("/api/v1/runs/demo-run/assistant/messages", json={"message": "Where is the migration now?", "idempotency_key": "demo-1"})
            assert first.status_code == 201
            first_body = first.json()
            assert first_body["answer"] == "The governed fake answer."
            with sessions() as session:
                actual_messages = [(item.role, item.message_order, item.status, item.idempotency_key, item.conversation_id) for item in session.scalars(select(AssistantMessageModel).order_by(AssistantMessageModel.message_order, AssistantMessageModel.id))]
                assert [(role, order) for role, order, _status, _key, _conversation in actual_messages] == [("user", 1), ("assistant", 3)], actual_messages
                assert actual_messages[1][3] == "demo-1" and actual_messages[0][3] != "demo-1"
                assert session.query(LlmInvocationModel).count() == 1
                assert session.query(UsageCostRecordModel).count() == 1
                assert [item.event_type for item in session.scalars(select(AssistantLifecycleEventModel).order_by(AssistantLifecycleEventModel.sequence))] == ["ASSISTANT_RESPONSE_STARTED", "ASSISTANT_CONTEXT_BUILT", "ASSISTANT_RESPONSE_COMPLETED"]
            follow = client.post("/api/v1/runs/demo-run/assistant/messages", json={"message": "What is the next permitted action?", "conversation_id": first_body["conversation_id"], "idempotency_key": "demo-2"})
            assert follow.status_code == 201
            assert provider.calls == 2
            replay = client.post("/api/v1/runs/demo-run/assistant/messages", json={"message": "Where is the migration now?", "idempotency_key": "demo-1"})
            assert replay.json()["message_id"] == first_body["message_id"] and provider.calls == 2
            conflict = client.post("/api/v1/runs/demo-run/assistant/messages", json={"message": "changed", "idempotency_key": "demo-1"})
            assert conflict.status_code == 409
            with sessions() as session:
                run = session.get(MigrationRunModel, "demo-run")
                run.state_version += 1
                session.commit()
            history = client.get("/api/v1/runs/demo-run/assistant/messages").json()
            assert all(item["stale"] for item in history["messages"])
            # The legacy TestClient `.get(...).text` technique waited for a
            # finite response and is invalid for R8's long-lived stream. The
            # real bounded HTTP route proof lives in test_assistant_r8_sse.py.
            with sessions() as session:
                assert [item.sequence for item in session.scalars(select(AssistantLifecycleEventModel).where(AssistantLifecycleEventModel.run_id == "demo-run").order_by(AssistantLifecycleEventModel.sequence))] == [1, 2, 3, 4, 5, 6]
            mutation = client.post("/api/v1/runs/demo-run/assistant/messages", json={"message": "Apply the patch.", "idempotency_key": "demo-mutation"})
            assert mutation.status_code == 201 and "read-only" in mutation.json()["answer"]
    finally:
        assistant_routes.session_scope = original_scope
        app.dependency_overrides.pop(assistant_routes.get_service, None)

    restarted = AssistantContextService(session_scope_factory=scope, invocation_service=LlmEvidenceApplicationService(session_scope_factory=scope, gateway=provider))
    restored = restarted.history("demo-run", first_body["conversation_id"])
    assert [message.role for message in restored.messages] == ["user", "assistant", "user", "assistant", "user", "assistant"]
    with sessions() as session:
        assert WorkflowProjectionService().build(session, "demo-run").run_id == "demo-run"
        assert session.query(AssistantMessageModel).count() == 6
        assert session.query(UsageCostRecordModel).count() == 2

    failure_provider = GovernedFakeProvider(fail=True)
    failed_service = AssistantContextService(session_scope_factory=scope, invocation_service=LlmEvidenceApplicationService(session_scope_factory=scope, gateway=failure_provider))
    try:
        failed_service.answer(AssistantMessageRequestDto(run_id="demo-run", message="Where is the migration now?", idempotency_key="demo-failure"))
    except Exception as error:
        assert "failed" in str(error).lower()
    with sessions() as session:
        failed = session.scalar(select(AssistantMessageModel).where(AssistantMessageModel.idempotency_key == "demo-failure"))
        assert failed is not None and failed.status == "failed"
        assert session.query(AssistantLifecycleEventModel).where(AssistantLifecycleEventModel.idempotency_key == "demo-failure").count() == 3
    engine.dispose()
