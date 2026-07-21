# Automated Test Standards

Applicable layers: domain/unit, application service, repository/transaction, Alembic, API/error, artifact integrity, event/SSE replay, LangGraph node/interrupt/resume, command real-process/timeout/cancel, idempotency/concurrency, security negatives, frontend component/accessibility, typecheck/lint/build, and cross-goal contract tests.

Use isolated external temporary roots and databases. Full Angular fixtures are generated outside Git and submitted through production APIs. Include exact happy, invalid, stale, duplicate, missing-prerequisite/gate, downstream-failure, restart/reconnect, cancellation, and authority-bypass cases from the backlog.

Do not weaken assertions, delete required tests, blindly update snapshots, skip core failures, or present not-configured/manual/deferred checks as passed.
