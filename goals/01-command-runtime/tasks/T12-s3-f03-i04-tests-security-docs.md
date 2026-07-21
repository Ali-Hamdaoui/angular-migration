# Task 12 — S3-F03-I04 — Verify and document Stream live command logs and recover after browser reconnect

## Identity

- Capability goal: `G01`
- Backlog feature: `S3-F03` / `AMFA-142`
- Jira subtask: `AMFA-165`
- Source contract SHA-256: `5f1c2a1a48c7a37e1989146eb2ec119a590ad934bcf6de205cad4627187077af`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S3-F03-I04 — Verify and document Stream live command logs and recover after browser reconnect

  - **Parent feature:** S3-F03
  - **Issue type:** Testing
  - **Technical story:** Prove Stream live command logs and recover after browser reconnect through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Long installs and builds need transparent progress, but live chunks are not the authoritative log evidence.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Terminal input, interactive command response, log editing, and cross-run aggregation.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `GET /api/v1/runs/{id}/commands/{commandId}/logs; existing SSE endpoint emits COMMAND_OUTPUT_AVAILABLE.` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `COMMAND_OUTPUT_AVAILABLE with offsets/sequence, followed by final command event.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Full immutable stdout/stderr logs with truncation metadata for UI stream.` where applicable.
  - **UI impact:** Execute the feature through `Custom log viewer with stdout/stderr filters, tail/pause/search, reconnect indicator, dropped-chunk warning, stored-log pagination, and final result link.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Memory pressure, event flood, dropped chunks, ordering mismatch, ANSI/control characters, secret redaction, and browser treating log text as state.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S3-F03-I03
  - **Suggested labels:** sprint-3, s3-f03, execution-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** High


---

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/12-S3-F03-I04.json`.
- Task completion requires reviewer verdict `PASS`.
