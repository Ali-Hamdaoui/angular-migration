# Task 20 — S3-F14-I04 — Verify and document Seal G12, copy forward, and reuse the parameterized stage engine through Angular 21

## Identity

- Capability goal: `G04`
- Backlog feature: `S3-F14` / `AMFA-153`
- Jira subtask: `AMFA-209`
- Source contract SHA-256: `810d3607c49b5cfe621475f6441d0fbd33478c5fd2b2873641585a654c698545`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S3-F14-I04 — Verify and document Seal G12, copy forward, and reuse the parameterized stage engine through Angular 21

  - **Parent feature:** S3-F14
  - **Issue type:** Testing
  - **Technical story:** Prove Seal G12, copy forward, and reuse the parameterized stage engine through Angular 21 through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Stage completion and copy-forward are separate trusted boundaries. The engine must use actual prior-stage output and finalize exact versions before each new stage.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** LLM repair, final clean assurance, delivery, and startup crash recovery.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/stages/{stageId}/complete-package; POST /api/v1/runs/{id}/approvals/G12/decisions; POST /api/v1/runs/{id}/stages/{stageId}/copy-forward` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `STAGE_CLEANUP_COMPLETED, STAGE_WAITING_APPROVAL, STAGE_COMPLETED, NEXT_STAGE_CREATED/SANDBOX_READY.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Cleanup report, cleanliness report, output manifest/fingerprint, stage evidence index, G12 package, and copy-forward report.` where applicable.
  - **UI impact:** Execute the feature through `Stage completion review, cleanliness/fingerprint cards, G12 controls, copy-forward progress, three-stage timeline, and stage-specific state/log/artifact navigation.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: node_modules copied forward, unstable fingerprint, stage index mismatch, wrong sandbox path, next exact profile not revalidated, artifact cross-stage overwrite, and UI showing wrong active stage.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G12 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S3-F14-I03
  - **Suggested labels:** sprint-3, s3-f14, approval-capability, testing, g12, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** Medium


---


### D.3.5 Sprint integration tests

- Command policy negative tests for shell strings, forbidden flags, cwd escape, environment smuggling, and stale plan.

- Real harmless subprocess, timeout, live log, process-tree cancellation, and partial-evidence tests.

- Run-scoped stage sandbox isolation and no-node_modules copy-forward tests.

- Complete stage validation matrix and core-gate non-bypass tests.

- LangGraph parameterized stage-loop tests using actual prior-stage output and exact re-resolution.


### D.3.6 Sprint manual demonstration

Approve G07; create Stage 18→19 sandbox; run exact update; watch/reconnect logs; inspect diff and approve G08; run install/static/build/tests/lint/parity; approve G09; clean/fingerprint and approve G12; copy forward; cancel a controlled command; prove source unchanged; run all three stages on a passing fixture.


#### Demonstration checklist

1. Approve G07.

2. Create Stage 18→19 sandbox.

3. Run exact update.

4. Watch/reconnect logs.

5. Inspect diff and approve G08.

6. Run install/static/build/tests/lint/parity.

7. Approve G09.

8. Clean/fingerprint and approve G12.

9. Copy forward.

10. Cancel a controlled command.

11. Prove source unchanged.

12. Run all three stages on a passing fixture..


### D.3.7 Sprint exit criteria

- The CommandExecutor is the sole process path.

- G07, G08, G09, and G12 block and bind correctly.

- All three MVP transitions pass on a representative passing fixture.

- Browser refresh does not cancel execution.

- Explicit cancellation terminates the controlled process tree and preserves evidence.

- Every stage has a distinct clean sandbox and fingerprint.


### D.3.8 Risks carried into the next sprint

Repair governance, crash recovery, final assurance, atomic delivery, reporting, and runtime acceptance are completed in Sprint 4.

## Sprint 4 — Failure Evidence, Two-LLM Repair, Recovery, Final Assurance, Delivery, Reporting, and Runtime Proof

**Dependency:** Sprint 3 integrated stage engine and Sprint 2 production Azure gateway  
**Human gates:** G10, G11, G13, G14, G15  
**Feature count:** 15 vertical features / 60 bounded issues

### Sprint goal

Complete the MVP with deterministic failure evidence and routing, checksum-bound Repair Proposer/Reviewer governance, exact persisted patch application, safe recovery, evidence-grounded Assistant help, independent final assurance, atomic delivery, deterministic reporting with optional AI narrative, and a real Angular 18.x→21.x proof.

### Features in implementation order

1. **S4-F01 — Capture FailureEvidence and parse deterministic diagnostics**
2. **S4-F02 — Route failures with C-Lite and show environment or retry actions**
3. **S4-F03 — Build and inspect a bounded sanitized RepairContextPack**
4. **S4-F04 — Generate a checksum-bound Repair Proposer candidate**
5. **S4-F05 — Review the Repair Proposer candidate with a non-authoring Reviewer**
6. **S4-F06 — Persist the reviewed proposal and decide G10 Apply or Reject**
7. **S4-F07 — Validate and apply only the exact persisted repair diff**
8. **S4-F08 — Run patch preflight, resume normal validation, and decide G11**
9. **S4-F09 — Stop no-progress repair loops and reconstruct or roll back safely**
10. **S4-F10 — Reconcile interrupted commands, leases, artifacts, and graph state on startup**
11. **S4-F11 — Explain authoritative migration state through the AI Assistant**
12. **S4-F12 — Run independent final assurance and decide G13**
13. **S4-F13 — Create a delivery candidate and publish atomically through G14**
14. **S4-F14 — Generate the deterministic evidence report, optional AI narrative, and decide G15**
15. **S4-F15 — Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart**

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/20-S3-F14-I04.json`.
- Task completion requires reviewer verdict `PASS`.
