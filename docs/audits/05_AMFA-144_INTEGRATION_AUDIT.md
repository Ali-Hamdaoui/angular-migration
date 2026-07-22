# AMFA-144 Integration Closure Audit

## Verdict

\`CODE_AND_AUTOMATED_INTEGRATION_COMPLETE\`

\`MANUAL_RUNTIME_EVIDENCE_DEFERRED_BY_OWNER\`

AMFA-173 implementation and automated verification are complete. Manual live-runtime screenshots and real runtime identifiers were explicitly deferred by the delivery owner. This report makes no claim that manual exit evidence exists.

## Identity

| Item | Value |
|---|---|
| Repository | \`C:\\Users\\ilyas.abarbach\\Documents\\angular-migration\` |
| Branch | \`hermes/02-stage-workspace-bootstrap\` |
| Base | \`c2f80e8f5c110a3f62b576a7aec78f1278f846ec\` |
| Retained authorities | AMFA-170, AMFA-171, AMFA-172, AMFA-173 |

## Requirement matrix

| AMFA-144 requirement | Automated authority |
|---|---|
| Exact plan/profile/input/fingerprint resolution and lock | \`test_amfa144_persisted_prepare_g07_sandbox_integration.py\` |
| Durable stage-start and G07 event ordering | Same parent integration test; existing AMFA-171 persistence tests |
| Pending, modification-requested, rejected, stale G07 blocks sandbox | Same parent integration test and \`test_stage_workspace.py\` |
| Approved G07 creates an allowed physical sandbox | Same parent integration test and WorkspaceManager tests |
| Copy report, verification, source immutability | Same parent integration test and artifact/source-safety tests |
| Duplicate decision/copy idempotency and conflict rejection | Same parent integration test and AMFA-171 persistence tests |
| Restart/session reconstruction and one ready event | Same parent integration test and AMFA-171 restart tests |
| Authentication and foreign-actor rejection | AMFA-171 API authorization tests and parent integration test |

## Validation commands and observed results

The parent integration module is \`backend/tests/test_amfa144_stage_sandbox_integration.py\` and passed twice to detect order or persistence dependence.

| Command | Observed result |
|---|---|
| \`backend/.venv/Scripts/python.exe -m pytest tests/test_stage_workspace.py -q\` | 65 passed |
| \`backend/.venv/Scripts/python.exe -m pytest tests/test_stage_preparation_persistence_api_s3_f05_i02.py -q\` | 31 passed; one existing Starlette deprecation warning |
| \`backend/.venv/Scripts/python.exe -m pytest tests/test_workspace_delivery.py tests/test_source_snapshot_security_s1_f07.py tests/test_path_validation_api.py -q\` | 17 passed; one existing Starlette deprecation warning |
| \`backend/.venv/Scripts/python.exe -m pytest tests/test_amfa144_stage_sandbox_integration.py -q\` | 1 passed, run twice |
| \`frontend/npm test -- --run src/components/__tests__/StagePreparationPanel.test.tsx src/components/__tests__/AuthoritativeRunDashboard.test.tsx src/hooks/__tests__/useMigrationEvents.test.ts src/hooks/__tests__/useAuthoritativeRun.test.tsx src/hooks/__tests__/useAuthoritativeRun.llm.test.tsx\` | 5 files, 29 passed |
| \`frontend/npm run typecheck\` | passed |
| \`backend/.venv/Scripts/python.exe -m ruff check tests/test_stage_workspace.py tests/test_stage_preparation_persistence_api_s3_f05_i02.py tests/test_amfa144_stage_sandbox_integration.py\` | passed |
| \`backend/.venv/Scripts/python.exe -m compileall -q app tests\` | passed |
| \`git diff --check\` | passed |

Frontend focused tests cover \`StagePreparationPanel\`, \`AuthoritativeRunDashboard\`, \`useAuthoritativeRun\`, \`useMigrationEvents\`, G07 decision/readiness states, reconnect/restart restoration, safe paths, and accessibility; no frontend server is started.

## Scope cleanup

Baseline route wiring, baseline installation, execution-profile normalization, direct-registry capability, environment diagnostics/probes, Windows command-environment changes, and related discovery artifacts were removed as out-of-scope runtime exploration. \`docs/sprint.md\`, dependency manifests, lockfiles, and generated contracts were not modified.

## Deferred evidence

No server, browser, localhost port, external migration runtime, Angular migration run, G01-G07 manual workflow, screenshot, or real runtime identifier was produced for this delivery. Manual AMFA-173 evidence remains deferred by owner.
