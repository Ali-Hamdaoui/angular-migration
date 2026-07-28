"""Focused V1.1 Assistant vertical-slice contracts."""

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.contracts import AssistantMessageRequestDto
from app.repositories.models import Base, MigrationRunModel
from app.services.assistant_capabilities import AssistantCapability, AssistantCapabilityRegistry, classify_intent
from app.services.assistant_context_budget import build_bounded_context, count_tokens
from app.services.assistant_context_service import AssistantContextService
from app.llm_gateway import LlmContextSegment


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
    assert classify_intent("Explain the latest validation failure.") == "blocker_or_failure"
    assert classify_intent("explain") == "general_migration_question"
    assert classify_intent("Compare the migration evidence in plain language") == "general_migration_question"
    registry = AssistantCapabilityRegistry()
    registry.register(AssistantCapability("test_capability", frozenset({"test_intent"})))
    assert registry.get_for_intent("test_intent").capability_key == "test_capability"


def test_read_only_migration_paraphrases_do_not_hit_the_unsupported_classifier():
    questions = [
        "explain",
        "why",
        "Give me a plain-language summary",
        "Compare the current state with the target",
        "What evidence matters most?",
        "What changed since the last gate?",
        "Are there risks I should review?",
        "Summarize the migration for a developer",
        "How confident is the current evidence?",
        "What should I understand before the next decision?",
    ]
    assert all(classify_intent(question) != "unsupported" for question in questions)


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


def test_failed_provider_response_keeps_code_and_safe_azure_diagnostics():
    response = type("Response", (), {"failure_code": "LLM_PROVIDER_FAILURE", "provider": "azure_openai", "deployment_alias": "assistant-deployment", "prompt_version": "assistant-response-v1", "schema_version": "assistant-response-v1", "provider_http_status": 503, "provider_error_code": "upstream_error", "sanitized_provider_message": "safe provider message", "provider_request_id": "azure-request-1", "failure_stage": "http_response", "failure_subtype": "HTTP_ERROR_ENVELOPE", "retryable": True, "response_received": True, "response_kind": "json", "transport_started": True})()
    error = AssistantContextService._provider_failure(response)
    provenance = AssistantContextService._provider_provenance(response)
    assert (error.code, error.status_code) == ("LLM_PROVIDER_FAILURE", 503)
    assert provenance["provider"] == "azure_openai"
    assert provenance["deployment"] == "assistant-deployment"
    assert provenance["diagnostics"]["request_id"] == "azure-request-1"


def test_protocol_provider_failure_maps_to_bad_gateway():
    response = type("Response", (), {"failure_code": "protocol", "deployment_alias": "assistant-deployment", "failure_stage": "response_contract_validation", "failure_subtype": "MISSING_STRUCTURED_CONTENT", "retryable": False, "provider_request_id": "azure-request-2", "provider_http_status": None, "provider_error_code": "missing_structured_content", "sanitized_provider_message": "safe shape diagnostic", "response_kind": "json", "response_received": True, "transport_started": True})()
    error = AssistantContextService._provider_failure(response)
    assert error.status_code == 502
    assert error.details["failure_subtype"] == "MISSING_STRUCTURED_CONTENT"
