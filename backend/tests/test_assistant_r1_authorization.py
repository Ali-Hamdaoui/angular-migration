from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.api.llm_contracts import LlmInvocationResponse
from app.api.routes import assistant as assistant_routes
from app.domain.contracts import AssistantMessageRequestDto
from app.main import app
from app.repositories.models import (
    AssistantConversationModel,
    AssistantLifecycleEventModel,
    AssistantMessageModel,
    Base,
    LlmInvocationModel,
    MigrationRunModel,
    UsageCostRecordModel,
)
from app.services.assistant_context_service import AssistantContextService


class InvocationSpy:
    def __init__(self):
        self.calls = 0

    def assistant(self, request, *, actor):
        self.calls += 1
        return LlmInvocationResponse(
            invocation_id=f"invocation-{self.calls}",
            run_id=request.run_id,
            status="completed",
            role="assistant",
            task_type="assistant_response",
            provider="fake",
            deployment_alias="fake",
            structured_output={"answer": "Owner answer.", "summary": "Owner answer.", "intent": "workflow_status", "capability_key": "workflow_status", "proof_label": "authoritative_persisted_fact", "citations": [], "missing_information": [], "suggested_follow_ups": [], "next_step_proposals": [], "confidence": "high"},
            correlation_id=request.correlation_id,
            prompt_version="prompt",
            schema_version="schema",
            pricing_version="pricing",
            input_tokens=1,
            output_tokens=1,
            total_tokens=2,
            input_cost_usd=0,
            output_cost_usd=0,
            total_cost_usd=0,
            state_version=1,
            event_sequence=1,
        )


def isolated_app(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'r1.db'}")
    Base.metadata.create_all(engine)
    AssistantLifecycleEventModel.__table__.create(engine, checkfirst=True)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as session:
        session.add(MigrationRunModel(
            id="run-owned-by-alice",
            actor="alice",
            status="WAITING",
            run_phase="FEASIBILITY_PLANNING",
            phase_status="waiting_approval",
            state_version=1,
            source_angular_version="18.x",
            target_angular_version="21.x",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ))
        session.commit()

    @contextmanager
    def scope():
        with sessions() as session:
            yield session
            session.commit()

    spy = InvocationSpy()
    service = AssistantContextService(session_scope_factory=scope, invocation_service=spy)
    app.dependency_overrides[assistant_routes.get_service] = lambda: service

    @asynccontextmanager
    async def test_lifespan(_app):
        yield

    original_lifespan = app.router.lifespan_context
    original_event_scope = assistant_routes.session_scope
    app.router.lifespan_context = test_lifespan
    assistant_routes.session_scope = scope
    return engine, sessions, spy, service, original_lifespan, original_event_scope


def counts(sessions):
    with sessions() as session:
        return {
            "conversations": session.scalar(select(func.count()).select_from(AssistantConversationModel)),
            "messages": session.scalar(select(func.count()).select_from(AssistantMessageModel)),
            "events": session.scalar(select(func.count()).select_from(AssistantLifecycleEventModel)),
            "invocations": session.scalar(select(func.count()).select_from(LlmInvocationModel)),
            "usage": session.scalar(select(func.count()).select_from(UsageCostRecordModel)),
        }


def test_missing_identity_is_rejected_before_any_assistant_side_effect(tmp_path):
    engine, sessions, spy, _, original_lifespan, original_event_scope = isolated_app(tmp_path)
    try:
        before = counts(sessions)
        with TestClient(app) as client:
            response = client.post("/api/v1/runs/run-owned-by-alice/assistant/messages", json={"message": "status"})
        assert response.status_code == 401
        assert response.json()["error_code"] == "assistant_authentication_required"
        assert response.json()["correlation_id"]
        assert counts(sessions) == before
        assert spy.calls == 0
    finally:
        app.dependency_overrides.pop(assistant_routes.get_service, None)
        app.router.lifespan_context = original_lifespan
        assistant_routes.session_scope = original_event_scope
        engine.dispose()


@pytest.mark.parametrize("path", [
    "/api/v1/runs/run-owned-by-alice/assistant/messages",
    "/api/v1/runs/run-owned-by-alice/assistant/events",
])
def test_missing_identity_is_rejected_on_history_and_events(tmp_path, path):
    engine, sessions, spy, _, original_lifespan, original_event_scope = isolated_app(tmp_path)
    try:
        before = counts(sessions)
        with TestClient(app) as client:
            response = client.get(path)
        assert response.status_code == 401
        assert response.json()["error_code"] == "assistant_authentication_required"
        assert counts(sessions) == before
        assert spy.calls == 0
    finally:
        app.dependency_overrides.pop(assistant_routes.get_service, None)
        app.router.lifespan_context = original_lifespan
        assistant_routes.session_scope = original_event_scope
        engine.dispose()


