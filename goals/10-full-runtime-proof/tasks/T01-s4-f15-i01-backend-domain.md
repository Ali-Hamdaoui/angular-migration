# Task 01 — S4-F15-I01 — Implement backend application contract for Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart

## Identity

- Capability goal: `G10`
- Backlog feature: `S4-F15` / `AMFA-225`
- Jira subtask: `AMFA-282`
- Source contract SHA-256: `d90598803c8de31aa8b98d40b013d6c10b500496e5f296ee172576f94f0d0646`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S4-F15-I01 — Implement backend application contract for Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart

  - **Parent feature:** S4-F15
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart so the feature has one authoritative service path.
  - **Context:** The MVP is complete only when the integrated controlled platform—not isolated services—proves the authoritative workflow.
  - **Scope:** Fixture harness, real subprocess test profiles, deterministic failure fixtures, fake model integration suite plus one configured Azure path, end-to-end orchestration tests, security tests, and runtime evidence collector.
  - **Out of scope:** Angular 11-17 production validation, Angular 22, unsupported topologies, browser automation, and enterprise scale.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `Existing production APIs; optional GET /api/v1/operator/acceptance-suite/status`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: Fixture harness, real subprocess test profiles, deterministic failure fixtures, fake model integration suite plus one configured Azure path, end-to-end orchestration tests, security tests, and runtime evidence collector.
  - **Database impact:** Use or introduce the records summarized by: Test execution metadata and complete migration-run records/artifacts.
  - **API impact:** Define service-facing request/response models supporting: Existing production APIs; optional GET /api/v1/operator/acceptance-suite/status
  - **Event impact:** Request durable events only through the transition/event service: Existing production events validated for completeness/order; acceptance-suite status events optional.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: External fixture-generation manifests, repository-isolation evidence, external-output-layout evidence, automated integration results, real runtime proof report, cancellation/restart evidence, repair lineage, final output fingerprint, and external-source integrity proof.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Fixture not representative, external registry/model instability, runtime duration, corporate proxy variance, flaky real tests, and treating simulated proof as runtime proof.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S4-F01, S4-F02, S4-F03, S2-F03, S4-F04, S4-F05, S4-F06, S4-F07, S4-F08, S4-F09, S4-F10, S4-F11, S4-F12, S4-F13, S4-F14
  - **Suggested labels:** sprint-4, s4-f15, operational-capability, backend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

## Goal 10 phase boundary

Phase A implements only the branch-owned acceptance harness and consuming contracts. Any criterion requiring real G01–G09 production implementations is recorded as `BLOCKED_INTEGRATION` rather than faked. Phase A may become `harness_ready` but cannot complete AMFA-225. Phase B executes this exact task contract against the integrated product and is required for `jira_complete=true`.

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/01-S4-F15-I01.json`.
- Task completion requires reviewer verdict `PASS`.
