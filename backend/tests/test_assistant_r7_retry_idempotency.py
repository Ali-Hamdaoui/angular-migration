"""R7 red/green proof: user retry is distinct from transport replay."""

from __future__ import annotations

import threading

import pytest
from sqlalchemy import select

from app.domain.contracts import AssistantMessageRequestDto
from app.repositories.models import AssistantMessageModel, LlmInvocationModel
from app.services.assistant_context_service import AssistantContextService, AssistantRequestError
from tests.test_assistant_r6_durable_conversation import DeterministicGateway, setup


def _request(message: str, key: str, conversation_id: str | None = None, **extra):
    message = extra.pop("message", message)
    return AssistantMessageRequestDto(
        run_id="r6-run",
        message=message,
        idempotency_key=key,
        request_id=key,
        conversation_id=conversation_id,
        **extra,
    )


def _failed(service, gateway, scope, sessions):
    with pytest.raises(AssistantRequestError) as error:
        service.answer(_request("Where is the migration now?", "r7-original"), actor="r6-actor")
    assert error.value.code == "assistant_provider_failed"
    assert error.value.correlation_id
    assert error.value.details["message_id"]
    with sessions() as session:
        failed = session.scalar(select(AssistantMessageModel).where(AssistantMessageModel.status == "failed"))
        assert failed is not None
        return failed.message_id, failed.conversation_id


def test_user_retry_links_failed_message_and_is_a_new_attempt(tmp_path):
    engine, scope, sessions, service = setup(tmp_path, DeterministicGateway(failure=True))
    failed_id, conversation_id = _failed(service, None, scope, sessions)

    gateway = DeterministicGateway()
    retry_service = AssistantContextService(session_scope_factory=scope, gateway=gateway)
    result = retry_service.answer(
        _request(
            "Where is the migration now?",
            "r7-retry",
            conversation_id,
            retry_of_message_id=failed_id,
        ),
        actor="r6-actor",
    )

    assert result.request_id == "r7-retry"
    assert result.retry_of_message_id == failed_id
    with sessions() as session:
        rows = list(session.scalars(select(AssistantMessageModel).where(AssistantMessageModel.conversation_id == conversation_id).order_by(AssistantMessageModel.message_order)))
        assert [row.role for row in rows] == ["user", "assistant", "user", "assistant"]
        assert rows[1].status == "failed"
        assert rows[3].retry_of_message_id == failed_id
        assert rows[1].message_id != rows[3].message_id
    assert gateway.calls == 1
    engine.dispose()


def test_failed_transport_replay_returns_same_failure_without_new_attempt(tmp_path):
    engine, scope, sessions, service = setup(tmp_path, DeterministicGateway(failure=True))
    failed_id, conversation_id = _failed(service, None, scope, sessions)
    replay_service = AssistantContextService(session_scope_factory=scope, gateway=DeterministicGateway())
    replay = replay_service.answer(_request("Where is the migration now?", "r7-original", conversation_id), actor="r6-actor")
    assert replay.message_id == failed_id
    assert replay.response_status == "failed"
    with sessions() as session:
        assert len(list(session.scalars(select(AssistantMessageModel)))) == 2
        assert len(list(session.scalars(select(LlmInvocationModel)))) == 1
        assert session.scalar(select(AssistantMessageModel).where(AssistantMessageModel.message_id == failed_id)).status == "failed"
    engine.dispose()


def test_identical_questions_with_distinct_transport_ids_are_independent(tmp_path):
    engine, scope, sessions, service = setup(tmp_path, DeterministicGateway())
    first = service.answer(_request("Where is the migration now?", "r7-independent-1"), actor="r6-actor")
    second = service.answer(_request("Where is the migration now?", "r7-independent-2"), actor="r6-actor")
    assert first.message_id != second.message_id
    with sessions() as session:
        assert len(list(session.scalars(select(LlmInvocationModel)))) == 2
    engine.dispose()


def test_same_key_changed_retry_link_is_a_conflict(tmp_path):
    engine, scope, sessions, service = setup(tmp_path, DeterministicGateway(failure=True))
    failed_id, conversation_id = _failed(service, None, scope, sessions)
    success = AssistantContextService(session_scope_factory=scope, gateway=DeterministicGateway()).answer(
        _request("Where is the migration now?", "r7-retry-conflict", conversation_id, retry_of_message_id=failed_id), actor="r6-actor"
    )
    with pytest.raises(AssistantRequestError) as error:
        service.answer(_request("Where is the migration now?", "r7-retry-conflict", conversation_id), actor="r6-actor")
    assert error.value.code == "assistant_idempotency_conflict"
    assert success.retry_of_message_id == failed_id
    with sessions() as session:
        assert len(list(session.scalars(select(LlmInvocationModel)))) == 2
    engine.dispose()


@pytest.mark.parametrize("change", [{"answer_mode": "detailed"}, {"message": "changed question"}])
def test_same_idempotency_key_changed_logical_payload_is_stable_conflict(tmp_path, change):
    engine, scope, sessions, service = setup(tmp_path, DeterministicGateway())
    first = service.answer(_request("Where is the migration now?", "r7-conflict"), actor="r6-actor")
    with pytest.raises(AssistantRequestError) as error:
        changed_message = change.get("message", "Where is the migration now?")
        changed_mode = change.get("answer_mode", "concise")
        service.answer(_request(changed_message, "r7-conflict", first.conversation_id, answer_mode=changed_mode), actor="r6-actor")
    assert error.value.code == "assistant_idempotency_conflict"
    with sessions() as session:
        assert len(list(session.scalars(select(LlmInvocationModel)))) == 1
    engine.dispose()


def test_duplicate_arrival_while_provider_blocked_has_one_attempt(tmp_path):
    started, release = threading.Event(), threading.Event()
    gateway = DeterministicGateway(started=started, release=release)
    engine, scope, sessions, service = setup(tmp_path, gateway)
    errors = []

    def invoke():
        try:
            service.answer(_request("Where is the migration now?", "r7-blocked"), actor="r6-actor")
        except Exception as error:  # pragma: no cover - assertion below records the stable branch
            errors.append(error)

    first = threading.Thread(target=invoke)
    first.start()
    assert started.wait(timeout=10)
    with pytest.raises(AssistantRequestError) as duplicate:
        service.answer(_request("Where is the migration now?", "r7-blocked"), actor="r6-actor")
    assert duplicate.value.code == "assistant_request_in_progress"
    release.set()
    first.join(timeout=10)
    assert not errors
    assert gateway.calls == 1
    with sessions() as session:
        assert len(list(session.scalars(select(AssistantMessageModel)))) == 2
    engine.dispose()


@pytest.mark.parametrize("target_kind", ["missing", "user", "completed"])
def test_retry_target_must_be_the_same_failed_assistant_message(tmp_path, target_kind):
    engine, scope, sessions, service = setup(tmp_path, DeterministicGateway())
    original = service.answer(_request("Where is the migration now?", "r7-target"), actor="r6-actor")
    with sessions() as session:
        if target_kind == "missing":
            target = "does-not-exist"
        elif target_kind == "user":
            target = session.scalar(select(AssistantMessageModel).where(AssistantMessageModel.role == "user")).message_id
        else:
            target = original.message_id
    with pytest.raises(AssistantRequestError) as error:
        service.answer(_request("Where is the migration now?", "r7-invalid-retry", original.conversation_id, retry_of_message_id=target), actor="r6-actor")
    assert error.value.code in {"assistant_retry_target_not_found", "assistant_retry_target_invalid"}
    engine.dispose()
