"""Tests for the mock Server-Sent Events endpoint and event service."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.mock_event_service import (
    generate_mock_events,
    format_sse_event,
)

client = TestClient(app)

EXPECTED_EVENT_TYPES = {
    "run_state_changed",
    "stage_state_changed",
    "agent_state_changed",
    "validation_gate_changed",
    "artifact_created",
    "approval_required",
    "workflow_completed",
}


async def _collect_events(run_id: str) -> list:
    return [event async for event in generate_mock_events(run_id, delay=0)]


def test_mock_event_sequence_covers_every_event_type() -> None:
    events = asyncio.run(_collect_events("mock-run-angular-18-to-21"))
    emitted_types = {event.event_type.value for event in events}
    assert EXPECTED_EVENT_TYPES.issubset(emitted_types)
    assert all(event.run_id == "mock-run-angular-18-to-21" for event in events)
    assert len(events) == 9


def test_format_sse_event_produces_valid_sse_block() -> None:
    events = asyncio.run(_collect_events("mock-run-angular-18-to-21"))
    block = format_sse_event(events[0])
    assert block.startswith("event: run_state_changed\n")
    assert "data: " in block
    assert block.endswith("\n\n")
    data_line = block.split("data: ", 1)[1].strip()
    payload = json.loads(data_line)
    assert payload["event_type"] == "run_state_changed"
    assert payload["payload"]["status"] == "RUNNING"


def test_sse_endpoint_returns_text_event_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.mock_event_service.MOCK_EVENT_DELAY_SECONDS", 0
    )
    response = client.get("/migrations/mock-run-angular-18-to-21/events")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]


def test_sse_endpoint_emits_all_mock_event_types(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.mock_event_service.MOCK_EVENT_DELAY_SECONDS", 0
    )
    response = client.get("/migrations/mock-run-angular-18-to-21/events")
    body = response.text
    emitted_types: set[str] = set()
    for line in body.splitlines():
        if line.startswith("event: "):
            emitted_types.add(line.removeprefix("event: "))
    assert EXPECTED_EVENT_TYPES.issubset(emitted_types)


def test_sse_event_data_contains_valid_json_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.mock_event_service.MOCK_EVENT_DELAY_SECONDS", 0
    )
    response = client.get("/migrations/mock-run-angular-18-to-21/events")
    data_lines = [
        line.removeprefix("data: ")
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert len(data_lines) == 9
    for raw in data_lines:
        payload = json.loads(raw)
        assert "event_id" in payload
        assert "run_id" in payload
        assert "event_type" in payload
        assert "occurred_at" in payload
        assert "payload" in payload


def test_sse_endpoint_includes_no_cache_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.mock_event_service.MOCK_EVENT_DELAY_SECONDS", 0
    )
    response = client.get("/migrations/mock-run-angular-18-to-21/events")
    assert response.headers["cache-control"] == "no-cache"
