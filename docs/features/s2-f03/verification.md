# S2-F03 verification record

Feature: **S2-F03 — Invoke Azure OpenAI through a governed role-routed gateway**

This record verifies I01–I03 through the I04 test and manual seams. It is a
verification aid, not a second source of workflow state.

## Automated coverage

Backend coverage is split by authority:

- `tests/test_llm_gateway.py`: Azure configuration fail-closed behavior,
  role/schema validation, structured-output validation, retry classification,
  untrusted-content labeling, prompt redaction, `store=false`, pricing
  snapshot cost calculation, and budget decisions.
- `tests/test_llm_evidence_s2_f03.py`: temporary SQLite and Artifact Store
  evidence, ordered lifecycle events, idempotent replay, stale state,
  idempotency conflict, and redacted provider failure evidence.
- `tests/test_llm_verification_s2_f03.py`: FastAPI route contracts for
  readiness, smoke, activity, and usage; stable validation/stale errors;
  correlation-ID propagation; and absence of credential fields in validation
  errors.

Frontend coverage is split by projection boundary:

- `src/components/__tests__/LlmDiagnosticsPanel.test.tsx`: provenance,
  token/cost display, governed invocation, and stale-state presentation.
- `src/api/__tests__/llm.test.ts`: typed endpoint paths and HTTP methods.
- `src/hooks/__tests__/useAuthoritativeRun.llm.test.tsx`: LLM lifecycle and
  budget SSE subscriptions plus duplicate-event suppression.

## Validation commands

From `backend`:

```powershell
python -m pytest tests/test_llm_gateway.py tests/test_llm_evidence_s2_f03.py tests/test_llm_verification_s2_f03.py -q --basetemp C:\tmp\pytest-s2f03-i04
python -m ruff check app tests/test_llm_gateway.py tests/test_llm_evidence_s2_f03.py tests/test_llm_verification_s2_f03.py
python -m compileall -q app alembic
```

From `frontend`:

```powershell
npm run typecheck
npm run lint
npm run test -- --run
npm run build
```

The live Azure provider is intentionally not required for automated tests;
fake transport/gateway adapters keep tests deterministic and prevent secrets
from entering the repository or test artifacts.

## Manual verification

Preconditions:

1. Start the backend with the Feature 3 database migration applied.
2. Start the Next.js frontend.
3. Use an authenticated local operator and a valid run fixture.
4. Configure Azure OpenAI only through local environment configuration; never
   enter credentials in the browser or commit them.

Steps:

1. Open the run dashboard and confirm the LLM panel distinguishes loading,
   empty, readiness-blocked, and backend-failure states.
2. Confirm the readiness state and deployment capability are visible.
3. Select **Run governed smoke check** and verify the pending state does not
   locally advance workflow status.
4. Confirm the completed panel shows provider, deployment alias, role, task,
   input/output/total tokens, estimated input/output/total cost, retries,
   latency, budget status, state version, event sequence, and artifact IDs.
5. Refresh the page and disconnect/reconnect the SSE connection. Confirm the
   backend snapshot and replayed events restore the same result without a
   duplicate invocation.
6. Submit with a stale state version and confirm `STALE_STATE_VERSION`, a
   correlation ID, recovery guidance, and no local workflow progression.
7. Simulate an unavailable Azure configuration/provider failure and confirm a
   redacted error, preserved partial evidence, and no secret/raw prompt in the
   UI or artifacts.
8. Inspect the four API responses and registered artifact IDs; verify that
   artifact content is retrieved by ID and checksums remain unchanged.

Expected evidence:

- `LLM_INVOCATION_STARTED` followed by `LLM_INVOCATION_COMPLETED` or
  `LLM_INVOCATION_FAILED`.
- Applicable `LLM_BUDGET_WARNING` or `LLM_BUDGET_BLOCKED` event.
- Sanitized request manifest, validated structured response, redacted error
  when failed, and usage/cost report.
- `llm_invocations` and `usage_cost_records` rows with version, checksum,
  idempotency, token, pricing, and cost metadata.

## Known limitations

- Azure live-provider execution, external security scanning, and browser
  screenshots require environment-specific credentials and are manual/deferred
  evidence rather than CI requirements.
- ESLint currently reports one pre-existing warning in
  `BaselinePreparationPanel.tsx`; I04 introduces no new lint errors.
- Cached/reasoning tokens, direct browser Azure calls, model-driven commands,
  and autonomous budget overrides remain out of scope.
