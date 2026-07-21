# Task 09 — S3-F03-I01 — Implement backend application contract for Stream live command logs and recover after browser reconnect

## Identity

- Capability goal: `G01`
- Backlog feature: `S3-F03` / `AMFA-142`
- Jira subtask: `AMFA-162`
- Source contract SHA-256: `73b91d3bbd39e7126115fa7e48ff37bf0f51098d752e686123ae63c771c35ad9`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S3-F03-I01 — Implement backend application contract for Stream live command logs and recover after browser reconnect

  - **Parent feature:** S3-F03
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Stream live command logs and recover after browser reconnect so the feature has one authoritative service path.
  - **Context:** Long installs and builds need transparent progress, but live chunks are not the authoritative log evidence.
  - **Scope:** Bounded log-chunk publisher, sequence metadata, SSE command events, final artifact linkage, pagination/search endpoint for stored logs, and backpressure controls.
  - **Out of scope:** Terminal input, interactive command response, log editing, and cross-run aggregation.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `GET /api/v1/runs/{id}/commands/{commandId}/logs; existing SSE endpoint emits COMMAND_OUTPUT_AVAILABLE.`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: Bounded log-chunk publisher, sequence metadata, SSE command events, final artifact linkage, pagination/search endpoint for stored logs, and backpressure controls.
  - **Database impact:** Use or introduce the records summarized by: Command event metadata only; complete logs remain artifacts.
  - **API impact:** Define service-facing request/response models supporting: GET /api/v1/runs/{id}/commands/{commandId}/logs; existing SSE endpoint emits COMMAND_OUTPUT_AVAILABLE.
  - **Event impact:** Request durable events only through the transition/event service: COMMAND_OUTPUT_AVAILABLE with offsets/sequence, followed by final command event.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Full immutable stdout/stderr logs with truncation metadata for UI stream.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Memory pressure, event flood, dropped chunks, ordering mismatch, ANSI/control characters, secret redaction, and browser treating log text as state.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S3-F02
  - **Suggested labels:** sprint-3, s3-f03, execution-capability, backend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/09-S3-F03-I01.json`.
- Task completion requires reviewer verdict `PASS`.
