# Observability

Owns run metrics, diagnostics summaries, alert vocabulary, correlation IDs, and non-authoritative operational evidence.

Metrics must not contain secrets, full source code, raw logs, prompts, command output, or arbitrary repository text. Observability failures must not corrupt state transitions or become a second workflow state store.

## Sprint 0 Metrics

Sprint 0 diagnostics are derived from canonical run records:

- command count, duration, status, and exit-code availability;
- artifact count;
- SSE event, reconnect, and replay counts;
- repair attempt and rollback counts;
- manual, deferred, and accepted-risk item counts;
- LLM call count, input tokens, output tokens, and cost from usage records.

## Alert Vocabulary

Sprint 0 defines these structured alert event types:

- `worker_loss`
- `stuck_state`
- `source_integrity_failure`
- `disk_threshold`
- `repeated_timeout`
- `state_artifact_inconsistency`
- `sqlite_contention`

Alerts are diagnostic signals only. State transitions remain owned by the state transition service.