"""Non-authoritative run diagnostics derived from canonical workflow records."""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.contracts import (
    AlertEventDto,
    AlertSeverity,
    AlertType,
    DiagnosticsSummaryDto,
    MigrationEventDto,
    MigrationRunDto,
    RunMetricDto,
    ValidationStatus,
)

SAFE_METRIC_LABELS = {"command_id", "status", "event_type", "model", "artifact_type"}


def _metric(name: str, run_id: str, value: float, unit: str, *, stage_id: str | None = None, labels: dict[str, str] | None = None) -> RunMetricDto:
    safe_labels = {key: value for key, value in (labels or {}).items() if key in SAFE_METRIC_LABELS}
    return RunMetricDto(metric_name=name, run_id=run_id, stage_id=stage_id, value=value, unit=unit, labels=safe_labels)


def build_diagnostics_summary(
    run: MigrationRunDto,
    *,
    events: list[MigrationEventDto] | None = None,
    stage_id: str | None = None,
    generated_at: datetime | None = None,
) -> DiagnosticsSummaryDto:
    """Build a diagnostics view without mutating or authorizing workflow state."""
    generated_at = generated_at or datetime.now(UTC)
    events = events or []
    commands = [command for command in run.command_results if stage_id is None or command.stage_id == stage_id]
    artifacts = [artifact for artifact in run.artifacts if stage_id is None or artifact.stage_id == stage_id]
    repairs = [attempt for attempt in run.repair_attempts if stage_id is None or attempt.stage_id == stage_id]
    validations = [gate for gate in run.validation_gates if stage_id is None or gate.stage_id == stage_id]
    scoped_events = [event for event in events if stage_id is None or event.stage_id == stage_id]
    llm_usage = [usage for usage in run.llm_usage if stage_id is None]

    metrics = [
        _metric("command.count", run.run_id, len(commands), "count", stage_id=stage_id),
        _metric("artifact.count", run.run_id, len(artifacts), "count", stage_id=stage_id),
        _metric("repair_attempt.count", run.run_id, len(repairs), "count", stage_id=stage_id),
        _metric("sse.event.count", run.run_id, len(scoped_events), "count", stage_id=stage_id),
        _metric("sse.replay.count", run.run_id, sum(1 for event in scoped_events if event.payload.get("replayed") is True), "count", stage_id=stage_id),
        _metric("sse.reconnect.count", run.run_id, sum(1 for event in scoped_events if event.payload.get("reconnected") is True), "count", stage_id=stage_id),
        _metric("manual_item.count", run.run_id, sum(1 for gate in validations if gate.status == ValidationStatus.MANUAL_VALIDATION_REQUIRED), "count", stage_id=stage_id),
        _metric("deferred_item.count", run.run_id, sum(1 for gate in validations if gate.status == ValidationStatus.DEFERRED_COMPANY_TOOL_REQUIRED), "count", stage_id=stage_id),
        _metric("accepted_risk.count", run.run_id, sum(1 for gate in validations if gate.status == ValidationStatus.ACCEPTED_RISK), "count", stage_id=stage_id),
        _metric("rollback.count", run.run_id, sum(1 for patch in run.patch_ledger if (stage_id is None or patch.stage_id == stage_id) and "rollback" in patch.change_summary.lower()), "count", stage_id=stage_id),
        _metric("llm.call.count", run.run_id, len(llm_usage), "count", stage_id=stage_id),
        _metric("llm.input_tokens.total", run.run_id, sum(usage.input_tokens for usage in llm_usage), "tokens", stage_id=stage_id),
        _metric("llm.output_tokens.total", run.run_id, sum(usage.output_tokens for usage in llm_usage), "tokens", stage_id=stage_id),
        _metric("llm.cost.total", run.run_id, round(sum(usage.cost_usd for usage in llm_usage), 6), "usd", stage_id=stage_id),
    ]
    metrics.extend(
        _metric("command.duration", run.run_id, result.duration_ms or 0, "ms", stage_id=result.stage_id, labels={"command_id": result.command_id, "status": result.status.value})
        for result in commands
    )

    alerts: list[AlertEventDto] = []
    if any(result.status.value == "TIMED_OUT" for result in commands):
        alerts.append(mock_alert(run.run_id, AlertType.REPEATED_TIMEOUT, stage_id=stage_id, severity=AlertSeverity.WARNING))
    if any(gate.status == ValidationStatus.FAILED for gate in validations):
        alerts.append(mock_alert(run.run_id, AlertType.STUCK_STATE, stage_id=stage_id, severity=AlertSeverity.WARNING))

    return DiagnosticsSummaryDto(
        run_id=run.run_id,
        stage_id=stage_id,
        generated_at=generated_at,
        metrics=metrics,
        alerts=alerts,
        notes=["Diagnostics are derived from canonical records and are not workflow state."],
    )


def mock_alert(run_id: str, alert_type: AlertType, *, stage_id: str | None = None, severity: AlertSeverity = AlertSeverity.WARNING) -> AlertEventDto:
    messages = {
        AlertType.WORKER_LOSS: "Worker heartbeat was not renewed before the lease window expired.",
        AlertType.STUCK_STATE: "Run or stage appears stuck beyond the mock diagnostic threshold.",
        AlertType.SOURCE_INTEGRITY_FAILURE: "Source integrity verification failed.",
        AlertType.DISK_THRESHOLD: "Available disk space crossed the mock warning threshold.",
        AlertType.REPEATED_TIMEOUT: "Repeated command timeout detected.",
        AlertType.STATE_ARTIFACT_INCONSISTENCY: "State references an artifact that is not available.",
        AlertType.SQLITE_CONTENTION: "SQLite write contention crossed the mock threshold.",
    }
    return AlertEventDto(
        alert_id=f"alert-{alert_type.value}",
        run_id=run_id,
        stage_id=stage_id,
        alert_type=alert_type,
        severity=severity,
        message=messages[alert_type],
        created_at=datetime.now(UTC),
        correlation_id=f"corr-{run_id}",
    )