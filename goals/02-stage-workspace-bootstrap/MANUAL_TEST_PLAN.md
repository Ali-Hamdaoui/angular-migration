# Manual Runtime Test Plan — G02 Stage Workspace, G07, and Bootstrap

## Environment

- Worktree: `/home/ubuntu/amfa-worktrees/02-stage-workspace-bootstrap`
- Runtime root: `/home/ubuntu/amfa-runtime/02-stage-workspace-bootstrap`
- Backend: `http://127.0.0.1:8302`
- Frontend: `http://127.0.0.1:3302`
- Dedicated SQLite, artifacts, logs, temp, browser profile, Playwright traces, and LangGraph namespace.
- Full Angular fixtures generated outside Git and submitted through production APIs.

## Cases

- `manual-tests/MT-001-s3-f05-authoritative-scenario.md`
- `manual-tests/MT-002-s3-f06-authoritative-scenario.md`
- `manual-tests/MT-900-capability-integrated-happy-path.md`
- `manual-tests/MT-910-stale-idempotency-reconnect-restart.md`
- `manual-tests/MT-920-security-accessibility-observability.md`

Run exact feature scenarios plus integrated, restart/reconnect/idempotency, security/accessibility/observability cases. The independent tester cannot edit code/tests. Any mandatory failure returns to implementation and regression.
