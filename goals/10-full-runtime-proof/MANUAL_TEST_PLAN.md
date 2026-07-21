# Manual Runtime Test Plan — G10 Integrated Angular 18→21 Runtime Proof

## Environment

- Worktree: `/home/ubuntu/amfa-worktrees/10-full-runtime-proof`
- Runtime root: `/home/ubuntu/amfa-runtime/10-full-runtime-proof`
- Backend: `http://127.0.0.1:8310`
- Frontend: `http://127.0.0.1:3310`
- Dedicated SQLite, artifacts, logs, temp, browser profile, Playwright traces, and LangGraph namespace.
- Full Angular fixtures generated outside Git and submitted through production APIs.

## Cases

- `manual-tests/MT-001-s4-f15-authoritative-scenario.md`
- `manual-tests/MT-900-capability-integrated-happy-path.md`
- `manual-tests/MT-910-stale-idempotency-reconnect-restart.md`
- `manual-tests/MT-920-security-accessibility-observability.md`

Run exact feature scenarios plus integrated, restart/reconnect/idempotency, security/accessibility/observability cases. The independent tester cannot edit code/tests. Any mandatory failure returns to implementation and regression.
