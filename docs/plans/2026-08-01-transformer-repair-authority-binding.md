# Transformer Repair Authority Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Separate untrusted LLM-authored repair/review content from backend-owned authority bindings while preserving stale-state protection, logical replay, human approval, and historical artifact readability.

**Architecture:** Azure receives strict v2 candidate schemas only. `RepairApplicationService` validates candidate content and constructs the existing v1-compatible persisted proposal/review shape from freshly reloaded backend authority. The graph, G10 gate, apply service, and revalidation consume only those bound results. Logical `LlmInvocationModel` replay remains unchanged in shape; physical provider-attempt history remains out of scope.

**Tech Stack:** Python, Pydantic, SQLAlchemy, pytest, Azure structured-output gateway, local immutable artifact store, Ruff.

## Global Constraints

- Continue on branch `fix/transformer-repair-llm-wiring`; do not create another branch.
- Preserve `frontend/next-env.d.ts`; never edit, stage, reset, or commit it.
- Do not start APIs/workers, call Azure, restart `run-6f89ac89792a`, modify its DB/artifacts, run a live migration, or run the full test suite.
- Keep strict structured output and `extra="forbid"` at the provider boundary.
- Only Repair Proposer may author repair operations or a diff; Repair Reviewer may not author or modify either.
- Backend owns checksums, IDs, fingerprints, lineage, commands, gates, persistence, apply, and validation.
- Human approval remains mandatory before apply.
- Existing v1 artifacts and legacy artifact sidecars remain readable and immutable.
- No physical-provider-attempt table or migration is added in this patch.

---

### Task 1: Define v2 provider candidates and bound compatibility models

**Files:**
- Modify: `backend/app/services/repair_application_service.py` near `RepairOperation`, `RepairProposal`, and `RepairReview`
- Modify: `backend/app/llm_gateway/azure_gateway.py` near prompt defaults, schema registry, and production policy tuples
- Test: `backend/tests/test_repair_provider_schema_policy.py`
- Test: `backend/tests/test_repair_application_service.py`

**Interfaces:**
- `RepairOperationCandidate` contains only `operation`, `path`, `old_text`, `new_text`, and `content`.
- `RepairProposalCandidate` contains `proposal_format`, `operations`, `unified_diff`, `rationale`, `risk_level`, `validation_targets`, and `limitations`.
- `RepairReviewCandidate` contains decision and review commentary only; it contains no checksum, ID, diff, operation, or gate field.
- New registry names are `repair_proposer_candidate_v2` and `repair_reviewer_candidate_v2`, with matching versioned prompt names.
- Existing persisted `RepairProposal` and `RepairReview` remain readable as the backend-bound v1-compatible shape.

- [ ] **Step 1: Write failing schema tests**

  Assert that v2 candidate JSON schemas reject `failure_evidence_checksum`, `context_pack_checksum`, `proposal_checksum`, `preimage_sha256`, `touched_files`, IDs, fingerprints, commands, gates, status, and arbitrary extra fields. Assert that a reviewer candidate containing any operation, unified diff, or patch is rejected.

- [ ] **Step 2: Run the schema tests and verify the expected failures**

  Run the exact candidate-schema test functions in `backend/tests/test_repair_provider_schema_policy.py` and `backend/tests/test_repair_application_service.py`. The failures must show that the v2 models and registry names are not yet present.

- [ ] **Step 3: Implement the minimum v2 models and registry entries**

  Keep the current size limits and `Literal` vocabularies. Register v2 prompt/schema names without changing v1 registrations. Keep all models strict with `extra="forbid"`.

- [ ] **Step 4: Run the same schema tests and verify they pass**

  Confirm v2 schemas reject every backend-owned field and v1 persisted payload helpers still validate.

- [ ] **Step 5: Commit the contract changes**

  Commit only the candidate models, registry/prompt definitions, and their focused tests with message `fix(transformer): separate repair candidate contracts`.

### Task 2: Bind proposer and reviewer output to fresh backend authority

**Files:**
- Modify: `backend/app/services/repair_application_service.py` in `propose`, `review`, `_attempt_context`, `_call`, `validate_proposal`, `_recover_completed`, `_persist_failure`, and `_persist_call`
- Modify: `backend/app/services/patch_apply_service.py` only where the existing parser can be reused to derive canonical touched files
- Test: `backend/tests/test_repair_application_service.py`
- Test: `backend/tests/test_patch_apply_service.py`

**Interfaces:**
- Candidate validation returns untrusted content only.
- A backend binding step returns the existing persisted `RepairProposal` shape with injected evidence checksums, derived preimages, canonical touched files, normalized validation targets, and backend lineage stored in the existing attempt/invocation/artifact records.
- A backend binding step returns the existing persisted `RepairReview` shape with the active proposal checksum inserted by the server.
- `_recover_completed()` returns a result only after validating stored artifact identity and current attempt lineage.

