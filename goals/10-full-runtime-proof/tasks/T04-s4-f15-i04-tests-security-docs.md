# Task 04 — S4-F15-I04 — Verify and document Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart

## Identity

- Capability goal: `G10`
- Backlog feature: `S4-F15` / `AMFA-225`
- Jira subtask: `AMFA-285`
- Source contract SHA-256: `60c5db4ca55fb87fa42665ba0fa089c5b4663c94b1b50a41164d43ce8ea86e2f`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S4-F15-I04 — Verify and document Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart

  - **Parent feature:** S4-F15
  - **Issue type:** Testing
  - **Technical story:** Prove Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** The MVP is complete only when the integrated controlled platform—not isolated services—proves the authoritative workflow.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Angular 11-17 production validation, Angular 22, unsupported topologies, browser automation, and enterprise scale.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `Existing production APIs; optional GET /api/v1/operator/acceptance-suite/status` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `Existing production events validated for completeness/order; acceptance-suite status events optional.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `External fixture-generation manifests, repository-isolation evidence, external-output-layout evidence, automated integration results, real runtime proof report, cancellation/restart evidence, repair lineage, final output fingerprint, and external-source integrity proof.` where applicable.
  - **UI impact:** Execute the feature through `Operator acceptance checklist linking each scenario to live product pages/artifacts; no hidden API-only completion.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Fixture not representative, external registry/model instability, runtime duration, corporate proxy variance, flaky real tests, and treating simulated proof as runtime proof.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S4-F15-I03
  - **Suggested labels:** sprint-4, s4-f15, operational-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** High


---

## Goal 10 phase boundary

Phase A implements only the branch-owned acceptance harness and consuming contracts. Any criterion requiring real G01–G09 production implementations is recorded as `BLOCKED_INTEGRATION` rather than faked. Phase A may become `harness_ready` but cannot complete AMFA-225. Phase B executes this exact task contract against the integrated product and is required for `jira_complete=true`.

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/04-S4-F15-I04.json`.
- Task completion requires reviewer verdict `PASS`.
