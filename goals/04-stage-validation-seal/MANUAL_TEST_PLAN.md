# Manual Runtime Test Plan — G04 Stage Validation, G09, G12, and Copy-Forward

## Environment

- Worktree: `/home/ubuntu/amfa-worktrees/04-stage-validation-seal`
- Runtime root: `/home/ubuntu/amfa-runtime/04-stage-validation-seal`
- Backend: `http://127.0.0.1:8304`
- Frontend: `http://127.0.0.1:3304`
- Dedicated SQLite, artifacts, logs, temp, browser profile, Playwright traces, and LangGraph namespace.
- Full Angular fixtures generated outside Git and submitted through production APIs.

## Cases

- `manual-tests/MT-001-s3-f10-authoritative-scenario.md`
- `manual-tests/MT-002-s3-f11-authoritative-scenario.md`
- `manual-tests/MT-003-s3-f12-authoritative-scenario.md`
- `manual-tests/MT-004-s3-f13-authoritative-scenario.md`
- `manual-tests/MT-005-s3-f14-authoritative-scenario.md`
- `manual-tests/MT-900-capability-integrated-happy-path.md`
- `manual-tests/MT-910-stale-idempotency-reconnect-restart.md`
- `manual-tests/MT-920-security-accessibility-observability.md`

Run exact feature scenarios plus integrated, restart/reconnect/idempotency, security/accessibility/observability cases. The independent tester cannot edit code/tests. Any mandatory failure returns to implementation and regression.