- [ ] **Step 1: Write failing binding tests**

  Add tests proving that a candidate without checksums succeeds after backend injection; provider-supplied checksum/preimage/touched-file values are rejected; preimages and touched files come from the active workspace/content; reviewer output cannot contain a diff; and the reviewer is bound to the active proposal checksum.

- [ ] **Step 2: Run the binding tests and verify the expected failures**

  Run only the new service tests and existing semantic validation tests. Confirm failures occur because the current service still validates the full provider-owned models.

- [ ] **Step 3: Implement candidate-to-bound normalization**

  Preserve all existing semantic checks. Normalize safe paths, derive operation preimages from the active workspace, derive touched files from operations or diff headers, and allow only backend-supported validation targets. Do not trust candidate checksums or target commands.

- [ ] **Step 4: Implement server-side review binding**

  Remove the provider checksum equality requirement for v2. Reload the active proposal artifact and insert its exact backend checksum into the persisted review result. Preserve historical v1 review loading.

- [ ] **Step 5: Run the binding tests and verify they pass**

  Confirm no proposal/review success artifact is written for malformed or semantically invalid candidates.

- [ ] **Step 6: Commit the binding changes**

  Commit with message `fix(transformer): bind repair output to backend authority`.

### Task 3: Add genuine stale-state protection and safe logical replay

**Files:**
- Modify: `backend/app/services/repair_application_service.py`
- Test: `backend/tests/test_repair_application_service.py`
- Test: `backend/tests/test_transformer_repair_failure_governance.py`

**Authority snapshot:** Capture before the provider call, after logical invocation start and before transport:

```text
run_id, stage_id, repair_attempt_id, attempt_number,
failure_artifact_id/checksum, context_artifact_id/checksum,
proposal_artifact_id/checksum for review,
workspace_binding_id/path/fingerprint, live workspace fingerprint,
stage_plan_checksum, run state_version/current node,
parent lineage, prompt version, schema version, request checksum
```

**Post-provider algorithm:** Reload all rows and immutable artifacts in a fresh scope, recompute the live workspace fingerprint, compare every authority value, and fail with the role-specific stale code before semantic success validation if any value differs. Repeat the same comparison in the success transaction using a conditional state/version check.

- [ ] **Step 1: Write failing drift and race tests**

  Mutate evidence lineage, workspace state, active attempt, stage plan, workspace binding, and proposal lineage during a fake provider call. Assert the operation fails closed, persists bounded failure evidence only, and leaves no proposal/review artifact. Add a test where authority changes between the post-call comparison and success persistence; assert the conditional write refuses success.

- [ ] **Step 2: Run the tests and verify they fail for the current missing comparison**

  Run only the new stale-state functions. The current implementation should incorrectly persist or continue after at least one simulated mutation.

- [ ] **Step 3: Implement the authority snapshot and comparison**

  Keep context artifacts immutable and do not regenerate them on replay. Use `run_id` in every invocation query. Persist stale failures through the existing safe failure-artifact path, including provider transport metadata.

- [ ] **Step 4: Make completed replay lineage-aware**

  A completed invocation may replay only when its artifact checksum, attempt IDs/checksums, role, and current backend lineage still match. Otherwise fail closed.

- [ ] **Step 5: Make duplicate recovery conditional**

  Preserve the state machine: completed artifact replay, failed reuse, non-transporting in-progress retry, and transporting in-progress uncertainty. Never reset an in-progress transporting row, including after a duplicate-key race.

- [ ] **Step 6: Run stale, replay, and concurrency tests and verify they pass**

  Include completed replay with zero provider calls, failed replay reusing one logical invocation, transporting invocation protection, cross-run key isolation, and one logical usage record.

- [ ] **Step 7: Commit the persistence/stale-state changes**

  Commit with message `fix(transformer): enforce repair authority freshness`.

### Task 4: Bind downstream graph, G10, gate, apply, and revalidation

**Files:**
- Modify: `backend/app/orchestration/transformer_graph.py` in `_propose_repair`, `_review_repair`, `_create_repair_gate`, `_apply_repair`, and `_start_revalidation`
- Modify: `backend/app/services/stage_gate_service.py` in `create` and `decide`
- Modify: `backend/app/services/patch_apply_service.py` at the apply boundary if required for checksum naming/binding
- Test: `backend/tests/test_transformer_repair_failure_governance.py`
- Test: `backend/tests/test_stage_gate_service.py`
- Test: `backend/tests/test_patch_apply_service.py`

