from contextlib import contextmanager
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
import pytest

from app.domain.contracts import AgentKind, AssistantMessageRequestDto
from app.llm_gateway import AzureGatewayError, LlmFailureCode, LlmResponse, LlmRole, LlmTaskType, PromptRedactionResult, build_usage_record
from app.api.llm_contracts import LlmInvocationResponse
from app.main import app
from app.repositories.models import ArtifactMetadataModel, AssistantLifecycleEventModel, AssistantMessageModel, Base, ExecutionProfileModel, G02ApprovalModel, LlmInvocationModel, MigrationRunModel, SourceSnapshotModel, UsageCostRecordModel, WorkflowEventModel
from app.services.assistant_context_service import AssistantContextService
from app.api.routes import assistant as assistant_routes
from app.domain.contracts import AssistantWorkflowProjectionDto, ProjectionValue
from app.core.config import get_settings
from app.services.llm_evidence_application_service import LlmEvidenceApplicationService
from app.services.assistant_evidence_retrieval_service import AssistantEvidenceRetrievalService
from app.services.workflow_projection_service import WorkflowProjectionService


class Gateway:
    def complete(self, request):
        usage = build_usage_record(run_id=request.run_id, stage_id=None, agent_kind=AgentKind.ASSISTANT, task_type=LlmTaskType.ASSISTANT_RESPONSE, model_deployment_alias="test-assistant", input_tokens=0, output_tokens=0, input_price_per_million=0.25, output_price_per_million=2.0)
        return LlmResponse(response_id="response", request_id=request.request_id, run_id=request.run_id, agent_kind=AgentKind.ASSISTANT, task_type=LlmTaskType.ASSISTANT_RESPONSE, model_deployment_alias="test-assistant", status="completed", summary="validated", usage=usage, redaction=PromptRedactionResult(redacted_text="safe", redaction_count=0), role=LlmRole.ASSISTANT, prompt_version="prompt", schema_version="schema", pricing_version="pricing")


class ProjectionGateway(Gateway):
    def __init__(self):
        self.calls = []

    def complete(self, request):
        self.calls.append(request)
        response = super().complete(request)
        return response.model_copy(update={"structured_output": {"answer": "The authoritative answer is Analysis.", "citations": []}})


class CitationGateway(ProjectionGateway):
    def __init__(self, citations):
        super().__init__()
        self.citations = citations

    def complete(self, request):
        response = super().complete(request)
        return response.model_copy(update={"structured_output": {"answer": "Cited answer.", "citations": self.citations}})


class FailingGateway(Gateway):
    def complete(self, request):
        raise RuntimeError("provider unavailable")


class InvalidStructuredGateway(Gateway):
    def complete(self, request):
        response = super().complete(request)
        return response.model_copy(update={"structured_output": {"answer": 42}})


class RetryGateway(Gateway):
    def complete(self, request):
        response = super().complete(request)
        return response.model_copy(update={"usage": response.usage.model_copy(update={"retry_count": 2}), "structured_output": {"answer": "Retried answer.", "citations": []}})


class TimeoutGateway(Gateway):
    def complete(self, request):
        raise AzureGatewayError(LlmFailureCode.TIMEOUT, "timed out", retryable=False)


class InvocationServiceSpy:
    def __init__(self):
        self.calls = []

    def assistant(self, request, *, actor="assistant"):
        self.calls.append((request, actor))
        return LlmInvocationResponse(invocation_id="invocation-spy", run_id=request.run_id, status="completed", role="assistant", task_type="assistant_response", provider="fake", deployment_alias="fake", structured_output={"answer": "Application-service answer.", "citations": []}, correlation_id="corr-spy", prompt_version="prompt-spy", schema_version="schema-spy", pricing_version="pricing-spy", input_tokens=3, output_tokens=2, total_tokens=5, input_cost_usd=0.1, output_cost_usd=0.2, total_cost_usd=0.3, state_version=3, event_sequence=2)


