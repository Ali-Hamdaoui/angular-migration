# Plan: Idempotent Transformer Failure Classification

**Date:** 2026-07-31
**Branch:** `fix/transformer-classification-idempotency`
**Base SHA:** `6d5bfb50dea75f6ab0ecb1ec78c86fb9242b332c`
**Scope:** Backend Transformer `classify_failure` persistence livelock. No frontend changes. No schema migration.

---

## 1. Objective

Make failure classification exactly-once and replay-safe, and terminate the
deterministic `classify_failure` livelock by classifying the persistence defect
as non-retryable operator-blocked state. Preserve the Angular/Jest peer-conflict
failure as the valid triggering failure. Protect Analysis, Planning, Planning
Reviewer, G06/G07, and command template authority.

## 2. Proven root cause (verified against preserved evidence and code)

1. **Duplicate registration in one transaction.** `TransformerOrchestrator._classify_failure`
   registers the same three artifacts twice: the Angular-update branch loop added by
   commit `7714b68` (`backend/app/orchestration/transformer_graph.py:700-702`) runs for
   `REPAIRABLE_SOURCE` without returning, then control falls through to the pre-existing
   common loop (`transformer_graph.py:721-723`). Both loops call
   `TransformerStageService.register_artifact` for the identical `(failure, route_artifact, context)`
   `StoredArtifact` objects.

2. **Guard is blind to pending objects.** `register_artifact`
   (`backend/app/services/transformer_stage_service.py:277`) dedupes with
   `session.get(ArtifactMetadataModel, id) is None`. Sessions are created with
   `autoflush=False` (`backend/app/repositories/session.py:49`), so `session.get()` cannot
   see instances added but not yet flushed (identity-map key is `None` until flush).
   Both adds stay pending; `commit()` flushes a 6-row `executemany` with three duplicate
   primary keys -> `sqlite3.IntegrityError: UNIQUE constraint failed: artifact_metadata.id`
   (`session_scope`, `session.py:69`). Empirically reproduced in-memory.

3. **Livelock mechanics.** The worker claim (`transformation_continuation_service.py:150-200`)
   commits in its own scope: `attempt + 1`, `state_version + 1`, 120 s lease. The node scope
   rolls back completely after the IntegrityError (`session.py:70-72`). `run_forever`
   (`transformer_worker.py:80-89`) catches everything and logs; after lease expiry
   `claim_next` re-claims the still-`running` continuation with **no attempt cap**.
   Each iteration writes fresh uuid4 artifact ids and `__vN` versioned files on disk, then
   fails identically. `state_version` arithmetic verified: 1 (create) + 16 (claims) + 10
   (node transitions) + 3 (wake_sequence) = 30. `repair_attempts` = 0 rows; 7 orphaned
   filesystem versions per failure file with zero committed `artifact_metadata` rows.

4. **Stable identity exists but is unused.** `failure_fingerprint` (sha256 of the normalized
   failure) is content-address-like and stable per replay, but `artifact_metadata.id` is
   `"metadata-" + uuid4-per-write`, so replay creates new rows instead of reusing.

## 3. Call path (verified)

| Step | Symbol | Location | Effect |
|---|---|---|---|
| 1 | `run_forever` / `run_once` | transformer_worker.py:40-89 | claim committed scope; catch-all; no escalation |
| 2 | `claim_next` | transformation_continuation_service.py:150-200 | attempt+1, state_version+1, lease+120 s; no cap |
| 3 | `_advance` dispatch | transformer_graph.py:1249-1253, 154-155 | `current_node == "classify_failure"` |
| 4 | scope #1: `_owned`, prior fingerprints, `collect` | transformer_graph.py:662-676 | read-only |
| 5 | `write` / `write_context_pack` (external work) | failure_evidence_service.py:116-180 | writes evidence + route + context files |
| 6 | `snapshot_workspace` | transformer_graph.py:687-695 | filesystem checkpoint copy |
| 7 | scope #2: `_owned`, `_is_angular_update_failure` | transformer_graph.py:696-698 | True (step `angular_update-0` FAILED) |
| 8 | registration loop #1 | transformer_graph.py:700-702 | 3 pending adds (invisible to guard) |
| 9 | registration loop #2 (fall-through) | transformer_graph.py:721-723 | 3 more pending adds |
| 10 | `RepairAttemptModel` add + `_queue("propose_repair")` | transformer_graph.py:741-779 | pending |
| 11 | `session_scope` commit -> flush -> executemany | session.py:69 | 6 rows, 3 duplicate PKs -> IntegrityError |
| 12 | rollback + re-raise; `run_forever` logs | session.py:70-72; transformer_worker.py:85-87 | nothing durable; retry forever |

## 4. Reconciled design

Two disjoint implementation scopes on two branches/worktrees from PLAN_SHA,
integrated on `fix/transformer-classification-idempotency`.

### Scope A — Persistence: single registration and idempotent evidence

**Owner: Implementation Agent 1.** Files: `backend/app/services/transformer_stage_service.py`,
`backend/app/services/failure_evidence_service.py`, plus their focused tests. NOT the graph.

- **A1. Pending-aware dedup in `register_artifact`** (`transformer_stage_service.py:276-292`):
  keep the `session.get` fast path, then also scan `session.new` (and `session.dirty`) for an
  `ArtifactMetadataModel` with the same id and skip the `add` when present. Idempotent within a
  session regardless of caller duplication. No rollback in the helper; no broad except.
