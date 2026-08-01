# Task 2 Report: backend repair authority binding

## Status

Completed on `fix/transformer-repair-llm-wiring` from base
`297a124eb26b7bd222bd2cd35b027dd914b6fff5` under the required commit message
`fix(transformer): complete backend repair binding`.

## Implementation

- Kept the v2 proposer/reviewer provider schemas strict and provider-only.
- Bound proposal evidence and context checksums from the active repair-attempt
  context; candidate attempts to provide checksums, preimages, touched files,
  commands, or other authority fields remain rejected by `extra="forbid"`.
- Normalized operation and unified-diff paths through the existing repair path
  safety policy before persistence.
- Derived operation preimage SHA-256 values from the active workspace and
  canonical `touched_files` from normalized operation paths or diff headers.
- Normalized and de-duplicated validation targets and restricted proposer and
  reviewer targets to the backend-supported `build`, `test`, and `lint` names.
  Command selection remains downstream backend-owned.
- Reloaded review context after provider output and bound the review to the
  checksum read from the active immutable proposal artifact, never candidate
  output or a stale row value.
- Added repair-attempt lineage to proposal, review, and failure artifact
  envelopes.
- Linked failure artifacts directly from the logical invocation through its
  existing `artifact_ids` and `artifact_checksums` fields. The immutable
  artifact store continues versioning repeated writes instead of overwriting
  prior evidence.
- Preserved the v1-compatible proposal/review JSON shape and historical
  completed-invocation artifact recovery path.
- No `PatchApplyService` production extraction was needed; its existing
  focused apply-boundary selector remained green.

## TDD evidence

The first valid behavioral RED run used the new binding selectors plus existing
semantic/apply regressions. It produced `4 failed, 7 passed in 7.19s`:

- operation and unified-diff binding persisted `src/./app.ts` instead of the
  canonical `src/app.ts`;
- proposer validation accepted the unknown `deploy` target;
- reviewer validation accepted the unknown `deploy` target.

A self-review mutation check removed immutable-artifact checksum binding and
ran
`test_review_binds_immutable_active_proposal_artifact_checksum`. It failed as
expected because review bound `sha256:stale-row-value`; restoring the binding
produced `1 passed in 2.59s`.

The final exact focused selector run covered candidate authority rejection,
checksum/preimage/touched-file injection, canonical operation and diff paths,
the target allowlist, reviewer restrictions and binding, invalid-candidate
artifact behavior, v1 recovery, Task 1 replay provenance, and patch apply:

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/test_repair_application_service.py::test_proposal_semantics_bind_preimage_and_safe_path tests/test_repair_application_service.py::test_reviewer_candidate_schema_cannot_author_candidate_content tests/test_repair_application_service.py::test_reviewer_candidate_schema_rejects_unified_diff_field tests/test_repair_application_service.py::test_proposal_rejects_stale_preimage_duplicate_paths_and_mixed_formats tests/test_repair_application_service.py::test_proposal_rejects_lockfiles_and_binary_targets tests/test_repair_application_service.py::test_proposer_candidate_schema_rejects_backend_authority_fields tests/test_repair_application_service.py::test_propose_persists_failed_row_for_schema_failure_after_transport tests/test_repair_application_service.py::test_repair_runtime_uses_v2_candidates_and_binds_authority_fields tests/test_repair_application_service.py::test_repair_runtime_binds_unified_diff_touched_files tests/test_repair_application_service.py::test_candidate_binding_canonicalizes_paths_targets_and_preimages tests/test_repair_application_service.py::test_unknown_proposer_target_persists_only_linked_failure_artifact tests/test_repair_application_service.py::test_unknown_reviewer_target_persists_no_review_artifact tests/test_repair_application_service.py::test_review_binds_immutable_active_proposal_artifact_checksum tests/test_repair_application_service.py::test_v1_persisted_proposal_and_review_artifacts_still_recover tests/test_repair_application_service.py::test_replayed_v1_invocation_refreshes_v2_provenance_for_success_and_failure tests/test_repair_application_service.py::test_pre_transport_disabled_failure_persists_without_transport tests/test_repair_application_service.py::test_semantic_failure_persists_repair_semantics_stage_without_proposal_artifact tests/test_repair_application_service.py::test_recover_completed_failed_returns_none_and_uncertain_transport_raises tests/test_patch_apply_service.py::test_operations_apply_atomically_with_preimage_and_ledger -q
```

Result: `20 passed in 19.11s`. The final staged-tree rerun also passed all 20
selectors in `20.82s`.

Focused static verification also passed:

```powershell
& '.venv\Scripts\python.exe' -m ruff check app/services/repair_application_service.py tests/test_repair_application_service.py tests/test_patch_apply_service.py
& '.venv\Scripts\python.exe' -m py_compile app/services/repair_application_service.py tests/test_repair_application_service.py tests/test_patch_apply_service.py
```

Result: `All checks passed!`, exit code 0.

## Self-review and scope

The final diff was checked against the Task 2 brief. No stale-state comparison,
logical invocation state-transition, or concurrency behavior was changed;
those remain reserved for Task 3. No service was started, no Azure call or live
migration occurred, no preserved run state was accessed or modified, and no
full suite was run. The pre-existing `frontend/next-env.d.ts` modification was
not edited or staged.

No unresolved Task 2 concerns remain. Task 3 must still add the specified
authority snapshot comparison and race-safe persistence checks.
