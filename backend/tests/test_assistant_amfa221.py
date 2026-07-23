from contextlib import contextmanager
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.domain.contracts import AgentKind, AssistantMessageRequestDto
from app.llm_gateway import LlmResponse, LlmRole, LlmTaskType, PromptRedactionResult, build_usage_record
from app.main import app
from app.repositories.models import ArtifactMetadataModel, AssistantLifecycleEventModel, AssistantMessageModel, Base, LlmInvocationModel, MigrationRunModel, UsageCostRecordModel, WorkflowEventModel
from app.services.assistant_context_service import AssistantContextService
from app.api.routes import assistant as assistant_routes


class Gateway:
    def complete(self, request):
        usage = build_usage_record(run_id=request.run_id, stage_id=None, agent_kind=AgentKind.ASSISTANT, task_type=LlmTaskType.ASSISTANT_RESPONSE, model_deployment_alias="test-assistant", input_tokens=10, output_tokens=5, input_price_per_million=0.25, output_price_per_million=2.0)
        return LlmResponse(response_id="response", request_id=request.request_id, run_id=request.run_id, agent_kind=AgentKind.ASSISTANT, task_type=LlmTaskType.ASSISTANT_RESPONSE, model_deployment_alias="test-assistant", status="completed", summary="validated", usage=usage, redaction=PromptRedactionResult(redacted_text="safe", redaction_count=0), role=LlmRole.ASSISTANT, prompt_version="prompt", schema_version="schema", pricing_version="pricing")


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
            assert [item["message_id"] for item in history.json()["messages"]] == [first_body["message_id"], second.json()["message_id"]]
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
    assert [message.message_id for message in restored.messages] == [first.message_id, follow_up.message_id]
    assert [message.usage.total_tokens for message in restored.messages] == [first.usage.total_tokens, follow_up.usage.total_tokens]
    with restarted_sessions() as session:
        events = list(session.scalars(select(AssistantLifecycleEventModel).where(AssistantLifecycleEventModel.run_id == "run-1").order_by(AssistantLifecycleEventModel.sequence)))
        assert len(events) == 4
    with restarted_sessions() as session:
        run = session.get(MigrationRunModel, "run-1")
        run.state_version = 4
        session.commit()
    stale_history = restored_service.history("run-1", first.conversation_id)
    assert all(message.stale for message in stale_history.messages)
    assert stale_history.messages[0].workflow_state_version == first.workflow_state_version
    newer = restored_service.answer(AssistantMessageRequestDto(run_id="run-1", conversation_id=first.conversation_id, message="Where is the migration now?", idempotency_key="restart-3", client_known_state_version=4))
    assert newer.workflow_state_version == 4
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
    assert "G02 Source Integrity Approval" in current.answer
    assert "G02 pending" in current.answer
    assert "Current gate: G02 pending." in current.answer
    assert "G02 pending (pending)" not in current.answer
    assert "Workflow state version: " in current.answer
    assert "reviewer decision required for G02" in current.answer
    assert "There is no technical blocker" in current.answer
    assert "Record a G02 reviewer decision through the governed cockpit control" in current.answer
    assert "unknown" not in current.answer.lower()
    assert "Source intake" in completed.answer and "Source snapshot" in completed.answer
    assert "unknown" not in completed.answer.lower()
    assert current.usage.total_tokens == 0
    assert current.usage.estimated_total_cost == 0
    assert operations.usage.total_tokens == 0
    assert [item.artifact_id for item in current.evidence_references] == ["artifact-snapshot", "artifact-integrity", "artifact-g02"]
    assert "Recorded workflow duration: " in operations.answer
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
    assert replay.messages[0].answer == result.answer
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
