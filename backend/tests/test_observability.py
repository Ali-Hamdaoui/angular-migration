from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.domain.contracts import AlertSeverity, AlertType, MigrationEventDto, WorkflowEventType
from app.observability import build_diagnostics_summary, mock_alert
from app.services.mock_migration_service import get_mock_migration_run


def metric(summary, name: str):
    return next(item for item in summary.metrics if item.metric_name == name)


def test_diagnostics_summary_aggregates_run_metrics_without_sensitive_labels() -> None:
    run = get_mock_migration_run()
    events = [
        MigrationEventDto(
            event_id="evt-reconnect",
            run_id=run.run_id,
            stage_id="angular-18-to-19",
            event_type=WorkflowEventType.RUN_STATE_CHANGED,
            occurred_at=datetime.now(UTC),
            payload={"reconnected": True, "secret": "do-not-label"},
        )
    ]

    summary = build_diagnostics_summary(run, events=events)

    assert metric(summary, "command.count").value == 1
    assert metric(summary, "artifact.count").value == 1
    assert metric(summary, "sse.reconnect.count").value == 1
    assert metric(summary, "llm.call.count").value == 1
    assert metric(summary, "llm.cost.total").value == 0.00094
    assert all("secret" not in item.labels for item in summary.metrics)
    assert summary.notes == ["Diagnostics are derived from canonical records and are not workflow state."]


def test_diagnostics_summary_filters_stage_metrics() -> None:
    run = get_mock_migration_run()

    summary = build_diagnostics_summary(run, stage_id="angular-19-to-20")

    assert summary.stage_id == "angular-19-to-20"
    assert metric(summary, "command.count").value == 0
    assert metric(summary, "artifact.count").value == 0


def test_mock_alert_event_vocabulary() -> None:
    alert = mock_alert("run-1", AlertType.SQLITE_CONTENTION, severity=AlertSeverity.CRITICAL)

    assert alert.alert_type == AlertType.SQLITE_CONTENTION
    assert alert.severity == AlertSeverity.CRITICAL
    assert "SQLite" in alert.message
    assert alert.correlation_id == "corr-run-1"


def test_diagnostics_endpoint_is_queryable_by_run_and_stage() -> None:
    client = TestClient(app)

    response = client.get("/migrations/mock-run-angular-18-to-21/diagnostics", params={"stage_id": "angular-18-to-19"})

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "mock-run-angular-18-to-21"
    assert body["stage_id"] == "angular-18-to-19"
    assert any(item["metric_name"] == "command.count" for item in body["metrics"])