# Task 03 — S4-F15-I03 — Build frontend experience for Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart

## Identity

- Capability goal: `G10`
- Backlog feature: `S4-F15` / `AMFA-225`
- Jira subtask: `AMFA-284`
- Source contract SHA-256: `bc524b0c688e55a9bda29c9e5beabba0d7a4f4e39944a80ff24a0ce85fdda4c9`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S4-F15-I03 — Build frontend experience for Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart

  - **Parent feature:** S4-F15
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart, using backend snapshots and durable events only.
  - **Context:** The MVP is complete only when the integrated controlled platform—not isolated services—proves the authoritative workflow.
  - **Scope:** Operator acceptance checklist linking each scenario to live product pages/artifacts; no hidden API-only completion.
  - **Out of scope:** Angular 11-17 production validation, Angular 22, unsupported topologies, browser automation, and enterprise scale.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `Existing production APIs; optional GET /api/v1/operator/acceptance-suite/status` plus durable events `Existing production events validated for completeness/order; acceptance-suite status events optional.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Operator acceptance checklist linking each scenario to live product pages/artifacts; no hidden API-only completion.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `Existing production APIs; optional GET /api/v1/operator/acceptance-suite/status` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `Existing production events validated for completeness/order; acceptance-suite status events optional.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: External fixture-generation manifests, repository-isolation evidence, external-output-layout evidence, automated integration results, real runtime proof report, cancellation/restart evidence, repair lineage, final output fingerprint, and external-source integrity proof.
  - **UI impact:** Implement: Operator acceptance checklist linking each scenario to live product pages/artifacts; no hidden API-only completion.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S4-F15-I02
  - **Suggested labels:** sprint-4, s4-f15, operational-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

## Goal 10 phase boundary

Phase A implements only the branch-owned acceptance harness and consuming contracts. Any criterion requiring real G01–G09 production implementations is recorded as `BLOCKED_INTEGRATION` rather than faked. Phase A may become `harness_ready` but cannot complete AMFA-225. Phase B executes this exact task contract against the integrated product and is required for `jira_complete=true`.

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/03-S4-F15-I03.json`.
- Task completion requires reviewer verdict `PASS`.
