# Manual Runtime Test Plan — G06 Repair Proposer, Reviewer, and G10

## Environment

- Worktree: `/home/ubuntu/amfa-worktrees/06-repair-agents-g10`
- Runtime root: `/home/ubuntu/amfa-runtime/06-repair-agents-g10`
- Backend: `http://127.0.0.1:8306`
- Frontend: `http://127.0.0.1:3306`
- Dedicated SQLite, artifacts, logs, temp, browser profile, Playwright traces, and LangGraph namespace.
- Full Angular fixtures generated outside Git and submitted through production APIs.

## Cases

- `manual-tests/MT-001-s4-f04-authoritative-scenario.md`
- `manual-tests/MT-002-s4-f05-authoritative-scenario.md`
- `manual-tests/MT-003-s4-f06-authoritative-scenario.md`
- `manual-tests/MT-900-capability-integrated-happy-path.md`
- `manual-tests/MT-910-stale-idempotency-reconnect-restart.md`
- `manual-tests/MT-920-security-accessibility-observability.md`

Run exact feature scenarios plus integrated, restart/reconnect/idempotency, security/accessibility/observability cases. The independent tester cannot edit code/tests. Any mandatory failure returns to implementation and regression.
