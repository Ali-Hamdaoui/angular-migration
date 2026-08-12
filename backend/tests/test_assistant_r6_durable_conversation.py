"""Focused R6 persistence, isolation, semantic freshness, and failure proof."""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.domain.contracts import AgentKind, AssistantMessageRequestDto, WorkflowEventType
from app.llm_gateway import LlmResponse, LlmRole, LlmTaskType, PromptRedactionResult, build_usage_record
from app.repositories.models import (
    AssistantLifecycleEventModel,
    AssistantMessageModel,
    Base,
    LlmInvocationModel,
    MigrationRunModel,
    UsageCostRecordModel,
)
from app.services.assistant_capabilities import classify_semantic_intent, default_capability_registry
from app.services.assistant_context_service import AssistantContextService, AssistantRequestError
from app.state.transition_service import StateTransitionService, TransitionRequest


def test_authoritative_failure_answer_preserves_governed_repair_boundary() -> None:
    answer = AssistantContextService._authoritative_failure_answer(
        {
            "blocker": "COMMAND_EXIT_NONZERO",
            "latest_command_result": {"command_key": "angular-update-exact", "status": "failed", "exit_code": 1, "failure_code": "COMMAND_EXIT_NONZERO"},
            "failure_classification": "angular_update_peer_conflict",
            "failure_reason": "Jest peer dependency conflict.\nYou can use the '--force' option to ignore it.",
            "repair_state": "attempt 1 accepted by reviewer; G10 approval required",
            "phase": "Transformation", "stage": "20-to-21", "gate": "G10", "status": "WAITING_GATE",
            "next_action": "Approve or reject the accepted repair proposal at G10.",
        }
    )

    assert "angular-update-exact" in answer
    assert "exit code 1" in answer
    assert "G10" in answer
    assert "--force" not in answer
    assert "do not bypass" in answer


def test_terminal_completed_failure_answer_does_not_promote_successful_command() -> None:
    answer = AssistantContextService._authoritative_failure_answer(
        {
            "blocker": "none",
            "latest_command_result": {
                "command_key": "final-validation",
                "status": "succeeded",
                "exit_code": 0,
                "failure_code": None,
            },
            "failure_classification": "unknown",
            "failure_reason": "unknown",
            "repair_state": "validation_passed",
            "phase": "Completion",
            "stage": "sealed-stage",
            "gate": "final approved",
            "status": "COMPLETED",
            "next_action": "Review final evidence and reporting.",
        }
    )

    assert "Current blocker: none" in answer
    assert "Current failed command: none" in answer
    assert "final-validation" not in answer
    assert "Failed command:" not in answer
    assert "not applicable because there is no current failure" in answer
    assert "Historical/resolved failures" in answer
    assert "historical/resolved only and are not current" in answer
    assert "no repair or gate approval is currently required" in answer
    assert "Review final evidence and reporting" in answer
    assert "read-only" in answer


def test_explicit_migration_plan_question_routes_to_planning():
    result = classify_semantic_intent("Explain the migration plan and its main risks or repair points.")
    assert result.intent == "planning_explanation"
    capability = default_capability_registry().get_for_intent(result.intent)
    assert capability is not None
    policy = json.loads(capability.provider_policy(selected_intent=result.intent, selected_excerpt_ids=["excerpt-plan"]))
    assert any("risks" in item for item in policy["required_answer_content"])


def test_completed_migration_summary_routes_to_completed_work_contract():
    result = classify_semantic_intent(
        "Summarize the completed migration: what changed, what validations passed, what Angular version is installed, and is the stage sealed?"
    )
    assert result.intent == "completed_work"
    capability = default_capability_registry().get_for_intent(result.intent)
    assert capability is not None
    policy = json.loads(capability.provider_policy(selected_intent=result.intent, selected_excerpt_ids=[]))
    assert "state whether the stage is sealed" in policy["required_answer_content"]
    assert "state the dependency-closure outcome" in policy["required_answer_content"]
    assert "cite the final sealed workspace fingerprint when known" in policy["required_answer_content"]


def test_completion_answer_includes_dependency_closure_and_sealed_workspace_evidence():
    answer = AssistantContextService._authoritative_completion_answer({
        "run_id": "run-complete",
        "current_angular_version": "21.2.19",
        "target_angular_version": "21.x",
        "migration_route": "20→21",
        "completed_phases": ["Dependency closure passed", "Final npm install passed", "Production build passed", "Tests passed"],
        "status": "COMPLETED",
        "phase": "Completion",
        "stage": "stage-20-21",
        "gate": "unknown",
        "stage_fingerprint": "sha256:sealed-workspace",
    })
    assert "Dependency closure passed" in answer
    assert "fingerprint sha256:sealed-workspace" in answer
    assert "stage is sealed" in answer


