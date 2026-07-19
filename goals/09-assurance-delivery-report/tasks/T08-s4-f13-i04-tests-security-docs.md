# Task 08 — S4-F13-I04 — Verify and document Create a delivery candidate and publish atomically through G14

## Identity

- Capability goal: `G09`
- Backlog feature: `S4-F13` / `AMFA-223`
- Jira subtask: `AMFA-277`
- Source contract SHA-256: `f73ebee2a9dbb5566f05b68dfe35d70ef23abffe66acc2673240f7e373a160b7`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S4-F13-I04 — Verify and document Create a delivery candidate and publish atomically through G14

  - **Parent feature:** S4-F13
  - **Issue type:** Testing
  - **Technical story:** Prove Create a delivery candidate and publish atomically through G14 through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Final output appears only at `<resolved-output-root>/migrated-app`, beneath the exact user-selected external output root, and only from the approved final fingerprint after independent verification, unchanged-original-source proof, destination revalidation, and human delivery authority.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Cloud deployment, Git push/PR, backend migration, and publishing before final assurance.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/delivery/candidate; GET /api/v1/runs/{id}/delivery; POST /api/v1/runs/{id}/approvals/G14/decisions; POST /api/v1/runs/{id}/delivery/publish` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `DELIVERY_CANDIDATE_READY, PUBLICATION_STARTED/COMPLETED/FAILED and G14 events.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Delivery manifest, exclusion list, candidate fingerprint, original-source final integrity report, output-root destination safety report, managed-output ownership report, G14 package, and publication record.` where applicable.
  - **UI impact:** Execute the feature through `Delivery review page with selected external output root, final `migrated-app` path, source-integrity status, file counts, fingerprint, exclusions, overwrite/fallback explanation, G14 controls, publish progress, and partial-failure evidence.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Cross-volume rename, output path or migration output changed after approval, existing unmanaged `migrated-app`, partial copy, disk exhaustion, file locks, platform-repository/source path escape, changed original source, and duplicate publication.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G14 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S4-F13-I03
  - **Suggested labels:** sprint-4, s4-f13, approval-capability, testing, g14, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** High


---

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/08-S4-F13-I04.json`.
- Task completion requires reviewer verdict `PASS`.
