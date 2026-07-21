# MT-001 — S4-F15 Authoritative Manual Scenario

## Metadata

- Goal: `G10`
- Feature/Jira: `S4-F15` / `AMFA-225`
- Commit SHA: record at execution
- Runtime root: `/home/ubuntu/amfa-runtime/10-full-runtime-proof`

## User-observable outcome

The team can execute the final manual and automated runtime proof on Angular 18.0.x and 18.2.x workspaces generated under external temporary test roots, including all gates, one real repair, an environment blocker, cancellation, restart recovery, final assurance, external-output publication, and unchanged external source.

## Exact backlog manual scenario

**Preconditions:** S4-F01, S4-F02, S4-F03, S2-F03, S4-F04, S4-F05, S4-F06, S4-F07, S4-F08, S4-F09, S4-F10, S4-F11, S4-F12, S4-F13, S4-F14; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Operator acceptance checklist linking each scenario to live product pages/artifacts; no hidden API-only completion.**.
3. Trigger the primary action for **Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** The team can execute the final manual and automated runtime proof on Angular 18.0.x and 18.2.x workspaces generated under external temporary test roots, including all gates, one real repair, an environment blocker, cancellation, restart recovery, final assurance, external-output publication, and unchanged external source. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Test execution metadata and complete migration-run records/artifacts.` are retrievable through `Existing production APIs; optional GET /api/v1/operator/acceptance-suite/status` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** External fixture-generation manifests, repository-isolation evidence, external-output-layout evidence, automated integration results, real runtime proof report, cancellation/restart evidence, repair lineage, final output fingerprint, and external-source integrity proof.

**Expected durable event:** Existing production events validated for completeness/order; acceptance-suite status events optional.

**Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.

**Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

## Required evidence

Record preconditions, external fixture identity/fingerprints, exact UI/API steps, expected/actual result, DB records/state version, durable event sequence, artifact IDs/checksums, screenshots/trace/network/SSE/log evidence, source-integrity proof, cleanup, defects, and PASS/FAIL/BLOCKED.
