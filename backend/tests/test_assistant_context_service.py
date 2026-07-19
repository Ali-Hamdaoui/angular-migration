"""Tests for G08 S4-F11 assistant context service."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.repositories.models.base import Base
from app.repositories.models import (
    AssistantConversationModel,
    AssistantMessageModel,
    MigrationRunModel,
)
from app.services.assistant_context_service import (
    AssistantContextService,
    AssistantError,
    AssistantMessageRequest,
)


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


def _seed_run(session, run_id: str, status: str = "RUNNING"):
    run = MigrationRunModel(
        id=run_id,
        status=status,
        run_phase="STAGED_MIGRATION",
        phase_status="running",
        state_version=1,
        created_at=datetime(2026, 7, 19, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 7, 19, 10, 0, 0, tzinfo=UTC),
    )
    session.add(run)
    session.flush()
    return run


class TestAssistantContextService:
    def test_send_message_happy_path(self, service, in_memory_session, now):
        """Happy path: send message and get assistant response."""
        _seed_run(in_memory_session, "run-001")

        result = service.send_message(AssistantMessageRequest(
            run_id="run-001",
            actor="test-user",
            message="What is the current status?",
            idempotency_key="test-key-001",
        ))

        assert result.status == "completed"
        assert result.deterministic_fallback is True
        assert "Run Status:" in result.response
        assert result.conversation_id.startswith("conv-")

    def test_send_message_run_not_found(self, service, in_memory_session, now):
        """Sending message to non-existent run raises error."""
        with pytest.raises(AssistantError) as exc:
            service.send_message(AssistantMessageRequest(
                run_id="nonexistent-run",
                actor="test-user",
                message="Hello?",
                idempotency_key="test-key-002",
            ))
        assert exc.value.code == "RUN_NOT_FOUND"

    def test_deterministic_fallback_content(self, service, in_memory_session, now):
        """Deterministic fallback response includes authoritative state."""
        _seed_run(in_memory_session, "run-002", status="COMPLETED")

        result = service.send_message(AssistantMessageRequest(
            run_id="run-002",
            actor="test-user",
            message="Show me evidence",
            idempotency_key="test-key-003",
        ))

        assert result.deterministic_fallback is True
        assert "COMPLETED" in result.response
        assert "Forbidden actions" in result.response

    def test_conversation_tracks_metadata(self, service, in_memory_session, now):
        """Conversation metadata is persisted across messages."""
        _seed_run(in_memory_session, "run-003")

        result1 = service.send_message(AssistantMessageRequest(
            run_id="run-003",
            actor="test-user",
            message="First question",
            idempotency_key="test-key-004",
        ))

        result2 = service.send_message(AssistantMessageRequest(
            run_id="run-003",
            actor="test-user",
            message="Second question",
            idempotency_key="test-key-005",
        ))

        assert result1.conversation_id == result2.conversation_id

        conv = in_memory_session.get(AssistantConversationModel, result1.conversation_id)
        assert conv is not None
        assert conv.message_count >= 4

    def test_get_conversation(self, service, in_memory_session, now):
        """get_conversation returns conversation info."""
        _seed_run(in_memory_session, "run-004")

        result = service.send_message(AssistantMessageRequest(
            run_id="run-004",
            actor="test-user",
            message="Test message",
            idempotency_key="test-key-006",
        ))

        conv = service.get_conversation("run-004", "test-user")
        assert conv is not None
        assert conv.conversation_id == result.conversation_id
        assert conv.message_count >= 2

    def test_get_conversation_not_found(self, service, in_memory_session, now):
        """get_conversation returns None for non-existent conversation."""
        conv = service.get_conversation("run-999", "test-user")
        assert conv is None

    def test_suggested_questions_included(self, service, in_memory_session, now):
        """Suggested questions appear in the deterministic response."""
        _seed_run(in_memory_session, "run-005")

        result = service.send_message(AssistantMessageRequest(
            run_id="run-005",
            actor="test-user",
            message="What can I ask?",
            idempotency_key="test-key-007",
            suggested_questions=["What is the status?", "Show recent events"],
        ))

        assert "What is the status?" in result.response
        assert "Show recent events" in result.response

    def test_forbidden_actions_included(self, service, in_memory_session, now):
        """Forbidden actions policy is included in response."""
        _seed_run(in_memory_session, "run-006")

        result = service.send_message(AssistantMessageRequest(
            run_id="run-006",
            actor="test-user",
            message="Execute something",
            idempotency_key="test-key-008",
        ))

        assert "command execution" in result.response.lower()
        assert "state transition" in result.response.lower()
