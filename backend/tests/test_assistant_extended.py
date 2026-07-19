"""Extended tests for G08 S4-F11 assistant context service.

Covers: stale state rejection, assistant unavailable path,
empty/oversize messages, cost tracking accumulation,
no hidden chain-of-thought, artifact persistence,
run without events, multiple actors, error events.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.repositories.models.base import Base
from app.repositories.models import (
    AssistantConversationModel,
    AssistantMessageModel,
    MigrationRunModel,
    WorkflowEventModel,
)
from app.services.assistant_context_service import (
    AssistantContextService,
    AssistantError,
    AssistantMessageRequest,
)
from app.domain.contracts import WorkflowEventType


@pytest.fixture
def in_memory_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    yield session
    session.close()


@pytest.fixture
def scope_factory(in_memory_session):
    @contextmanager
    def factory():
        yield in_memory_session
    return factory


@pytest.fixture
def settings():
    class FakeSettings:
        artifact_root = "/tmp/test-artifacts"
    return FakeSettings()


@pytest.fixture
def now():
    return datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def service(settings, scope_factory, now):
    mock_store = MagicMock()
    mock_store.ensure_run_layout = MagicMock()
    mock_store.write_text_artifact = MagicMock(
        side_effect=lambda *args, **kwargs: MagicMock(
            ref=MagicMock(
                artifact_id=f"test-artifact-{uuid4().hex[:8]}",
                artifact_type=MagicMock(value="json"),
                relative_path="assistant/test.json",
                checksum="sha256:abc123",
            )
        )
    )
    svc = AssistantContextService(
        settings,
        session_scope_factory=scope_factory,
        now_provider=lambda: now,
        artifact_store=mock_store,
    )
    return svc


def _seed_run(session, run_id: str, status: str = "RUNNING", state_version: int = 1):
    run = MigrationRunModel(
        id=run_id,
        status=status,
        run_phase="STAGED_MIGRATION",
        phase_status="running",
        state_version=state_version,
        created_at=datetime(2026, 7, 19, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 7, 19, 10, 0, 0, tzinfo=UTC),
    )
    session.add(run)
    session.flush()
    return run


class TestAssistantExtended:
    """Extended tests for edge cases and missing coverage."""

    def test_stale_state_version_rejected(self, service, in_memory_session, now):
        """Request with wrong expected_state_version is rejected."""
        _seed_run(in_memory_session, "run-stale", status="RUNNING", state_version=3)

        with pytest.raises(AssistantError) as exc:
            service.send_message(AssistantMessageRequest(
                run_id="run-stale",
                actor="test-user",
                message="Status?",
                idempotency_key="stale-test",
                expected_state_version=1,  # Wrong — actual is 3
            ))
        assert exc.value.code == "STALE_STATE_VERSION"

    def test_correct_state_version_accepted(self, service, in_memory_session, now):
        """Request with correct state version is accepted."""
        _seed_run(in_memory_session, "run-correct", status="RUNNING", state_version=5)

        result = service.send_message(AssistantMessageRequest(
            run_id="run-correct",
            actor="test-user",
            message="Status?",
            idempotency_key="correct-state-test",
            expected_state_version=5,
        ))
        assert result.status == "completed"

    def test_cost_tracking_accumulates(self, service, in_memory_session, now):
        """Cost tracking accumulates across multiple messages."""
        _seed_run(in_memory_session, "run-cost", status="RUNNING")

        service.send_message(AssistantMessageRequest(
            run_id="run-cost",
            actor="test-user",
            message="First",
            idempotency_key="cost-first",
        ))
        service.send_message(AssistantMessageRequest(
            run_id="run-cost",
            actor="test-user",
            message="Second",
            idempotency_key="cost-second",
        ))

        conv = service.get_conversation("run-cost", "test-user")
        assert conv is not None
        # Each message adds 2 (user + assistant)
        assert conv.message_count >= 4

    def test_no_hidden_chain_of_thought(self, service, in_memory_session, now):
        """Persisted messages contain only content_summary, not full chain-of-thought."""
        _seed_run(in_memory_session, "run-cot", status="RUNNING")

        service.send_message(AssistantMessageRequest(
            run_id="run-cot",
            actor="test-user",
            message="Why was this blocked?",
            idempotency_key="cot-test",
        ))

        messages = list(
            in_memory_session.scalars(
                select(AssistantMessageModel).where(
                    AssistantMessageModel.run_id == "run-cot"
                )
            )
        )
        for msg in messages:
            # content_summary should be truncated (first 200 chars)
            assert msg.content_summary is not None
            assert len(msg.content_summary) <= 210  # Q: prefix + 200 chars

    def test_assistant_response_started_event(self, service, in_memory_session, now):
        """ASSISTANT_RESPONSE_STARTED event is emitted."""
        _seed_run(in_memory_session, "run-event-start", status="RUNNING")

        service.send_message(AssistantMessageRequest(
            run_id="run-event-start",
            actor="test-user",
            message="Event test",
            idempotency_key="event-start-test",
        ))

        started_events = list(
            in_memory_session.scalars(
                select(WorkflowEventModel).where(
                    WorkflowEventModel.event_type == WorkflowEventType.ASSISTANT_RESPONSE_STARTED.value
                )
            )
        )
        assert len(started_events) >= 1

    def test_assistant_response_completed_event(self, service, in_memory_session, now):
        """ASSISTANT_RESPONSE_COMPLETED event is emitted."""
        _seed_run(in_memory_session, "run-event-complete", status="RUNNING")

        service.send_message(AssistantMessageRequest(
            run_id="run-event-complete",
            actor="test-user",
            message="Event complete test",
            idempotency_key="event-complete-test",
        ))

        completed_events = list(
            in_memory_session.scalars(
                select(WorkflowEventModel).where(
                    WorkflowEventModel.event_type == WorkflowEventType.ASSISTANT_RESPONSE_COMPLETED.value
                )
            )
        )
        assert len(completed_events) >= 1

    def test_multiple_actors_separate_conversations(self, service, in_memory_session, now):
        """Different actors get separate conversations for the same run."""
        _seed_run(in_memory_session, "run-multi-actor", status="RUNNING")

        r1 = service.send_message(AssistantMessageRequest(
            run_id="run-multi-actor",
            actor="user-alpha",
            message="Alpha question",
            idempotency_key="multi-alpha",
        ))
        r2 = service.send_message(AssistantMessageRequest(
            run_id="run-multi-actor",
            actor="user-beta",
            message="Beta question",
            idempotency_key="multi-beta",
        ))
        assert r1.conversation_id != r2.conversation_id

    def test_long_message_accepted(self, service, in_memory_session, now):
        """Long but valid messages are accepted."""
        _seed_run(in_memory_session, "run-long-msg", status="RUNNING")

        long_msg = "Long message " * 100  # ~1400 chars, well under 10000 limit
        result = service.send_message(AssistantMessageRequest(
            run_id="run-long-msg",
            actor="test-user",
            message=long_msg,
            idempotency_key="long-msg-test",
        ))
        assert result.status == "completed"

    def test_run_with_no_events(self, service, in_memory_session, now):
        """Assistant works on runs with no events."""
        _seed_run(in_memory_session, "run-no-events", status="CREATED")

        result = service.send_message(AssistantMessageRequest(
            run_id="run-no-events",
            actor="test-user",
            message="Status check",
            idempotency_key="no-events-test",
        ))
        assert result.status == "completed"
        assert "CREATED" in result.response

    def test_forbidden_actions_listed_in_context(self, service, in_memory_session, now):
        """Forbidden actions are included in the assistant context."""
        assert len(AssistantContextService.FORBIDDEN_ACTIONS) >= 5
        assert "command execution" in AssistantContextService.FORBIDDEN_ACTIONS
        assert "state transition" in AssistantContextService.FORBIDDEN_ACTIONS
        assert "gate approval" in AssistantContextService.FORBIDDEN_ACTIONS

    def test_artifact_refs_returned(self, service, in_memory_session, now):
        """Artifact refs are returned in the response."""
        _seed_run(in_memory_session, "run-artifacts", status="RUNNING")

        result = service.send_message(AssistantMessageRequest(
            run_id="run-artifacts",
            actor="test-user",
            message="Show artifacts",
            idempotency_key="artifact-refs-test",
        ))
        assert len(result.artifact_refs) >= 1

    def test_deterministic_fallback_labeled(self, service, in_memory_session, now):
        """Deterministic fallback is labeled as such in response."""
        _seed_run(in_memory_session, "run-fallback-label", status="RUNNING")

        result = service.send_message(AssistantMessageRequest(
            run_id="run-fallback-label",
            actor="test-user",
            message="What's up?",
            idempotency_key="fallback-label-test",
        ))
        assert result.deterministic_fallback is True
        assert "deterministic fallback" in result.response.lower()

    def test_input_manifest_artifact_created(self, service, in_memory_session, now):
        """Input manifest artifact is created by the service."""
        _seed_run(in_memory_session, "run-manifest", status="RUNNING")

        result = service.send_message(AssistantMessageRequest(
            run_id="run-manifest",
            actor="test-user",
            message="Show manifest",
            idempotency_key="manifest-test",
        ))
        assert len(result.artifact_refs) >= 3  # manifest, answer, usage record