**Bound G10 requirements:** Build from a fresh `RepairAttemptModel` reload and include the active failure/context lineage, proposal/review artifact IDs and checksums, proposer/reviewer invocation IDs, backend diff checksum, workspace fingerprint, stage-plan checksum, state version, policy report, and a backend lineage checksum. Do not modify frozen shared schemas; use an adapter if required.

- [ ] **Step 1: Write failing downstream tests**

  Assert that G10 creation, approval, and apply reject an inner proposal/review/attempt mismatch even when the outer package checksum is valid. Assert human approval remains required. Assert revalidation uses normalized backend targets.

- [ ] **Step 2: Run the downstream tests and verify the expected failures**

  Run only the G10/gate/apply governance tests. Current gate behavior should accept at least one inner-lineage mismatch.

- [ ] **Step 3: Implement fresh G10 reload and inner validation**

  Rebuild the package from current database lineage, validate it in `StageGateService`, and recheck the approved proposal checksum immediately before apply.

- [ ] **Step 4: Route only backend-bound targets to revalidation**

  Keep command selection in the backend allowlist/map. Never execute an LLM-authored command or gate.

- [ ] **Step 5: Run downstream tests and verify they pass**

  Confirm accepted G10 still requires human approval and valid workspace/state bindings.

- [ ] **Step 6: Commit the downstream changes**

  Commit with message `fix(transformer): enforce bound repair lineage downstream`.

### Task 5: Compatibility, current-run recovery tests, and review preparation

**Files:**
- Modify: `backend/tests/test_llm_gateway.py`
- Modify: `backend/tests/test_repair_provider_schema_policy.py`
- Modify: `backend/tests/test_transformer_repair_failure_governance.py`
- Modify: `backend/tests/test_transformation_api.py` only for offline restart/idempotency coverage
- Test: existing artifact-store compatibility tests

- [ ] **Step 1: Add historical compatibility tests**

  Load existing v1 proposal/review artifacts and legacy sidecars without rewriting them. Assert new v2 invocations record exact registry prompt/schema versions.

- [ ] **Step 2: Add current-run recovery tests**

  Assert a blocked run with a failed proposer invocation can be requeued by the existing restart/state-version path without changing evidence artifacts. Assert an uncertain transporting invocation remains uncertain after wake.

- [ ] **Step 3: Run the exact focused pytest set**

  Run only the changed test files/functions, never the full suite and never a live service.

- [ ] **Step 4: Run Ruff, py_compile, and diff checks**

  Run Ruff only on changed Python files, `py_compile` on changed Python files, and `git diff --check`.

- [ ] **Step 5: Obtain two independent reviews**

  Reviewer 1 checks schema ownership, candidate/bound separation, compatibility, and stale-state correctness. Reviewer 2 checks transactions, races, replay, G10 lineage, apply safety, and current-run recoverability. Fix every CRITICAL and IMPORTANT finding and rerun affected focused tests.

- [ ] **Step 6: Commit any review fixes separately**

  Use a focused `fix(transformer): address repair review findings` commit only for validated review corrections.

### Task 6: Push and final verification

- [ ] **Step 1: Verify the final commit range**

  Confirm the plan commit precedes all implementation commits and every implementation commit is based on `840b7546d5cfe5924c020e87172cd68199fbbbed`.

- [ ] **Step 2: Confirm protected-file and preserved-run invariants**

  Confirm `frontend/next-env.d.ts` is the only pre-existing modification and is absent from every commit. Confirm no preserved-run DB/artifact path was written.

- [ ] **Step 3: Push the same branch**

  Push `fix/transformer-repair-llm-wiring` without force. Verify `git rev-list --left-right --count HEAD...origin/fix/transformer-repair-llm-wiring` returns `0 0`.

- [ ] **Step 4: Report evidence and manual recovery procedure**

  Report exact SHAs, files/symbols, tests/results, review findings, status/diff stat, and the manual restart procedure. Do not execute the restart.

## Migration verdict

No Alembic migration is expected. Existing `RepairAttemptModel`, `LlmInvocationModel`, `ArtifactMetadataModel`, and `UsageCostRecordModel` contain the logical lineage and replay fields required for this patch. Physical provider-attempt history is explicitly deferred; adding it later requires an append-only table and gateway instrumentation, not overloading the logical invocation row.

## Recovery procedure to document but not execute

After deployment, read the existing proposer invocation state. If it is `failed`, call the existing transformation restart endpoint with a fresh restart idempotency key and current expected state version. The same attempt and immutable evidence artifacts must be reused. If it is `in_progress` with `transport_started=True`, do not retry automatically; retain `REPAIR_INVOCATION_UNCERTAIN` for explicit operator resolution.
