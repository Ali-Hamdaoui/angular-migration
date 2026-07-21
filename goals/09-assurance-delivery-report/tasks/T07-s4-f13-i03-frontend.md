# Task 07 — S4-F13-I03 — Build frontend experience for Create a delivery candidate and publish atomically through G14

## Identity

- Capability goal: `G09`
- Backlog feature: `S4-F13` / `AMFA-223`
- Jira subtask: `AMFA-276`
- Source contract SHA-256: `23084b1a6520fcd2d5809e7edd0e98e6e56f83f90587cb84dfa44b7981c0b2d7`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S4-F13-I03 — Build frontend experience for Create a delivery candidate and publish atomically through G14

  - **Parent feature:** S4-F13
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Create a delivery candidate and publish atomically through G14, using backend snapshots and durable events only.
  - **Context:** Final output appears only at `<resolved-output-root>/migrated-app`, beneath the exact user-selected external output root, and only from the approved final fingerprint after independent verification, unchanged-original-source proof, destination revalidation, and human delivery authority.
  - **Scope:** Delivery review page with selected external output root, final `migrated-app` path, source-integrity status, file counts, fingerprint, exclusions, overwrite/fallback explanation, G14 controls, publish progress, and partial-failure evidence.
  - **Out of scope:** Cloud deployment, Git push/PR, backend migration, and publishing before final assurance.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/delivery/candidate; GET /api/v1/runs/{id}/delivery; POST /api/v1/runs/{id}/approvals/G14/decisions; POST /api/v1/runs/{id}/delivery/publish` plus durable events `DELIVERY_CANDIDATE_READY, PUBLICATION_STARTED/COMPLETED/FAILED and G14 events.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Delivery review page with selected external output root, final `migrated-app` path, source-integrity status, file counts, fingerprint, exclusions, overwrite/fallback explanation, G14 controls, publish progress, and partial-failure evidence.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/delivery/candidate; GET /api/v1/runs/{id}/delivery; POST /api/v1/runs/{id}/approvals/G14/decisions; POST /api/v1/runs/{id}/delivery/publish` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `DELIVERY_CANDIDATE_READY, PUBLICATION_STARTED/COMPLETED/FAILED and G14 events.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Delivery manifest, exclusion list, candidate fingerprint, original-source final integrity report, output-root destination safety report, managed-output ownership report, G14 package, and publication record.
  - **UI impact:** Implement: Delivery review page with selected external output root, final `migrated-app` path, source-integrity status, file counts, fingerprint, exclusions, overwrite/fallback explanation, G14 controls, publish progress, and partial-failure evidence.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G14 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S4-F13-I02
  - **Suggested labels:** sprint-4, s4-f13, approval-capability, frontend, g14, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/07-S4-F13-I03.json`.
- Task completion requires reviewer verdict `PASS`.