- **A2. Deterministic metadata identity.** Compute the metadata id deterministically from
  `(run_id, stage_id, artifact_type, relative_path, checksum)` via sha256
  (`"metadata-" + hex`). Replay of the identical classification then yields the same id, making
  the guard effective across sessions. If a committed row with the same id exists, validate
  run/stage/artifact type/relative path/checksum bindings; mismatch must fail loudly
  (AGENTS.md §7: same key, different payload fails). No new IDs per retry; no uuid4 churn.
- **A3. Committed-evidence replay.** New `FailureEvidenceService` lookup: given
  `session`, `continuation`, `failure_fingerprint`, return the committed evidence triple
  (`failure`, `route_artifact`, `context` StoredArtifacts reconstructed from
  `artifact_metadata` + files) **only when** run id, stage id, command/source binding,
  artifact types, relative paths, and checksums all match. Deterministic lookup in a short
  read-only transaction; external writes still happen outside DB transactions (AGENTS.md §7).
- **A4. Tests** (new focused tests, existing style): pending-duplicate registration is a no-op;
  deterministic id stability; replay returns same committed artifacts and checksums; replay
  creates no additional versioned files; mismatch fails.

### Scope B — Orchestration: atomic lifecycle and livelock termination

**Owner: Implementation Agent 2.** Files: `backend/app/orchestration/transformer_graph.py`,
(worker only if required, prefer not), plus `backend/tests/test_command_terminal_lifecycle.py`
and new focused test file(s). NOT the metadata service internals.

- **B1. Single registration.** Hoist exactly one `register_artifact` pass for
  `(failure, route_artifact, context)` immediately after `_owned` in scope #2
  (`transformer_graph.py:697`); delete both loops (700-702 and 721-723). Evidence persists on
  all routes (transient retry, block, repairable) exactly once.
- **B2. Evidence reuse on replay.** Before `write`/`write_context_pack`
  (`transformer_graph.py:681-686`), call the Scope-A replay lookup; when valid committed
  evidence exists for the same failure identity, reuse it instead of rewriting files
  (no `__vN` growth, no new uuid4 ids). When absent, write as today. Workspace fingerprint
  derivation stays as-is.
- **B3. Deterministic defect -> operator-blocked, no retry.** Catch
  `sqlalchemy.exc.IntegrityError` raised from the scope-#2 commit (the deterministic metadata
  duplicate class). In a **fresh** short scope (never the failed session), set
  `status = "blocked"`, `last_error_code = "ARTIFACT_METADATA_DUPLICATE"`,
  `last_error_message` with artifact ids/paths, `worker_id = None`,
  `lease_expires_at = None`, `state_version += 1`. `claim_next` never claims `blocked`, so
  automatic retry stops; explicit operator recovery (requeue) is required. Only
  `IntegrityError` (deterministic) is blocked; transient failures (e.g. locked DB) still
  propagate and retry per existing policy. No broad exception swallowing.
- **B4. Attempt-scoped cleanup.** Track the relative paths written by this attempt (evidence,
  route, context + `.meta.json` sidecars, from the store refs). On deterministic failure,
  remove **only** those exact paths, resolved strictly within the run root via the artifact
  store's own path resolution; refuse to delete any path whose artifact id has a committed
  `artifact_metadata` row or which resolves outside the run root. Never touch previously
  committed immutable evidence. Publication boundary stays the metadata commit (`finalized_at`
  in the committed row); files only become authoritative after commit.
- **B5. Tests** (required behaviors 1-12): once-registration, three semantic artifacts,
  replay idempotency, no extra versioned files, duplicate invocation idempotent, two-worker
  exclusion, no orphan finalization on IntegrityError, cleanup cannot escape run root or
  remove other artifacts, one repair attempt + route to `propose_repair`, blocked state durable
  and not re-claimed, transient retry preserved, original Angular command execution immutable.

## 5. Required behavior tests (across both scopes)

1. Failure classification inserts every metadata id once.
2. One peer-dependency failure produces exactly three semantic artifacts.
3. Replay returns the same committed artifacts and checksums.
4. Replay creates no additional versioned files.
5. Duplicate invocation from the same worker is idempotent.
6. Two workers cannot create duplicate classification evidence.
7. IntegrityError before commit leaves no newly finalized orphan artifacts.
8. Cleanup cannot remove another artifact or escape the run root.
9. Successful classification creates one repair attempt and routes once to `propose_repair`.
10. Deterministic persistence failure becomes durable `blocked`/`ARTIFACT_METADATA_DUPLICATE`
    and is not repeatedly reclaimed.
11. Transient failures remain retryable per existing policy.
12. The original Angular command execution remains immutable.

## 6. Explicitly out of scope (protected)

Angular/Jest peer conflict; Analysis/Planning/Planning Reviewer/G06/G07 semantics; Angular
command templates v1/v2; frontend; the preserved database, logs, and run artifacts; schema
migrations; worker lease policy beyond blocking; unrelated runtime-launcher behavior.
No full test suites, no live migration, no API/worker runs against the preserved database.

## 7. Validation

- New focused test files and the directly affected existing files only
  (`test_command_terminal_lifecycle.py`, `test_failure_evidence_service.py` and any test file
  directly touching the changed helpers).
- Scoped Ruff on changed Python files; `git diff --check`.
- Recovery of the preserved run: **not executed**; documented procedure only
  (copy DB to sandbox, requeue continuation, verify classify_failure commits once).
