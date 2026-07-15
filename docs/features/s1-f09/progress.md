# S1-F09 Progress

## Delivered

- S1-F09-I01: deterministic Angular 18 source-runtime policy, paired Node/npm/npx compatibility resolution, exact immutable profile checksum, explicit multi-candidate confirmation, and stale-profile detection.
- S1-F09-I02: durable execution-profile persistence, Alembic migration, typed resolve/list/select API, ordered events, idempotency, G02 prerequisite enforcement, and immutable runtime evidence artifacts.
- S1-F09-I03: Control Tower runtime-candidate review panel with sanitized executable display, checksum-bound selection, and blocked/stale/failure states.
- S1-F09-I04: cross-layer security/regression tests, manual verification procedure, and traceability documentation.

## Security and authority boundary

ExecutionProfile resolution is deterministic and backend-owned. The frontend submits typed candidate inventory and renders authoritative results; it never selects a runtime locally or advances workflow state. Mixed Node/npm/npx installations, unavailable tools, incompatible Angular/TypeScript/RxJS versions, unapproved network policy, invalid certificate/environment/cache checks, stale executable identity, policy drift, and checksum tampering fail closed. No raw shell, automatic runtime download, LLM decision, or source mutation is introduced.

Runtime evidence is written under the run-scoped artifact root, registered by artifact ID and SHA-256 checksum, and displayed through approved artifact references. Environment evidence is redacted before persistence/display.

## Manual end-to-end verification

1. Start the backend and frontend with the approved external application-data roots.
2. Complete G01, create the run, create the immutable source snapshot, and approve G02.
3. Open the S1-F09 runtime panel and resolve a compatible Angular 18 source profile.
4. Inspect the candidate table: exact Node/npm/npx versions, sanitized executable paths, policy version, and compatibility rationale.
5. With multiple compatible candidates, select one and confirm the selected checksum and `EXECUTION_PROFILE_SELECTED` event are visible; confirm other candidates remain evidence only.
6. Open each runtime evidence artifact by artifact ID and confirm SHA-256 metadata matches.
7. Replace or invalidate the selected npm executable, or change the compatibility policy version, then retry baseline start. Confirm the profile is stale and baseline remains blocked until resolution is repeated.
8. Repeat with no compatible candidate and confirm actionable preparation guidance appears; confirm no runtime download, repair proposal, or source mutation occurs.
9. Refresh/reconnect the browser and confirm the same persisted resolution, selection, checksum, and ordered events are restored from the backend.

## Validation

- Backend focused S1-F09 domain, persistence, API, and security tests pass where the Windows pytest temporary-root ACL permits setup.
- Frontend full suite, typecheck, and production build pass.
