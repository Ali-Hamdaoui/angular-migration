from starlette.requests import Request

from app.api.compatibility_contracts import FeasibilityResolveActionRequest
from app.api.routes import compatibility


def test_resolution_command_dispatches_the_durable_job(monkeypatch):
    dispatched: list[tuple[str, str]] = []
    monkeypatch.setattr(
        compatibility,
        "enqueue_planning_job",
        lambda _run_id, **_: {"job_id": "planning-run-1", "status": "queued_after_g04", "current_step": "resolving_feasibility", "correlation_id": "planning:run-1"},
    )
    monkeypatch.setattr(compatibility, "dispatch_planning_job", lambda run_id, *, worker_id: dispatched.append((run_id, worker_id)))
    request = Request({"type": "http", "method": "POST", "path": "/api/v1/runs/run-1/feasibility/actions/resolve", "headers": []})

    result = compatibility.queue_feasibility_resolution(
        "run-1",
        FeasibilityResolveActionRequest(expected_state_version=3, idempotency_key="resolve-1"),
        request,
        "operator",
    )

    assert result["job_id"] == "planning-run-1"
    assert dispatched == [("run-1", "feasibility-command")]
