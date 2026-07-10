# Observability

Owns run metrics, diagnostics summaries, alert vocabulary, correlation IDs, and
non-authoritative operational evidence.

Metrics must not contain secrets, full source code, or become a second workflow
state store. Observability failures must not corrupt state transitions.