def test_blank_identity_is_rejected_on_history_and_events(tmp_path):
    engine, _, _, _, original_lifespan, original_event_scope = isolated_app(tmp_path)
    try:
        with TestClient(app) as client:
            responses = [
                client.post("/api/v1/runs/run-owned-by-alice/assistant/messages", headers={"X-Authenticated-Actor": "  "}, json={"message": "status"}),
                client.get("/api/v1/runs/run-owned-by-alice/assistant/messages", headers={"X-Authenticated-Actor": "  "}),
                client.get("/api/v1/runs/run-owned-by-alice/assistant/events", headers={"X-Authenticated-Actor": "  "}),
            ]
            for response in responses:
                assert response.status_code == 401
                assert response.json()["error_code"] == "assistant_authentication_required"
    finally:
        app.dependency_overrides.pop(assistant_routes.get_service, None)
        app.router.lifespan_context = original_lifespan
        assistant_routes.session_scope = original_event_scope
        engine.dispose()


def test_cross_actor_is_rejected_before_reads_or_provider_on_all_routes(tmp_path):
    engine, sessions, spy, _, original_lifespan, original_event_scope = isolated_app(tmp_path)
    try:
        before = counts(sessions)
        with TestClient(app) as client:
            for method, path in (
                ("post", "/api/v1/runs/run-owned-by-alice/assistant/messages"),
                ("get", "/api/v1/runs/run-owned-by-alice/assistant/messages"),
                ("get", "/api/v1/runs/run-owned-by-alice/assistant/events"),
            ):
                if method == "post":
                    response = client.post(path, headers={"X-Authenticated-Actor": "bob"}, json={"message": "status"})
                else:
                    response = client.get(path, headers={"X-Authenticated-Actor": "bob"})
                assert response.status_code == 403
                assert response.json()["error_code"] == "assistant_run_forbidden"
                assert response.json()["correlation_id"]
        assert counts(sessions) == before
        assert spy.calls == 0
    finally:
        app.dependency_overrides.pop(assistant_routes.get_service, None)
        app.router.lifespan_context = original_lifespan
        assistant_routes.session_scope = original_event_scope
        engine.dispose()


def test_owner_is_authorized_on_post_history_and_events(tmp_path):
    engine, _, spy, _, original_lifespan, original_event_scope = isolated_app(tmp_path)
    try:
        with TestClient(app) as client:
            headers = {"X-Authenticated-Actor": "alice"}
            post = client.post("/api/v1/runs/run-owned-by-alice/assistant/messages", headers=headers, json={"message": "status", "idempotency_key": "r1-owner"})
            assert post.status_code == 201
            assert client.get("/api/v1/runs/run-owned-by-alice/assistant/messages", headers=headers).status_code == 200
            # Long-lived stream opening and bounded consumption are proven by
            # the real-Uvicorn R8 route tests; TestClient.get would wait for
            # response completion by design.
        assert spy.calls == 1
    finally:
        app.dependency_overrides.pop(assistant_routes.get_service, None)
        app.router.lifespan_context = original_lifespan
        assistant_routes.session_scope = original_event_scope
        engine.dispose()


def test_direct_service_cannot_use_local_operator_bypass(tmp_path):
    engine, sessions, _, service, original_lifespan, original_event_scope = isolated_app(tmp_path)
    try:
        with pytest.raises(HTTPException) as error:
            service.answer(AssistantMessageRequestDto(run_id="run-owned-by-alice", message="status", idempotency_key="local-operator"), actor="local-operator")
        assert error.value.status_code == 403
        with pytest.raises(HTTPException) as error:
            service.history("run-owned-by-alice", actor="local-operator")
        assert error.value.status_code == 403
        assert counts(sessions) == {"conversations": 0, "messages": 0, "events": 0, "invocations": 0, "usage": 0}
    finally:
        app.dependency_overrides.pop(assistant_routes.get_service, None)
        app.router.lifespan_context = original_lifespan
        assistant_routes.session_scope = original_event_scope
        engine.dispose()


def test_authenticated_absent_run_returns_existing_404_contract(tmp_path):
    engine, _, _, _, original_lifespan, original_event_scope = isolated_app(tmp_path)
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/runs/absent-run/assistant/messages", headers={"X-Authenticated-Actor": "alice"})
        assert response.status_code == 404
        assert response.json()["error_code"] == "RUN_NOT_FOUND"
    finally:
        app.dependency_overrides.pop(assistant_routes.get_service, None)
        app.router.lifespan_context = original_lifespan
        assistant_routes.session_scope = original_event_scope
        engine.dispose()
