# Integration Coordinator Runbook

Goal sessions never merge. The coordinator:

1. verifies each pushed branch completion and source/base SHA;
2. integrates in `INTEGRATION_ORDER.md` order;
3. resolves central router/model/generated-client/event/Alembic changes;
4. replaces boundary fakes with real adapters and reruns contract tests;
5. runs Sprint 3 passing fixture, Sprint 4 governed repair, cancellation/reconnect/restart, final assurance/delivery/report;
6. sets `integration_verified=true` only with durable evidence;
7. uses Goal 10 for complete runtime proof.
