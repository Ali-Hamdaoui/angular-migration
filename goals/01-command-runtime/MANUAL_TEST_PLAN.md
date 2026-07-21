# Manual Runtime Test Plan — G01 Governed Command Runtime

## Environment

- Worktree: `/home/ubuntu/amfa-worktrees/01-command-runtime`
- Runtime root: `/home/ubuntu/amfa-runtime/01-command-runtime`
- Backend: `http://127.0.0.1:8301`
- Frontend: `http://127.0.0.1:3301`
- Dedicated SQLite, artifacts, logs, temp, browser profile, Playwright traces, and LangGraph namespace.
- Full Angular fixtures generated outside Git and submitted through production APIs.

## Cases

- `manual-tests/MT-001-s3-f01-authoritative-scenario.md`
- `manual-tests/MT-002-s3-f02-authoritative-scenario.md`
- `manual-tests/MT-003-s3-f03-authoritative-scenario.md`
- `manual-tests/MT-004-s3-f04-authoritative-scenario.md`
- `manual-tests/MT-900-capability-integrated-happy-path.md`
- `manual-tests/MT-910-stale-idempotency-reconnect-restart.md`
- `manual-tests/MT-920-security-accessibility-observability.md`

Run exact feature scenarios plus integrated, restart/reconnect/idempotency, security/accessibility/observability cases. The independent tester cannot edit code/tests. Any mandatory failure returns to implementation and regression.