def test_deterministic_completion_response_retains_v11_metadata_without_provider_artifact():
    structured = {
        "answer": "Stage is sealed.", "summary": "Stage is sealed.",
        "intent": "completed_work", "capability_key": "workflow_status",
        "proof_label": "authoritative_persisted_fact", "missing_information": [],
    }
    row = SimpleNamespace(model_provenance={"assistant_v11": {"deterministic_structured_response": structured}})
    assert AssistantContextService._structured_response(row, None) == structured


class DeterministicGateway:
    def __init__(self, *, failure: bool = False, started: threading.Event | None = None, release: threading.Event | None = None):
        self.failure = failure
        self.started = started
        self.release = release
        self.calls = 0

    def complete(self, request):
        self.calls += 1
        if self.started:
            self.started.set()
        if self.release:
            self.release.wait(timeout=10)
        if self.failure:
            from app.llm_gateway.azure_gateway import AzureGatewayError, LlmFailureCode
            raise AzureGatewayError(LlmFailureCode.PROVIDER, "controlled provider failure")
        question = json.loads(request.prepared_input["serialized_input"])["question"]
        intent = classify_semantic_intent(question).intent
        capability = default_capability_registry().get_for_intent(intent)
        usage = build_usage_record(run_id=request.run_id, stage_id=None, agent_kind=AgentKind.ASSISTANT, task_type=LlmTaskType.ASSISTANT_RESPONSE, model_deployment_alias="r6-test", input_tokens=3, output_tokens=5, input_price_per_million=0, output_price_per_million=0)
        return LlmResponse(response_id=f"r6-response-{self.calls}", request_id=request.request_id, run_id=request.run_id, agent_kind=AgentKind.ASSISTANT, task_type=LlmTaskType.ASSISTANT_RESPONSE, model_deployment_alias="r6-test", status="completed", summary="r6", structured_output={"answer": "R6 durable answer", "summary": "R6 durable answer", "intent": intent, "capability_key": capability.capability_key if capability else "", "proof_label": "authoritative_persisted_fact", "citations": [], "missing_information": [], "suggested_follow_ups": [], "next_step_proposals": [], "confidence": "high"}, usage=usage, redaction=PromptRedactionResult(redacted_text="safe", redaction_count=0), role=LlmRole.ASSISTANT, prompt_version="r6", schema_version="assistant-response-v1", pricing_version="r6")


