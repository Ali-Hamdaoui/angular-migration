# Task 05 — S4-F13-I01 — Implement backend application contract for Create a delivery candidate and publish atomically through G14

## Identity

- Capability goal: `G09`
- Backlog feature: `S4-F13` / `AMFA-223`
- Jira subtask: `AMFA-274`
- Source contract SHA-256: `5ddb1f01889ca2261cff6b5867ba6d2ee804fafb375cedd6155cc366a2612435`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S4-F13-I01 — Implement backend application contract for Create a delivery candidate and publish atomically through G14

  - **Parent feature:** S4-F13
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Create a delivery candidate and publish atomically through G14 so the feature has one authoritative service path.
  - **Context:** Final output appears only at `<resolved-output-root>/migrated-app`, beneath the exact user-selected external output root, and only from the approved final fingerprint after independent verification, unchanged-original-source proof, destination revalidation, and human delivery authority.
  - **Scope:** DeliveryService for candidate copy from the approved final stage sandbox, exclusions, manifest/fingerprint, original-source fingerprint revalidation, output-root containment, parent writability, and ownership revalidation, managed-output and overwrite policy, G14 package, idempotent publication to the exact registered `migrated-app` alias, same-volume atomic rename or two-phase fail-closed fallback, and source/snapshot/final binding.
  - **Out of scope:** Cloud deployment, Git push/PR, backend migration, and publishing before final assurance.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. G14 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/delivery/candidate; GET /api/v1/runs/{id}/delivery; POST /api/v1/runs/{id}/approvals/G14/decisions; POST /api/v1/runs/{id}/delivery/publish`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: DeliveryService for candidate copy from the approved final stage sandbox, exclusions, manifest/fingerprint, original-source fingerprint revalidation, output-root containment, parent writability, and ownership revalidation, managed-output and overwrite policy, G14 package, idempotent publication to the exact registered `migrated-app` alias, same-volume atomic rename or two-phase fail-closed fallback, and source/snapshot/final binding.
  - **Database impact:** Use or introduce the records summarized by: delivery_records, output-root/migrated-app aliases, source/snapshot/candidate/final fingerprints, publication attempts, gate decisions/events.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/delivery/candidate; GET /api/v1/runs/{id}/delivery; POST /api/v1/runs/{id}/approvals/G14/decisions; POST /api/v1/runs/{id}/delivery/publish
  - **Event impact:** Request durable events only through the transition/event service: DELIVERY_CANDIDATE_READY, PUBLICATION_STARTED/COMPLETED/FAILED and G14 events.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Delivery manifest, exclusion list, candidate fingerprint, original-source final integrity report, output-root destination safety report, managed-output ownership report, G14 package, and publication record.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Cross-volume rename, output path or migration output changed after approval, existing unmanaged `migrated-app`, partial copy, disk exhaustion, file locks, platform-repository/source path escape, changed original source, and duplicate publication.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G14 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S4-F12
  - **Suggested labels:** sprint-4, s4-f13, approval-capability, backend, g14, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/05-S4-F13-I01.json`.
- Task completion requires reviewer verdict `PASS`.
