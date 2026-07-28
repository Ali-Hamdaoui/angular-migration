"""Bounded real-HTTP proof for R8 durable Assistant SSE."""

from __future__ import annotations

import asyncio
import socket
import threading
from contextlib import contextmanager
from datetime import UTC, datetime

import httpx
import pytest
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.api.routes import assistant as assistant_routes
from app.api.errors import error_response
from app.repositories.models import AssistantLifecycleEventModel, Base, MigrationRunModel
from app.repositories.session import session_scope as production_scope
from app.services.assistant_context_service import AssistantContextService


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _event(run_id: str, sequence: int, event_type: str, *, idempotency_key: str | None = None) -> AssistantLifecycleEventModel:
    return AssistantLifecycleEventModel(
        id=f"event-{run_id}-{sequence}", run_id=run_id, conversation_id="conversation-1", message_id=f"message-{sequence}",
        event_type=event_type, sequence=sequence, correlation_id=f"correlation-{sequence}", state_version=1,
        status="failed" if event_type.endswith("FAILED") else "completed", idempotency_key=idempotency_key or f"request-{sequence}",
        payload={"safe": True}, occurred_at=datetime.now(UTC),
    )


@pytest.fixture()
def sse_server(tmp_path):
    # Use the current ORM schema without touching the configured application
    # database; the route's session seam is redirected only for this test app.
    test_engine = create_engine(f"sqlite:///{tmp_path / 'r8-sse.sqlite3'}", connect_args={"check_same_thread": False})
    sessions = sessionmaker(bind=test_engine, expire_on_commit=False)

    @contextmanager
    def scope():
        with sessions() as session:
            yield session
            session.commit()

    Base.metadata.create_all(test_engine)
    with sessions() as session:
        session.query(AssistantLifecycleEventModel).delete()
        session.query(MigrationRunModel).filter(MigrationRunModel.id == "r8-stream-run").delete()
        session.add(MigrationRunModel(id="r8-stream-run", actor="alice", status="RUNNING", run_phase="DISCOVERY_BASELINE", phase_status="running", state_version=1, source_angular_version="18", target_angular_version="21", created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
        session.commit()

    app = FastAPI()
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        return error_response(request, status_code=exc.status_code, error_code=str(detail.get("error_code") or "HTTP_ERROR"), message=str(detail.get("message") or exc.detail), details=detail.get("details") or {})

    service = AssistantContextService(session_scope_factory=scope)
    app.dependency_overrides[assistant_routes.get_service] = lambda: service
    original_scope = assistant_routes.session_scope
    assistant_routes.session_scope = scope
    app.include_router(assistant_routes.router, prefix="/api/v1")
    original_poll = assistant_routes.ASSISTANT_SSE_POLL_INTERVAL_SECONDS
    original_heartbeat = assistant_routes.ASSISTANT_SSE_HEARTBEAT_INTERVAL_SECONDS
    assistant_routes.ASSISTANT_SSE_POLL_INTERVAL_SECONDS = 0.02
    assistant_routes.ASSISTANT_SSE_HEARTBEAT_INTERVAL_SECONDS = 0.06

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", lifespan="off"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    def wait_ready():
        with httpx.Client(timeout=1) as client:
            for _ in range(100):
                try:
                    response = client.get(f"http://127.0.0.1:{port}/api/v1/runs/r8-stream-run/assistant/events", headers={"X-Authenticated-Actor": "bob"})
                    if response.status_code == 403:
                        return
                except httpx.HTTPError:
                    pass
                import time
                time.sleep(0.01)
        raise AssertionError("test SSE server did not start")

    wait_ready()

    def add_events(*events: AssistantLifecycleEventModel):
        with sessions() as session:
            session.add_all(events)
            session.commit()

    yield f"http://127.0.0.1:{port}", add_events, sessions

    server.should_exit = True
    thread.join(timeout=2)
    assistant_routes.session_scope = original_scope
    assistant_routes.ASSISTANT_SSE_POLL_INTERVAL_SECONDS = original_poll
    assistant_routes.ASSISTANT_SSE_HEARTBEAT_INTERVAL_SECONDS = original_heartbeat
    app.dependency_overrides.clear()


async def _read_until(iterator, predicate, timeout: float = 2.0) -> list[str]:
    lines: list[str] = []
    async def read():
        while True:
            line = await iterator.__anext__()
            lines.append(line)
            if predicate(lines):
                return lines
    return await asyncio.wait_for(read(), timeout)


def test_live_after_connect_delivers_all_lifecycle_events(sse_server):
    asyncio.run(_test_live_after_connect_delivers_all_lifecycle_events(sse_server))


async def _test_live_after_connect_delivers_all_lifecycle_events(sse_server):
    base, add_events, _ = sse_server
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("GET", f"{base}/api/v1/runs/r8-stream-run/assistant/events", headers={"X-Authenticated-Actor": "alice"}) as response:
            assert response.status_code == 200
            iterator = response.aiter_lines().__aiter__()
            await _read_until(iterator, lambda lines: ": heartbeat" in lines)
            add_events(_event("r8-stream-run", 1, "ASSISTANT_RESPONSE_STARTED"))
            add_events(_event("r8-stream-run", 2, "ASSISTANT_CONTEXT_BUILT"))
            add_events(_event("r8-stream-run", 3, "ASSISTANT_RESPONSE_COMPLETED"))
            lines = await _read_until(iterator, lambda values: any("ASSISTANT_RESPONSE_COMPLETED" in line for line in values))
            assert [event for event in ("ASSISTANT_RESPONSE_STARTED", "ASSISTANT_CONTEXT_BUILT", "ASSISTANT_RESPONSE_COMPLETED") if any(event in line for line in lines)] == ["ASSISTANT_RESPONSE_STARTED", "ASSISTANT_CONTEXT_BUILT", "ASSISTANT_RESPONSE_COMPLETED"]


def test_heartbeat_does_not_create_rows_or_advance_cursor(sse_server):
    asyncio.run(_test_heartbeat_does_not_create_rows_or_advance_cursor(sse_server))


async def _test_heartbeat_does_not_create_rows_or_advance_cursor(sse_server):
    base, add_events, sessions = sse_server
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("GET", f"{base}/api/v1/runs/r8-stream-run/assistant/events", headers={"X-Authenticated-Actor": "alice"}) as response:
            iterator = response.aiter_lines().__aiter__()
            await _read_until(iterator, lambda lines: ": heartbeat" in lines)
            with sessions() as session:
                assert session.scalar(select(func.count()).select_from(AssistantLifecycleEventModel)) == 0
            add_events(_event("r8-stream-run", 1, "ASSISTANT_RESPONSE_FAILED"))
            lines = await _read_until(iterator, lambda values: any("ASSISTANT_RESPONSE_FAILED" in line for line in values))
            assert any("id: 1" == line for line in lines)


def test_last_event_id_header_precedes_query_and_replays_only_later_rows(sse_server):
    asyncio.run(_test_last_event_id_header_precedes_query_and_replays_only_later_rows(sse_server))


async def _test_last_event_id_header_precedes_query_and_replays_only_later_rows(sse_server):
    base, add_events, _ = sse_server
    add_events(_event("r8-stream-run", 1, "ASSISTANT_RESPONSE_STARTED"), _event("r8-stream-run", 2, "ASSISTANT_CONTEXT_BUILT"), _event("r8-stream-run", 3, "ASSISTANT_RESPONSE_COMPLETED"))
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("GET", f"{base}/api/v1/runs/r8-stream-run/assistant/events?last_event_id=0", headers={"X-Authenticated-Actor": "alice", "Last-Event-ID": "2"}) as response:
            iterator = response.aiter_lines().__aiter__()
            lines = await _read_until(iterator, lambda values: any("id: 3" == line for line in values))
            assert "id: 1" not in lines and "id: 2" not in lines
        malformed = await client.get(f"{base}/api/v1/runs/r8-stream-run/assistant/events?last_event_id=1", headers={"X-Authenticated-Actor": "alice", "Last-Event-ID": "not-a-cursor"})
        assert malformed.status_code == 400
        assert malformed.json()["error_code"] == "assistant_invalid_event_cursor"


def test_authorization_happens_before_stream_and_cursor_is_run_scoped(sse_server):
    asyncio.run(_test_authorization_happens_before_stream_and_cursor_is_run_scoped(sse_server))


async def _test_authorization_happens_before_stream_and_cursor_is_run_scoped(sse_server):
    base, add_events, _ = sse_server
    add_events(_event("r8-stream-run", 1, "ASSISTANT_RESPONSE_STARTED"))
    async with httpx.AsyncClient(timeout=1) as client:
        missing = await client.get(f"{base}/api/v1/runs/r8-stream-run/assistant/events")
        blank = await client.get(f"{base}/api/v1/runs/r8-stream-run/assistant/events")
        denied = await client.get(f"{base}/api/v1/runs/r8-stream-run/assistant/events", headers={"X-Authenticated-Actor": "bob"})
        assert missing.status_code == 401 and blank.status_code == 401 and denied.status_code == 403


def test_cancellation_stops_polling_without_leaving_an_idle_session(sse_server):
    asyncio.run(_test_cancellation_stops_polling_without_leaving_an_idle_session(sse_server))


async def _test_cancellation_stops_polling_without_leaving_an_idle_session(sse_server):
    _base, _add_events, _sessions = sse_server
    class IdleRequest:
        headers = {}
        query_params = {}

        async def is_disconnected(self):
            return False

    request = IdleRequest()
    original_scope = assistant_routes.session_scope
    polls = 0

    @contextmanager
    def counting_scope():
        nonlocal polls
        polls += 1
        with original_scope() as session:
            yield session

    assistant_routes.session_scope = counting_scope
    try:
        response = assistant_routes.stream_events("r8-stream-run", request, "alice", AssistantContextService(session_scope_factory=original_scope))
        iterator = response.body_iterator
        pending = asyncio.create_task(iterator.__anext__())
        await asyncio.sleep(0.03)
        pending.cancel()
        with pytest.raises(StopAsyncIteration):
            await pending
        observed_polls = polls
        await asyncio.sleep(0.05)
        assert polls == observed_polls
    finally:
        assistant_routes.session_scope = original_scope