def setup(tmp_path, gateway):
    engine = create_engine(f"sqlite:///{tmp_path / 'r6.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    now = datetime.now(UTC)
    with sessions.begin() as session:
        session.add(MigrationRunModel(id="r6-run", status="RUNNING", run_phase="DISCOVERY_BASELINE", phase_status="running", approval_status="not_required", repair_status="not_required", state_version=1, source_path="r6-source", target_output_path="r6-target", actor="r6-actor", created_at=now, updated_at=now, graph_thread_id="r6-thread", artifact_root=str(tmp_path / "artifacts")))

    @contextmanager
    def scope():
        with sessions() as session:
            yield session
            session.commit()

    return engine, scope, sessions, AssistantContextService(session_scope_factory=scope, gateway=gateway)


def request(message, key, conversation_id=None):
    return AssistantMessageRequestDto(run_id="r6-run", message=message, idempotency_key=key, request_id=key, conversation_id=conversation_id)


def test_pending_user_is_visible_from_a_separate_session_before_provider_completion(tmp_path):
    started, release = threading.Event(), threading.Event()
    engine, _scope, sessions, service = setup(tmp_path, DeterministicGateway(started=started, release=release))
    result = {}

    def invoke():
        result["response"] = service.answer(request("Where is the migration now?", "pending-1"), actor="r6-actor")

    worker = threading.Thread(target=invoke)
    worker.start()
    assert started.wait(timeout=10)
    with sessions() as session:
        rows = list(session.scalars(select(AssistantMessageModel).where(AssistantMessageModel.run_id == "r6-run").order_by(AssistantMessageModel.message_order)))
        assert len(rows) == 1
        assert rows[0].role == "user" and rows[0].status == "pending"
        conversation_id = rows[0].conversation_id
        assert rows[0].request_id == "pending-1"
    release.set(); worker.join(timeout=10)
    assert result["response"].conversation_id == conversation_id
    with sessions() as session:
        rows = list(session.scalars(select(AssistantMessageModel).where(AssistantMessageModel.conversation_id == conversation_id).order_by(AssistantMessageModel.message_order)))
        assert [row.role for row in rows] == ["user", "assistant"]
    engine.dispose()


def test_failure_is_durable_and_survives_service_restart(tmp_path):
    engine, _scope, sessions, service = setup(tmp_path, DeterministicGateway(failure=True))
    with pytest.raises(AssistantRequestError):
        service.answer(request("Where is the migration now?", "failure-1"), actor="r6-actor")
    with sessions() as session:
        rows = list(session.scalars(select(AssistantMessageModel).where(AssistantMessageModel.run_id == "r6-run").order_by(AssistantMessageModel.message_order)))
        assert [row.role for row in rows] == ["user", "assistant"]
        assert rows[1].status == "failed"
        assert rows[1].model_provenance["failure_code"] == "assistant_provider_failed"
        correlation_id = rows[1].correlation_id
    restarted_engine = create_engine(f"sqlite:///{tmp_path / 'r6.db'}", connect_args={"check_same_thread": False})
    restarted_sessions = sessionmaker(bind=restarted_engine, expire_on_commit=False)

    @contextmanager
    def restarted_scope():
        with restarted_sessions() as session:
            yield session
            session.commit()

    restored = AssistantContextService(session_scope_factory=restarted_scope, gateway=DeterministicGateway())
    history = restored.history("r6-run", actor="r6-actor")
    assert history.messages[-1].response_status == "failed"
    assert history.messages[-1].error_code == "assistant_provider_failed"
    assert history.messages[-1].correlation_id == correlation_id
    restarted_engine.dispose(); engine.dispose()


def test_history_isolation_latest_resolution_ordering_and_cross_run_unavailable(tmp_path):
    engine, _scope, sessions, service = setup(tmp_path, DeterministicGateway())
    with sessions.begin() as session:
        other = MigrationRunModel(id="other-run", status="RUNNING", run_phase="DISCOVERY_BASELINE", phase_status="running", approval_status="not_required", repair_status="not_required", state_version=1, actor="r6-actor", created_at=datetime.now(UTC), updated_at=datetime.now(UTC))
        session.add(other)
    a = service.answer(request("Where is the migration now?", "iso-a", "conversation-a"), actor="r6-actor")
    b = service.answer(request("Where is the migration now?", "iso-b", "conversation-b"), actor="r6-actor")
    assert {m.conversation_id for m in service.history("r6-run", "conversation-a", actor="r6-actor").messages} == {"conversation-a"}
    assert {m.conversation_id for m in service.history("r6-run", "conversation-b", actor="r6-actor").messages} == {"conversation-b"}
    latest = service.history("r6-run", actor="r6-actor")
    assert latest.conversation_id == "conversation-b"
    assert [m.message_order for m in latest.messages] == sorted(m.message_order for m in latest.messages)
    assert service.history("other-run", "conversation-a", actor="r6-actor").messages == []
    assert a.message_id != b.message_id
    engine.dispose()


def test_telemetry_does_not_stale_but_governed_semantic_transition_does(tmp_path):
    engine, _scope, sessions, service = setup(tmp_path, DeterministicGateway())
    answer = service.answer(request("Where is the migration now?", "stale-1"), actor="r6-actor")
    current = service.history("r6-run", answer.conversation_id, actor="r6-actor")
    assert all(not message.stale for message in current.messages)
    with sessions.begin() as session:
        assert session.scalar(select(LlmInvocationModel).where(LlmInvocationModel.run_id == "r6-run")) is not None
        assert session.scalar(select(UsageCostRecordModel).where(UsageCostRecordModel.run_id == "r6-run")) is not None
        run = session.get(MigrationRunModel, "r6-run")
        StateTransitionService(session).apply_transition(TransitionRequest(run_id="r6-run", expected_state_version=run.state_version, idempotency_key="semantic-1", event_type=WorkflowEventType.RUN_STATE_CHANGED, actor="r6-actor", reason="R6 semantic transition"))
    stale = service.history("r6-run", answer.conversation_id, actor="r6-actor")
    assert all(message.stale for message in stale.messages)
    assert all(message.semantic_state_version == 1 for message in stale.messages)
    engine.dispose()


def test_r6_control_surface_is_harness_only():
    from app.main import app as production_app
    from tests.browser_harness.r6_app import app as harness_app
    from tests.browser_harness.r6_app import fixed_actor

    assert not any(path.startswith("/__test__/r6/") for path in production_app.openapi()["paths"])
    assert any(path.startswith("/__test__/r6/") for path in harness_app.openapi()["paths"])
    assert fixed_actor() == "r6-browser-actor"
