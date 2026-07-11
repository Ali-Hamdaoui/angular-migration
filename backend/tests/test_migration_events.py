"""Tests for ordered mock Server-Sent Events, replay, and recovery."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.mock_event_service import (
    ReplayUnavailableError,
    format_sse_event,
    generate_mock_events,
    replay_events,
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
    return [event async for event in generate_mock_events(run_id, delay=0, include_heartbeat=False)]


def test_mock_event_sequence_covers_every_event_type_with_monotonic_sequences() -> None:
    events = asyncio.run(_collect_events("mock-run-angular-18-to-21"))
    emitted_types = {event.event_type.value for event in events}
    assert EXPECTED_EVENT_TYPES.issubset(emitted_types)
    assert all(event.run_id == "mock-run-angular-18-to-21" for event in events)
    assert [event.sequence for event in events] == list(range(1, 10))
    assert len(events) == 9


def test_format_sse_event_produces_id_event_and_valid_json_payload() -> None:
    events = asyncio.run(_collect_events("mock-run-angular-18-to-21"))
    block = format_sse_event(events[0])
    assert block.startswith("id: 1\nevent: run_state_changed\n")
    assert "data: " in block
    assert block.endswith("\n\n")
    data_line = block.split("data: ", 1)[1].strip()
    payload = json.loads(data_line)
    assert payload["event_type"] == "run_state_changed"
    assert payload["sequence"] == 1
    assert payload["payload"]["status"] == "RUNNING"


def test_replay_returns_only_events_after_last_event_id() -> None:
    events = replay_events("mock-run-angular-18-to-21", last_event_id=6)
    assert [event.sequence for event in events] == [7, 8, 9]


def test_replay_outside_retention_raises_gap_signal() -> None:
    with pytest.raises(ReplayUnavailableError):
        replay_events("mock-run-angular-18-to-21", last_event_id=1, retention=3)


def test_sse_endpoint_returns_text_event_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.mock_event_service.MOCK_EVENT_DELAY_SECONDS", 0)
    response = client.get("/migrations/mock-run-angular-18-to-21/events")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]


def test_sse_endpoint_emits_all_mock_event_types_and_heartbeat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.mock_event_service.MOCK_EVENT_DELAY_SECONDS", 0)
    response = client.get("/migrations/mock-run-angular-18-to-21/events")
    body = response.text
    emitted_types: set[str] = set()
    for line in body.splitlines():
        if line.startswith("event: "):
            emitted_types.add(line.removeprefix("event: "))
    assert EXPECTED_EVENT_TYPES.issubset(emitted_types)
    assert "heartbeat" in emitted_types


def test_sse_endpoint_replays_from_last_event_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.mock_event_service.MOCK_EVENT_DELAY_SECONDS", 0)
    response = client.get("/migrations/mock-run-angular-18-to-21/events", headers={"Last-Event-ID": "7"})
    ids = [line.removeprefix("id: ") for line in response.text.splitlines() if line.startswith("id: ")]
    assert ids == ["8", "9"]


def test_sse_endpoint_reports_replay_unavailable_when_retention_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.mock_event_service.MOCK_EVENT_DELAY_SECONDS", 0)
    monkeypatch.setattr("app.api.routes.migrations.get_settings", lambda: type("Settings", (), {"sse_replay_retention_events": 3})())
    response = client.get("/migrations/mock-run-angular-18-to-21/events", headers={"Last-Event-ID": "1"})
    assert "event: replay_unavailable" in response.text
    assert "snapshot_required" in response.text


def test_sse_event_data_contains_valid_json_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.mock_event_service.MOCK_EVENT_DELAY_SECONDS", 0)
    response = client.get("/migrations/mock-run-angular-18-to-21/events")
    data_lines = [line.removeprefix("data: ") for line in response.text.splitlines() if line.startswith("data: ")]
    event_payloads = [json.loads(raw) for raw in data_lines if "event_id" in raw]
    assert len(event_payloads) == 9
    for payload in event_payloads:
        assert "event_id" in payload
        assert "run_id" in payload
        assert "event_type" in payload
        assert "occurred_at" in payload
        assert "sequence" in payload
        assert "payload" in payload


def test_sse_endpoint_includes_no_cache_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.mock_event_service.MOCK_EVENT_DELAY_SECONDS", 0)
    response = client.get("/migrations/mock-run-angular-18-to-21/events")
    assert response.headers["cache-control"] == "no-cache"
