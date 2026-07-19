# Manual Runtime Test Plan — G07 Exact Patch Apply, G11, and Loop Protection

## Environment

- Worktree: `/home/ubuntu/amfa-worktrees/07-patch-validation-loop`
- Runtime root: `/home/ubuntu/amfa-runtime/07-patch-validation-loop`
- Backend: `http://127.0.0.1:8307`
- Frontend: `http://127.0.0.1:3307`
- Dedicated SQLite, artifacts, logs, temp, browser profile, Playwright traces, and LangGraph namespace.
- Full Angular fixtures generated outside Git and submitted through production APIs.

## Cases

- `manual-tests/MT-001-s4-f07-authoritative-scenario.md`
- `manual-tests/MT-002-s4-f08-authoritative-scenario.md`
- `manual-tests/MT-003-s4-f09-authoritative-scenario.md`
- `manual-tests/MT-900-capability-integrated-happy-path.md`
- `manual-tests/MT-910-stale-idempotency-reconnect-restart.md`
- `manual-tests/MT-920-security-accessibility-observability.md`

Run exact feature scenarios plus integrated, restart/reconnect/idempotency, security/accessibility/observability cases. The independent tester cannot edit code/tests. Any mandatory failure returns to implementation and regression.
