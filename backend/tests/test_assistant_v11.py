"""Focused V1.1 Assistant vertical-slice contracts."""

import json
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.llm_contracts import LlmInvocationResponse
from app.domain.contracts import AssistantMessageRequestDto
from app.llm_gateway import LlmContextSegment
from app.repositories.models import AssistantMessageModel, Base, MigrationRunModel
from app.services.assistant_capabilities import (
    AssistantCapability,
    AssistantCapabilityRegistry,
    classify_intent,
    classify_semantic_intent,
    default_capability_registry,
)
from app.services.assistant_context_budget import build_bounded_context, count_tokens
from app.services.assistant_context_service import AssistantContextService, AssistantRequestError
from app.services.llm_evidence_application_service import _AssistantResponse
from app.services.llm_evidence_application_service import build_assistant_response_contract


def scope_for(tmp_path, actor="owner"):
    engine = create_engine(f"sqlite:///{tmp_path / 'v11.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as session:
        now = datetime.now(UTC)
        session.add(MigrationRunModel(id="run-v11", actor=actor, status="RUNNING", run_phase="FEASIBILITY_PLANNING", phase_status="running", state_version=4, created_at=now, updated_at=now))
        session.commit()

    def scope():
        from contextlib import contextmanager
        @contextmanager
        def managed():
            with sessions() as session:
                yield session
                session.commit()
        return managed()
    return engine, scope


def test_run_authorization_is_owner_bound(tmp_path):
    engine, scope = scope_for(tmp_path)
    service = AssistantContextService(session_scope_factory=scope)
    service.authorize("run-v11", "owner")
    with pytest.raises(HTTPException) as error:
        service.authorize("run-v11", "other-actor")
    assert error.value.status_code == 403
    engine.dispose()


def test_natural_intent_and_extensible_registry():
    assert classify_intent("What is the current migration state?") == "workflow_status"
    assert classify_intent("Why did this stop?") == "blocker_or_failure"
    for question in (
        "Why did it stop, and what should happen next?",
        "Why is the migration blocked?",
        "What is preventing progress?",
        "What is the next permitted action?",
        "Explain the blocker and the next step.",
    ):
        assert classify_intent(question) == "blocker_or_failure"
    assert classify_intent("Explain the latest validation failure.") == "validation_explanation"
    registry = AssistantCapabilityRegistry()
    registry.register(AssistantCapability("test_capability", frozenset({"test_intent"})))
    assert registry.get_for_intent("test_intent").capability_key == "test_capability"


def test_context_budget_manifest_bounds_input():
    segments = [LlmContextSegment(segment_id=f"s{i}", label="section", content="x" * 20_000) for i in range(10)]
    bounded = build_bounded_context(segments)
    assert bounded.manifest["total_tokens"] <= 40_000
    assert bounded.manifest["omitted_item_identifiers"]
    assert count_tokens("x" * 20_000) == 5_000


def test_request_supports_new_transport_and_retry_identity():
    request = AssistantMessageRequestDto(message="Why did this stop?", request_id="request-2", idempotency_key="request-2", retry_of_message_id="failed-1", answer_mode="detailed")
    assert request.request_id == "request-2"
    assert request.retry_of_message_id == "failed-1"
    assert request.answer_mode == "detailed"


def test_complete_v11_provider_contract_is_strict_and_read_only():
    valid = {
        "answer": "The migration is waiting for review.", "summary": "Waiting for review.",
        "intent": "workflow_status", "capability_key": "workflow_status",
        "proof_label": "authoritative_persisted_fact", "citations": [],
        "missing_information": [], "suggested_follow_ups": [], "next_step_proposals": [], "confidence": "high",
    }
    assert _AssistantResponse.model_validate(valid).model_dump() == valid
    with pytest.raises(ValidationError):
        _AssistantResponse.model_validate({**valid, "unexpected": True})
    with pytest.raises(ValidationError):
        _AssistantResponse.model_validate({**valid, "intent": "made_up"})
    with pytest.raises(ValidationError):
        _AssistantResponse.model_validate({**valid, "proof_label": "made_up"})
    with pytest.raises(ValidationError):
        _AssistantResponse.model_validate({**valid, "answer": ""})
    with pytest.raises(ValidationError):
        _AssistantResponse.model_validate({**valid, "next_step_proposals": [{"action_key": "x", "label": "x", "reason": "x", "target_route": "/x", "requires_human_approval": True, "executable_by_assistant": True}]})


def test_bound_provider_contract_contains_selected_intent_capability_and_excerpt_constraints():
    contract = build_assistant_response_contract(
        intent="evidence_question",
        capability_key="analysis",
        selected_excerpt_ids=["excerpt-selected"],
    )
    schema = contract.model_json_schema()
    assert schema["properties"]["intent"]["const"] == "evidence_question" or schema["properties"]["intent"]["enum"] == ["evidence_question"]
    assert schema["properties"]["capability_key"]["const"] == "analysis" or schema["properties"]["capability_key"]["enum"] == ["analysis"]
    citation = schema["$defs"]["BoundAssistantCitation"]
    assert citation["properties"]["excerpt_id"].get("const", citation["properties"]["excerpt_id"].get("enum")) == "excerpt-selected"


def test_bound_provider_contract_rejects_other_valid_intent_capability_and_missing_evidence_citation():
    contract = build_assistant_response_contract(
        intent="evidence_question",
        capability_key="analysis",
        selected_excerpt_ids=["excerpt-selected"],
    )
    valid = {
        "answer": "Evidence-backed answer.", "summary": "Evidence-backed answer.",
        "intent": "evidence_question", "capability_key": "analysis",
        "proof_label": "approved_evidence_supported", "citations": [{
            "excerpt_id": "excerpt-selected", "artifact_id": "artifact", "checksum_sha256": "sha256:x",
            "stage_key": "run", "locator": {"kind": "line_range", "value": "1-1"},
            "proof_label": "approved_evidence_supported",
        }], "missing_information": [], "suggested_follow_ups": [], "next_step_proposals": [], "confidence": "high",
    }
    with pytest.raises(ValidationError):
        contract.model_validate({**valid, "intent": "next_steps"})
    with pytest.raises(ValidationError):
        contract.model_validate({**valid, "capability_key": "next_steps"})
    with pytest.raises(ValidationError):
        contract.model_validate({**valid, "citations": []})
    with pytest.raises(ValidationError):
        contract.model_validate({**valid, "citations": [{**valid["citations"][0], "excerpt_id": "excerpt-other"}]})


def test_proof_label_policy_is_fail_closed_without_selected_evidence():
    evidence_policy = json.loads(default_capability_registry().get_for_intent("evidence_question").provider_policy(selected_intent="evidence_question", selected_excerpt_ids=[]))
    assert evidence_policy["allowed_proof_labels"] == ["unknown_or_unavailable"]
    evidence_contract = build_assistant_response_contract(intent="evidence_question", capability_key="analysis", selected_excerpt_ids=[])
    response = {"answer": "No usable approved evidence is available.", "summary": "No usable approved evidence is available.", "intent": "evidence_question", "capability_key": "analysis", "proof_label": "unknown_or_unavailable", "citations": [], "missing_information": [], "suggested_follow_ups": [], "next_step_proposals": [], "confidence": "low"}
    evidence_contract.model_validate(response)
    with pytest.raises(ValidationError):
        evidence_contract.model_validate({**response, "proof_label": "approved_evidence_supported"})
    status_policy = json.loads(default_capability_registry().get_for_intent("workflow_status").provider_policy(selected_intent="workflow_status", selected_excerpt_ids=[]))
    assert "approved_evidence_supported" not in status_policy["allowed_proof_labels"]


def test_empty_selected_evidence_contract_forbids_citations_and_no_synthetic_excerpt_id():
    contract = build_assistant_response_contract(intent="workflow_status", capability_key="workflow_status", selected_excerpt_ids=[])
    schema = contract.model_json_schema()
    assert schema["properties"]["citations"].get("maxItems") == 0
    citation = schema["$defs"]["BoundAssistantCitation"]
    assert "__no_selected_excerpt__" not in json.dumps(citation)


def test_workflow_status_provider_citations_are_normalized_to_empty_and_succeeds(tmp_path):
    _, scope = scope_for(tmp_path)
    output = {"answer": "The migration is waiting for review.", "summary": "Waiting for review.", "intent": "workflow_status", "capability_key": "workflow_status", "proof_label": "authoritative_persisted_fact", "citations": [{"excerpt_id": "__no_selected_excerpt__", "artifact_id": "metadata-artifact", "checksum_sha256": "sha256:metadata", "stage_key": "run", "locator": {"kind": "json_pointer", "value": "/source_validation_result.json"}, "proof_label": "approved_evidence_supported"}], "missing_information": [], "suggested_follow_ups": [], "next_step_proposals": [], "confidence": "high"}

    class Invocation:
        def assistant(self, request, *, actor=None):
            return LlmInvocationResponse(invocation_id="inv-empty", run_id=request.run_id, status="completed", role="assistant", task_type="assistant_response", provider="governed_gateway", deployment_alias="gpt-5-mini", structured_output=output, correlation_id=request.correlation_id, input_tokens=2, output_tokens=3, total_tokens=5, input_cost_usd=0, output_cost_usd=0, total_cost_usd=0, state_version=4, event_sequence=7)

    result = AssistantContextService(session_scope_factory=scope, invocation_service=Invocation()).answer(AssistantMessageRequestDto(run_id="run-v11", message="Explain the current migration state and what is waiting now.", idempotency_key="empty-evidence"), actor="owner", correlation_id="corr-empty")
    assert result.response_status == "completed"
    assert result.intent == "workflow_status"
    assert result.capability_key == "workflow_status"
    assert result.citations == []
    assert result.model == "gpt-5-mini"


def test_failed_citation_path_preserves_resolved_v11_metadata(tmp_path):
    _, scope = scope_for(tmp_path)
    output = {"answer": "Evidence answer.", "summary": "Evidence answer.", "intent": "evidence_question", "capability_key": "analysis", "proof_label": "approved_evidence_supported", "citations": [{"excerpt_id": "not-selected", "artifact_id": "artifact", "checksum_sha256": "sha256:x", "stage_key": "run", "locator": {"kind": "line_range", "value": "1-1"}, "proof_label": "approved_evidence_supported"}], "missing_information": [], "suggested_follow_ups": [], "next_step_proposals": [], "confidence": "high"}

    class Invocation:
        def assistant(self, request, *, actor=None):
            return LlmInvocationResponse(invocation_id="inv-failed", run_id=request.run_id, status="completed", role="assistant", task_type="assistant_response", provider="governed_gateway", deployment_alias="gpt-5-mini", structured_output=output, correlation_id=request.correlation_id, input_tokens=2, output_tokens=3, total_tokens=5, input_cost_usd=0, output_cost_usd=0, total_cost_usd=0, state_version=4, event_sequence=7)

    service = AssistantContextService(session_scope_factory=scope, invocation_service=Invocation())
    service._evidence_retrieval.retrieve = lambda session, run_id, question: ([LlmContextSegment(segment_id="excerpt-selected", label="approved evidence", content="approved", artifact_ref="excerpt-selected", untrusted=True)], [{"excerpt_id": "excerpt-selected", "artifact_id": "artifact", "checksum_sha256": "sha256:x", "stage_key": "run", "locator": {"kind": "line_range", "value": "1-1"}, "proof_label": "approved_evidence_supported", "text": "approved", "label": "evidence.json"}])
    with pytest.raises(AssistantRequestError) as error:
        service.answer(AssistantMessageRequestDto(run_id="run-v11", message="What evidence supports this?", idempotency_key="failed-metadata", request_id="request-failed"), actor="owner", correlation_id="corr-failed")
    assert error.value.code == "assistant_invalid_citation"
    with scope() as session:
        row = session.scalar(select(AssistantMessageModel).where(AssistantMessageModel.idempotency_key == "failed-metadata"))
        assert row.intent == "evidence_question"
        assert row.capability_key == "analysis"
        assert row.request_id == "request-failed"
        assert row.correlation_id == "corr-failed"
        assert row.model_provenance["deployment"] == "gpt-5-mini"


def test_all_supported_intents_have_one_registry_capability_and_extension_is_pipeline_independent():
    registry = default_capability_registry()
    for intent in ("workflow_status", "blocker_or_failure", "completed_work", "remaining_work", "analysis_explanation", "planning_explanation", "transformation_explanation", "validation_explanation", "evidence_question", "usage_and_cost", "next_steps", "comparison"):
        assert registry.dispatch(classify_semantic_intent(f"Explain {intent.replace('_', ' ')}")) is not None or registry.get_for_intent(intent) is not None
    extension = AssistantCapability("test_future_read_only", frozenset({"future_intent"}))
    registry.register(extension)
    assert registry.get_for_intent("future_intent") is extension


def test_structured_response_round_trips_through_post_history_and_restart(tmp_path):
    _, scope = scope_for(tmp_path)
    structured = {"answer": "Waiting for review.", "summary": "Review is pending.", "intent": "workflow_status", "capability_key": "workflow_status", "proof_label": "authoritative_persisted_fact", "citations": [], "missing_information": ["reviewer decision"], "suggested_follow_ups": ["Ask for the review outcome."], "next_step_proposals": [{"action_key": "review_gate", "label": "Review gate", "reason": "A human decision is required.", "target_route": "/runs/{run_id}/planning/review", "requires_human_approval": True, "executable_by_assistant": False}], "confidence": "high"}

    class Invocation:
        def __init__(self):
            self.calls = 0

        def assistant(self, request, *, actor=None):
            self.calls += 1
            return LlmInvocationResponse(invocation_id="inv-1", run_id=request.run_id, status="completed", role="assistant", task_type="assistant_response", provider="test", deployment_alias="test", structured_output=structured, correlation_id=request.correlation_id, input_tokens=2, output_tokens=3, total_tokens=5, input_cost_usd=0.1, output_cost_usd=0.2, total_cost_usd=0.3, state_version=4, event_sequence=7)

    invocation = Invocation()
    service = AssistantContextService(session_scope_factory=scope, invocation_service=invocation)
    request = AssistantMessageRequestDto(run_id="run-v11", message="Where is the migration now?", idempotency_key="round-trip")
    first = service.answer(request, actor="owner", correlation_id="corr-round-trip")
    restored = AssistantContextService(session_scope_factory=scope, invocation_service=invocation).history("run-v11", first.conversation_id, actor="owner").messages[-1]
    assert invocation.calls == 1
    assert first.model_dump(include={"answer", "summary", "intent", "capability_key", "proof_label", "citations", "missing_information", "suggested_follow_ups", "next_step_proposals", "confidence", "correlation_id"}) == restored.model_dump(include={"answer", "summary", "intent", "capability_key", "proof_label", "citations", "missing_information", "suggested_follow_ups", "next_step_proposals", "confidence", "correlation_id"})
    assert restored.request_id == "round-trip"
    assert restored.semantic_state_version == 4
    assert restored.answer_mode == "concise"


def test_legacy_message_fallback_does_not_fabricate_structured_facts_or_citations(tmp_path):
    engine, scope = scope_for(tmp_path)
    with scope() as session:
        session.add(AssistantMessageModel(
            id="legacy-row", message_id="legacy-message", conversation_id="legacy-conversation", run_id="run-v11",
            message_order=1, role="assistant", input_manifest={}, input_manifest_checksum="legacy-checksum",
            answer="A historical answer.", state_version=4, projection={"phase": "unknown"}, evidence=[],
            proof_label="unknown_or_unavailable", usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "estimated_input_cost": 0, "estimated_output_cost": 0, "estimated_total_cost": 0},
            model_provenance={"role": "assistant"}, correlation_id="legacy-correlation", idempotency_key="legacy-key",
            status="completed", created_at=datetime.now(UTC), request_id="legacy-request", semantic_state_version=4,
            operational_event_sequence=0, intent="workflow_status", capability_key="workflow_status", answer_mode="concise",
        ))
    restored = AssistantContextService(session_scope_factory=scope).history("run-v11", "legacy-conversation", actor="owner").messages[0]
    assert restored.answer == "A historical answer."
    assert restored.summary == "unavailable"
    assert restored.citations == []
    assert restored.missing_information == ["V1.1 metadata unavailable for this legacy message"]
    assert restored.confidence == "unknown_or_unavailable"
    assert restored.capability_key == ""
    engine.dispose()
