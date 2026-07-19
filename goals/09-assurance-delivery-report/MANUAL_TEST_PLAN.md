# Manual Runtime Test Plan — G09 Final Assurance, Delivery, Reporting, and G13–G15

## Environment

- Worktree: `/home/ubuntu/amfa-worktrees/09-assurance-delivery-report`
- Runtime root: `/home/ubuntu/amfa-runtime/09-assurance-delivery-report`
- Backend: `http://127.0.0.1:8309`
- Frontend: `http://127.0.0.1:3309`
- Dedicated SQLite, artifacts, logs, temp, browser profile, Playwright traces, and LangGraph namespace.
- Full Angular fixtures generated outside Git and submitted through production APIs.

## Cases

- `manual-tests/MT-001-s4-f12-authoritative-scenario.md`
- `manual-tests/MT-002-s4-f13-authoritative-scenario.md`
- `manual-tests/MT-003-s4-f14-authoritative-scenario.md`
- `manual-tests/MT-900-capability-integrated-happy-path.md`
- `manual-tests/MT-910-stale-idempotency-reconnect-restart.md`
- `manual-tests/MT-920-security-accessibility-observability.md`

Run exact feature scenarios plus integrated, restart/reconnect/idempotency, security/accessibility/observability cases. The independent tester cannot edit code/tests. Any mandatory failure returns to implementation and regression.
