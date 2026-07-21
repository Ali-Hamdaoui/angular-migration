# Feature 3 manual end-to-end scenario

## Repeatable local verification record

Scenario: an authenticated operator invokes the governed smoke check for an authorized, approved run.

Validated by the backend focused suite (`29 passed, 1 skipped`) and full suite (`354 passed, 2 skipped`) on 2026-07-19, plus frontend build/typecheck and `30` frontend test files / `78` tests. The exercised contract records:

- actor from the authenticated boundary, with no actor field accepted in smoke JSON;
- role/task route `assistant` / `smoke_check`;
- registered strict `json_schema` output and schema validation;
- prompt, schema, model capability/deployment, pricing, stage, input hash, redacted summary, correlation ID, artifact IDs/checksums/links, and ordered workflow events;
- idempotent replay without duplicate invocation side effects.

Negative cases covered by tests: incomplete provider configuration is blocked; stale state returns `STALE_STATE_VERSION`; a reused idempotency key with a different payload returns `IDEMPOTENCY_KEY_REUSED`; a non-owner actor returns `RUN_NOT_AUTHORIZED`; unmet approval prerequisites return `RUN_PREREQUISITES_NOT_MET`; provider failure is redacted and retains its correlation ID; and artifact access is ownership-checked.

## Live-provider/manual UI evidence

Live Azure OpenAI execution and browser screenshot/artifact/event capture remain an environment-dependent manual step. No Azure endpoint/key or authenticated browser session was available in this workspace, so no live provider evidence is claimed. Before release, run the same scenario against the configured Azure deployment and attach the returned run ID, invocation ID, correlation ID, artifact IDs, event sequence, and UI screenshots to the release record.