def setup(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'assistant.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as session:
        session.add(MigrationRunModel(id="run-1", status="WAITING", run_phase="FEASIBILITY_PLANNING", phase_status="waiting_approval", state_version=3, source_angular_version="18.x", target_angular_version="21.x", created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
        session.commit()

    @contextmanager
    def scope():
        with sessions() as session:
            yield session
            session.commit()

    return engine, scope, sessions


def test_in_process_post_persists_and_get_restores_ordered_history(tmp_path):
    engine, scope, sessions = setup(tmp_path)
    service = AssistantContextService(session_scope_factory=scope, gateway=Gateway())
    app.dependency_overrides[assistant_routes.get_service] = lambda: service
    try:
        with TestClient(app) as client:
            first = client.post("/api/v1/runs/run-1/assistant/messages", json={"message": "Where is the migration now?", "idempotency_key": "one"})
            assert first.status_code == 201
            first_body = first.json()
            assert first_body["workflow_state_version"] == 1 or first_body["workflow_state_version"] == 3
            assert first_body["proof_label"] == "authoritative persisted fact"
            replay = client.post("/api/v1/runs/run-1/assistant/messages", json={"message": "Where is the migration now?", "idempotency_key": "one"})
            assert replay.json()["message_id"] == first_body["message_id"]
            second = client.post("/api/v1/runs/run-1/assistant/messages", json={"message": "What did the Planning Agent propose?", "conversation_id": first_body["conversation_id"], "idempotency_key": "two"})
            assert second.status_code == 201
            history = client.get(f"/api/v1/runs/run-1/assistant/messages?conversation_id={first_body['conversation_id']}")
            history_messages = history.json()["messages"]
            assert [item["role"] for item in history_messages] == ["user", "assistant", "user", "assistant"]
            assert [item["message_id"] for item in history_messages[1::2]] == [first_body["message_id"], second.json()["message_id"]]
        with sessions() as session:
            assert session.scalar(select(AssistantMessageModel).where(AssistantMessageModel.run_id == "run-1")) is not None
    finally:
        app.dependency_overrides.pop(assistant_routes.get_service, None)
        engine.dispose()


def test_mutation_is_refused_and_unsupported_is_unknown(tmp_path):
    engine, scope, _ = setup(tmp_path)
    service = AssistantContextService(session_scope_factory=scope, gateway=Gateway())
    mutation = service.answer(AssistantMessageRequestDto(run_id="run-1", message="Approve the current gate.", idempotency_key="mutation"))
    unsupported = service.answer(AssistantMessageRequestDto(run_id="run-1", message="What is the weather?", idempotency_key="unsupported"))
    assert "read-only" in mutation.answer
    assert unsupported.proof_label == "unknown or unavailable"
    engine.dispose()


def test_assistant_conversation_and_events_restore_after_session_restart(tmp_path):
    engine, scope, sessions = setup(tmp_path)
    first_service = AssistantContextService(session_scope_factory=scope, gateway=Gateway())
    first = first_service.answer(AssistantMessageRequestDto(run_id="run-1", message="Where is the migration now?", idempotency_key="restart-1"))
    follow_up = first_service.answer(AssistantMessageRequestDto(run_id="run-1", conversation_id=first.conversation_id, message="What is the next permitted action?", idempotency_key="restart-2"))
    with sessions() as session:
        events = list(session.scalars(select(AssistantLifecycleEventModel).where(AssistantLifecycleEventModel.run_id == "run-1").order_by(AssistantLifecycleEventModel.sequence)))
        assert [event.event_type for event in events] == ["ASSISTANT_RESPONSE_STARTED", "ASSISTANT_RESPONSE_COMPLETED", "ASSISTANT_RESPONSE_STARTED", "ASSISTANT_RESPONSE_COMPLETED"]
        assert len({event.sequence for event in events}) == 4
    engine.dispose()

    restarted_engine = create_engine(f"sqlite:///{tmp_path / 'assistant.db'}")
    restarted_sessions = sessionmaker(bind=restarted_engine, expire_on_commit=False)
    @contextmanager
    def restarted_scope():
        with restarted_sessions() as session:
            yield session
            session.commit()
    restored_service = AssistantContextService(session_scope_factory=restarted_scope, gateway=Gateway())
    restored = restored_service.history("run-1", first.conversation_id)
    assert restored.conversation_id == first.conversation_id
    assert [message.role for message in restored.messages] == ["user", "assistant", "user", "assistant"]
    assert [message.message_id for message in restored.messages[1::2]] == [first.message_id, follow_up.message_id]
    assert [message.usage.total_tokens for message in restored.messages[1::2]] == [first.usage.total_tokens, follow_up.usage.total_tokens]
    with restarted_sessions() as session:
        events = list(session.scalars(select(AssistantLifecycleEventModel).where(AssistantLifecycleEventModel.run_id == "run-1").order_by(AssistantLifecycleEventModel.sequence)))
        assert len(events) == 4
    with restarted_sessions() as session:
        run = session.get(MigrationRunModel, "run-1")
        run.state_version += 1
        newer_state_version = run.state_version
        session.commit()
    stale_history = restored_service.history("run-1", first.conversation_id)
    assert all(message.stale for message in stale_history.messages)
    assert stale_history.messages[0].workflow_state_version == first.workflow_state_version
    newer = restored_service.answer(AssistantMessageRequestDto(run_id="run-1", conversation_id=first.conversation_id, message="Where is the migration now?", idempotency_key="restart-3", client_known_state_version=newer_state_version))
    assert newer.workflow_state_version == newer_state_version
    assert newer.message_id not in {first.message_id, follow_up.message_id}
    restarted_engine.dispose()


def test_observed_g02_projection_maps_authoritative_progress_and_zero_usage(tmp_path):
    engine, scope, sessions = setup(tmp_path)
    now = datetime.now(UTC)
    with sessions() as session:
        run = session.get(MigrationRunModel, "run-1")
        run.status = "SOURCE_VALIDATED"
        run.run_phase = "PREFLIGHT_SNAPSHOT"
        run.state_version = 8
        for sequence, event_type, payload in [
            (1, "SOURCE_INTAKE_COMPLETED", {}),
            (2, "SNAPSHOT_CREATED", {"artifact_ids": ["artifact-snapshot"]}),
            (3, "SOURCE_INTEGRITY_VERIFIED", {"artifact_ids": ["artifact-integrity"]}),
            (4, "G02_CREATED", {"gate_id": "G02", "artifact_ids": ["artifact-g02"]}),
        ]:
            session.add(WorkflowEventModel(id=f"event-{sequence}", run_id="run-1", event_type=event_type, idempotency_key=f"event-{sequence}", actor="worker", reason="authoritative", sequence=sequence, payload=payload, occurred_at=now))
        for artifact_id, path in [("artifact-create", "01_run_creation/create_run_request.json"), ("artifact-snapshot", "02_snapshot/source_snapshot.json"), ("artifact-integrity", "03_g02/source_integrity_verification.json"), ("artifact-g02", "03_g02/g02_evidence_index.json")]:
            session.add(ArtifactMetadataModel(id=artifact_id, run_id="run-1", stage_id=None, artifact_type="json", relative_path=path, checksum=f"sha256:{artifact_id}", created_at=now))
        session.commit()

    service = AssistantContextService(session_scope_factory=scope, gateway=Gateway())
    current = service.answer(AssistantMessageRequestDto(run_id="run-1", message="Where is the migration now?", idempotency_key="observed-current"))
    completed = service.answer(AssistantMessageRequestDto(run_id="run-1", conversation_id=current.conversation_id, message="What has already been completed?", idempotency_key="observed-completed"))
    operations = service.answer(AssistantMessageRequestDto(run_id="run-1", conversation_id=current.conversation_id, message="How much token usage and cost has the migration consumed?", idempotency_key="observed-usage"))

    assert "Preflight Snapshot" in current.answer
    assert "Current gate: unknown" in current.answer
    assert "G02" not in current.answer
    assert "Workflow state version: " in current.answer
    assert "next permitted action is: unknown" in current.answer
    assert "Source intake" not in completed.answer
    assert "Source snapshot" not in completed.answer
    assert current.usage.total_tokens == 0
    assert current.usage.estimated_total_cost == 0
    assert operations.usage.total_tokens == 0
    assert [item.artifact_id for item in current.evidence_references] == ["artifact-snapshot", "artifact-integrity", "artifact-g02"]
    assert "$0.000000" in operations.answer
    engine.dispose()


def test_recorded_duration_uses_persisted_event_timestamps_and_replays_stably(tmp_path):
    engine, scope, sessions = setup(tmp_path)
    start = datetime(2026, 7, 23, 17, 53, 27, 680679, tzinfo=UTC)
    with sessions() as session:
        run = session.get(MigrationRunModel, "run-1")
        run.created_at = start
        run.updated_at = start.replace(microsecond=885989)
        session.add(WorkflowEventModel(id="duration-1", run_id="run-1", event_type="RUN_CREATED", idempotency_key="duration-1", actor="worker", reason="authoritative", sequence=1, payload={}, occurred_at=start.replace(microsecond=680679)))
        session.add(WorkflowEventModel(id="duration-2", run_id="run-1", event_type="G02_CREATED", idempotency_key="duration-2", actor="worker", reason="authoritative", sequence=2, payload={}, occurred_at=start.replace(microsecond=885989)))
        session.commit()
    service = AssistantContextService(session_scope_factory=scope, gateway=Gateway())
    result = service.answer(AssistantMessageRequestDto(run_id="run-1", message="How much recorded workflow time, token usage, and estimated cost has this migration consumed?", idempotency_key="duration-1"))
    replay = service.history("run-1", result.conversation_id)
    assert "Recorded workflow duration: 0.21 seconds." in result.answer
    assert replay.messages[1].answer == result.answer
    assert result.usage.total_tokens == 0
    assert result.usage.estimated_total_cost == 0
    engine.dispose()


def test_recorded_duration_prefers_terminal_run_timestamp(tmp_path):
    engine, scope, sessions = setup(tmp_path)
    start = datetime(2026, 7, 23, 17, 53, 27, tzinfo=UTC)
    terminal = start.replace(second=30)
    with sessions() as session:
        run = session.get(MigrationRunModel, "run-1")
        run.status = "COMPLETED"
        run.created_at = start
        run.updated_at = terminal
        session.add(WorkflowEventModel(id="terminal-1", run_id="run-1", event_type="RUN_COMPLETED", idempotency_key="terminal-1", actor="worker", reason="authoritative", sequence=1, payload={}, occurred_at=start.replace(second=29)))
        session.commit()
    service = AssistantContextService(session_scope_factory=scope, gateway=Gateway())
    result = service.answer(AssistantMessageRequestDto(run_id="run-1", message="How much recorded workflow time, token usage, and estimated cost has this migration consumed?", idempotency_key="terminal-duration"))
    assert "Recorded workflow duration: 3.00 seconds." in result.answer
    engine.dispose()


def test_recorded_duration_is_unavailable_without_persisted_timestamps():
    run = type("Run", (), {"status": "SOURCE_VALIDATED", "created_at": None, "updated_at": None, "workflow_events": []})()
    assert AssistantContextService._recorded_workflow_duration_seconds(run) is None


def test_assistant_usage_matches_governed_invocation_records(tmp_path):
    engine, scope, sessions = setup(tmp_path)
    now = datetime.now(UTC)
    with sessions() as session:
        session.add(LlmInvocationModel(id="invocation-1", run_id="run-1", stage_id=None, idempotency_key="llm-1", request_checksum="sha256:req", input_hashes=[], correlation_id="corr", actor="operator", role="assistant", task_type="smoke_check", provider="azure_openai", deployment_alias="azure-openai", prompt_version="prompt", schema_version="schema", pricing_version="pricing", stage=None, redacted_summary="safe", status="completed", failure_code=None, artifact_ids=[], artifact_checksums={}, state_version=3, event_sequence=1, retries=0, started_at=now, completed_at=now, created_at=now))
        session.add(UsageCostRecordModel(id="usage-1", invocation_id="invocation-1", run_id="run-1", stage_id=None, pricing_version="pricing", input_tokens=10, output_tokens=5, total_tokens=15, input_price_per_million=1.0, output_price_per_million=2.0, input_cost_usd=0.00001, output_cost_usd=0.00001, total_cost_usd=0.00002, created_at=now))
        session.commit()
    result = AssistantContextService(session_scope_factory=scope, gateway=Gateway()).answer(AssistantMessageRequestDto(run_id="run-1", message="How much token usage and cost has the migration consumed?", idempotency_key="governed-usage"))
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 5
    assert result.usage.total_tokens == 15
    assert result.usage.estimated_total_cost == 0.00002
    engine.dispose()


def test_failed_runtime_profile_projection_uses_authoritative_records_and_citation_allowlist(tmp_path):
    engine, scope, sessions = setup(tmp_path)
    now = datetime.now(UTC)
    with sessions() as session:
        run = session.get(MigrationRunModel, "run-1")
        run.status = "FAILED"
        run.run_phase = "PREFLIGHT_SNAPSHOT"
        run.approval_status = "approved"
        run.state_version = 12
        for artifact_id in ("artifact-snapshot", "artifact-g02", "artifact-profile"):
            session.add(ArtifactMetadataModel(id=f"metadata-{artifact_id}", run_id="run-1", stage_id=None, artifact_type="json", relative_path=f"evidence/{artifact_id}.json", checksum=f"sha256:{artifact_id}", immutable=True, created_at=now))
        session.add(SourceSnapshotModel(id="snapshot-1", run_id="run-1", idempotency_key="snapshot-1", actor="worker", status="created", source_path="source", snapshot_path="snapshot", manifest_id="manifest", fingerprint="sha256:snapshot", policy_version="policy", file_count=1, total_size_bytes=1, exclusions=[], git_metadata={}, artifact_ids=["artifact-snapshot"], state_version=8, event_sequence=2, created_at=now, updated_at=now))
        session.add(G02ApprovalModel(id="g02-1", run_id="run-1", gate_id="G02", gate_version="v1", idempotency_key="g02-1", actor="operator", status="approved", decision="approved", package_checksum="sha256:package", artifact_set_checksum="sha256:set", snapshot_id="snapshot-1", state_version=9, event_sequence=3, baseline_input_boundary="snapshot", package={}, artifact_ids=["artifact-g02"], created_at=now, updated_at=now))
        session.add(ExecutionProfileModel(id="profile-1", run_id="run-1", idempotency_key="profile-1", request_checksum="sha256:req", policy_version="policy", status="blocked", source_angular_exact="18.2.0", selected_profile_id=None, selected_checksum=None, profiles=[], blockers=["NO_COMPATIBLE_RUNTIME_PROFILE"], guidance=["Install or expose an approved paired Node/npm/npx runtime."], artifact_ids=["artifact-profile"], state_version=12, event_sequence=5, created_at=now, updated_at=now))
        session.add(WorkflowEventModel(id="failed-runtime", run_id="run-1", event_type="SOURCE_INTAKE_FAILED", idempotency_key="failed-runtime", actor="worker", reason="failed", sequence=6, payload={}, occurred_at=now))
        session.commit()
        projection = WorkflowProjectionService().build(session, "run-1").model_dump(mode="json")
        _, refs = AssistantEvidenceRetrievalService().retrieve(session, "run-1", "Where is the migration now?")
    assert projection["status"] == {"value": "FAILED", "availability": "known"}
    assert projection["blocker"] == {"value": "NO_COMPATIBLE_RUNTIME_PROFILE", "availability": "known"}
    assert projection["next_permitted_action"]["availability"] == "known"
    assert {item["artifact_id"] for item in projection["evidence_references"]} == {"metadata-artifact-snapshot", "metadata-artifact-g02", "metadata-artifact-profile"}
    assert {item["artifact_id"] for item in refs} == {"metadata-artifact-snapshot", "metadata-artifact-g02", "metadata-artifact-profile"}
    engine.dispose()


def test_assistant_uses_shared_projection_over_conversation_and_does_not_infer_fields(tmp_path):
    engine, scope, _ = setup(tmp_path)
    service = AssistantContextService(session_scope_factory=scope, gateway=Gateway())
    projection = AssistantWorkflowProjectionDto(
        run_id="run-1",
        phase=ProjectionValue(value="Analysis", availability="known"),
        stage=ProjectionValue(value="analysis-stage", availability="known"),
        gate=ProjectionValue(value="G04", availability="known"),
        status=ProjectionValue(value="WAITING", availability="known"),
        blocker=ProjectionValue(value=None, availability="unsupported"),
        next_permitted_action=ProjectionValue(value=None, availability="unsupported"),
        workflow_state_version=3,
    )
    service._run = lambda _run_id: type("Run", (), {"assistant_projection": projection})()
    assert service._projection(service._run("run-1"))["phase"] == "Analysis"
    assert service._projection(service._run("run-1"))["blocker"] == "unknown"
    engine.dispose()


def test_normal_migration_question_uses_governed_assistant_role(tmp_path):
    engine, scope, _ = setup(tmp_path)
    gateway = ProjectionGateway()
    result = AssistantContextService(session_scope_factory=scope, gateway=gateway).answer(
        AssistantMessageRequestDto(run_id="run-1", message="Where is the migration now?", idempotency_key="governed-state")
    )
    assert gateway.calls
    assert result.answer == "The authoritative answer is Analysis."
    with scope() as session:
        assert session.scalar(select(LlmInvocationModel).where(LlmInvocationModel.run_id == "run-1")) is not None
        assert session.scalar(select(UsageCostRecordModel).where(UsageCostRecordModel.run_id == "run-1")) is not None
        assert [item.event_type for item in session.scalars(select(AssistantLifecycleEventModel).where(AssistantLifecycleEventModel.run_id == "run-1").order_by(AssistantLifecycleEventModel.sequence))] == ["ASSISTANT_RESPONSE_STARTED", "ASSISTANT_RESPONSE_COMPLETED"]
    engine.dispose()


def test_assistant_routes_through_s2_f03_application_service_not_gateway(tmp_path):
    engine, scope, _ = setup(tmp_path)
    invocation_service = InvocationServiceSpy()
    gateway = ProjectionGateway()
    result = AssistantContextService(session_scope_factory=scope, gateway=gateway, invocation_service=invocation_service).answer(AssistantMessageRequestDto(run_id="run-1", message="Where is the migration now?", idempotency_key="application-seam"))
    assert result.answer == "Application-service answer."
    assert len(invocation_service.calls) == 1
    assert not gateway.calls
    assert invocation_service.calls[0][0].role == "assistant"
    engine.dispose()


def test_same_idempotency_key_with_changed_request_is_rejected(tmp_path):
    engine, scope, _ = setup(tmp_path)
    service = AssistantContextService(session_scope_factory=scope, gateway=Gateway())
    service.answer(AssistantMessageRequestDto(run_id="run-1", message="Where is the migration now?", idempotency_key="same-key"))
    with pytest.raises(Exception, match="different payload"):
        service.answer(AssistantMessageRequestDto(run_id="run-1", message="What is the next action?", idempotency_key="same-key"))
    engine.dispose()


def test_idempotency_checksum_covers_conversation_and_client_state_version(tmp_path):
    engine, scope, _ = setup(tmp_path)
    service = AssistantContextService(session_scope_factory=scope, gateway=Gateway())
    service.answer(AssistantMessageRequestDto(run_id="run-1", message="Where is the migration now?", conversation_id="conversation-a", client_known_state_version=3, idempotency_key="complete-key"))
    for conversation_id, state_version in (("conversation-b", 3), ("conversation-a", 4)):
        with pytest.raises(Exception, match="different payload"):
            service.answer(AssistantMessageRequestDto(run_id="run-1", message="Where is the migration now?", conversation_id=conversation_id, client_known_state_version=state_version, idempotency_key="complete-key"))
    engine.dispose()


def test_provider_failure_is_recoverable_and_persists_failed_lifecycle(tmp_path):
    engine, scope, sessions = setup(tmp_path)
    with pytest.raises(Exception, match="provider failed"):
        AssistantContextService(session_scope_factory=scope, gateway=FailingGateway()).answer(AssistantMessageRequestDto(run_id="run-1", message="Where is the migration now?", idempotency_key="provider-failure"))
    with sessions() as session:
        assert [item.event_type for item in session.scalars(select(AssistantLifecycleEventModel).where(AssistantLifecycleEventModel.run_id == "run-1").order_by(AssistantLifecycleEventModel.sequence))] == ["ASSISTANT_RESPONSE_STARTED", "ASSISTANT_RESPONSE_FAILED"]
        failed = session.scalar(select(AssistantMessageModel).where(AssistantMessageModel.run_id == "run-1", AssistantMessageModel.idempotency_key == "provider-failure"))
        assert failed is not None and failed.status == "failed" and failed.failure_reason
    engine.dispose()


def test_invalid_structured_response_is_governed_failure_with_provider_usage(tmp_path):
    engine, scope, sessions = setup(tmp_path)
    with pytest.raises(Exception, match="provider failed"):
        AssistantContextService(session_scope_factory=scope, gateway=InvalidStructuredGateway()).answer(AssistantMessageRequestDto(run_id="run-1", message="Where is the migration now?", idempotency_key="invalid-structured"))
    with sessions() as session:
        invocation = session.scalar(select(LlmInvocationModel).where(LlmInvocationModel.run_id == "run-1"))
        usage = session.scalar(select(UsageCostRecordModel).where(UsageCostRecordModel.run_id == "run-1"))
        assert invocation.status == "failed"
        assert usage is not None and usage.total_tokens == 0
    engine.dispose()


def test_governed_retry_count_and_timeout_classification_are_preserved(tmp_path):
    engine, scope, sessions = setup(tmp_path)
    result = AssistantContextService(session_scope_factory=scope, gateway=RetryGateway()).answer(AssistantMessageRequestDto(run_id="run-1", message="Where is the migration now?", idempotency_key="retry-accounting"))
    assert result.answer == "Retried answer."
    with sessions() as session:
        invocation = session.scalar(select(LlmInvocationModel).where(LlmInvocationModel.run_id == "run-1"))
        assert invocation.retries == 2
    engine.dispose()


def test_budget_block_happens_before_assistant_provider_execution(tmp_path):
    engine, scope, sessions = setup(tmp_path)
    settings = get_settings()
    previous_budget = settings.llm_token_budget
    settings.llm_token_budget = 1
    try:
        now = datetime.now(UTC)
        with sessions() as session:
            session.add(LlmInvocationModel(id="prior-budget", run_id="run-1", stage_id=None, idempotency_key="prior-budget", request_checksum="sha256:prior", input_hashes=[], correlation_id="prior", actor="operator", role="assistant", task_type="assistant_response", provider="fake", deployment_alias="fake", prompt_version="prompt", schema_version="schema", pricing_version="pricing", stage=None, redacted_summary="safe", status="completed", failure_code=None, artifact_ids=[], artifact_checksums={}, state_version=3, event_sequence=1, retries=0, started_at=now, completed_at=now, created_at=now))
            session.add(UsageCostRecordModel(id="prior-budget-usage", invocation_id="prior-budget", run_id="run-1", stage_id=None, pricing_version="pricing", input_tokens=2, output_tokens=0, total_tokens=2, input_price_per_million=0.0, output_price_per_million=0.0, input_cost_usd=0.0, output_cost_usd=0.0, total_cost_usd=0.0, created_at=now))
            session.commit()
        gateway = ProjectionGateway()
        invocation_service = LlmEvidenceApplicationService(settings=settings, session_scope_factory=scope, gateway=gateway)
        with pytest.raises(Exception, match="provider failed"):
            AssistantContextService(session_scope_factory=scope, invocation_service=invocation_service).answer(AssistantMessageRequestDto(run_id="run-1", message="Where is the migration now?", idempotency_key="budget-block"))
        assert not gateway.calls
    finally:
        settings.llm_token_budget = previous_budget
        engine.dispose()

    timeout_path = tmp_path / "timeout"
    timeout_path.mkdir()
    engine, scope, sessions = setup(timeout_path)
    with pytest.raises(Exception, match="provider failed"):
        AssistantContextService(session_scope_factory=scope, gateway=TimeoutGateway()).answer(AssistantMessageRequestDto(run_id="run-1", message="Where is the migration now?", idempotency_key="timeout-accounting"))
    with sessions() as session:
        invocation = session.scalar(select(LlmInvocationModel).where(LlmInvocationModel.run_id == "run-1"))
        assert invocation.status == "failed"
        assert invocation.failure_code == "timeout"
    engine.dispose()


def test_wrong_run_citation_is_rejected(tmp_path):
    engine, scope, _ = setup(tmp_path)
    gateway = CitationGateway([{"artifact_id": "not-run-1", "checksum": "sha256:wrong", "stage_id": None}])
    with pytest.raises(Exception, match="citation"):
        AssistantContextService(session_scope_factory=scope, gateway=gateway).answer(AssistantMessageRequestDto(run_id="run-1", message="Where is the migration now?", idempotency_key="wrong-citation"))
    engine.dispose()


def test_citation_requires_approved_supported_lineage_and_immutable_artifact(tmp_path):
    engine, scope, sessions = setup(tmp_path)
    now = datetime.now(UTC)
    with sessions() as session:
        session.add(ArtifactMetadataModel(id="approved", run_id="run-1", stage_id=None, artifact_type="report", relative_path="evidence/report.json", checksum="sha256:approved", owner_reference="arbitrary-owner", immutable=True, safe_metadata={"approval_status": "approved", "lineage": "run-1"}, created_at=now))
        session.add(ArtifactMetadataModel(id="unapproved", run_id="run-1", stage_id=None, artifact_type="report", relative_path="evidence/unapproved.json", checksum="sha256:unapproved", immutable=True, safe_metadata={"approval_status": "pending", "lineage": "run-1"}, created_at=now))
        session.commit()
    valid = AssistantContextService(session_scope_factory=scope, gateway=CitationGateway([{"artifact_id": "approved", "checksum": "sha256:approved", "stage_id": None}])).answer(AssistantMessageRequestDto(run_id="run-1", message="Where is the migration now?", idempotency_key="valid-citation"))
    assert valid.answer == "Cited answer."
    for key, citation in (("bad-checksum", {"artifact_id": "approved", "checksum": "sha256:wrong", "stage_id": None}), ("missing", {"artifact_id": "missing", "checksum": "sha256:none", "stage_id": None}), ("unapproved", {"artifact_id": "unapproved", "checksum": "sha256:unapproved", "stage_id": None}), ("foreign-stage", {"artifact_id": "approved", "checksum": "sha256:approved", "stage_id": "foreign-stage"})):
        with pytest.raises(Exception, match="citation"):
            AssistantContextService(session_scope_factory=scope, gateway=CitationGateway([citation])).answer(AssistantMessageRequestDto(run_id="run-1", message="Where is the migration now?", idempotency_key=key))
    engine.dispose()


def test_normal_assistant_composition_uses_production_application_service_without_mock_default(tmp_path):
    engine, scope, _ = setup(tmp_path)
    service = AssistantContextService(session_scope_factory=scope)
    assert isinstance(service._invocations, LlmEvidenceApplicationService)
    assert service._invocations.gateway is None
    engine.dispose()


def test_projection_statistics_distinguish_unavailable_from_persisted_zero(tmp_path):
    engine, scope, sessions = setup(tmp_path)
    from app.services.workflow_projection_service import WorkflowProjectionService
    with sessions() as session:
        projection = WorkflowProjectionService().build(session, "run-1")
        assert projection.operational_statistics.input_tokens is None
        now = datetime.now(UTC)
        session.add(LlmInvocationModel(id="zero-invocation", run_id="run-1", stage_id=None, idempotency_key="zero", request_checksum="sha256:zero", input_hashes=[], correlation_id="zero", actor="test", role="assistant", task_type="assistant_response", provider="fake", deployment_alias="fake", prompt_version="prompt", schema_version="schema", pricing_version="pricing", stage=None, redacted_summary=None, status="completed", failure_code=None, artifact_ids=[], artifact_checksums={}, state_version=3, event_sequence=1, retries=0, started_at=now, completed_at=now, created_at=now))
        session.add(UsageCostRecordModel(id="zero-usage", invocation_id="zero-invocation", run_id="run-1", stage_id=None, pricing_version="pricing", input_tokens=0, output_tokens=0, total_tokens=0, input_price_per_million=0, output_price_per_million=0, input_cost_usd=0, output_cost_usd=0, total_cost_usd=0, created_at=now))
        session.commit()
        projection = WorkflowProjectionService().build(session, "run-1")
        assert projection.operational_statistics.input_tokens == 0
        assert projection.operational_statistics.total_cost_usd == 0
    engine.dispose()
