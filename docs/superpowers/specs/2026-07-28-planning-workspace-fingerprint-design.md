# Planning Workspace Fingerprint Recovery Design

## Goal

Preserve the approved G03 physical workspace fingerprint through Analysis/G04 and Feasibility/G05, provide an immutable-safe recovery path for legacy null-fingerprint runs, and ensure planning failures and retries are represented truthfully.

## Scope

The change is limited to the supplied handoff patch:

- Backend-owned G03 fingerprint derivation and mismatch rejection.
- Legacy G04 reconciliation during new feasibility generation.
- Fingerprint-required feasibility and G05 approval safeguards.
- Step-local planning retry counters and usable job correlation IDs.
- Frontend regeneration action, approval guard, and terminal failure wording.
- Focused regression coverage.

Historical evidence remains append-only. No database backfill, unrelated refactor, commit, push, or repair of pre-existing environment failures is included.

## Architecture and Data Flow

Approved G03 is the sole authority for the physical workspace identity. The Analysis evidence service derives the fingerprint from G03 and rejects any conflicting client value. Planning input resolution validates a fingerprint-bearing G04 against G03; a legacy null G04 is rebound only for the new feasibility command, leaving the historical row unchanged.

Compatibility creation rejects missing bindings, and G05 approval rejects/stales an unbound package. Successful workflow transitions reset the attempt counter so each step has its own retry budget. New planning jobs receive a deterministic `planning:<run_id>` correlation fallback.

The frontend exposes regeneration when the current package or terminal planning failure indicates a missing fingerprint. Regeneration uses the separate `feasibility-rebind` idempotency namespace, and G05 approval is disabled until a fingerprint is present. Terminal failures show `(terminal)` instead of implying remaining retries.

## Error and State Handling

- Missing approved G03 fingerprint fails closed with `PLANNING_WORKSPACE_FINGERPRINT_MISSING`.
- G03/G04 mismatch fails closed with `PLANNING_G04_WORKSPACE_FINGERPRINT_MISMATCH`.
- Missing feasibility/G05 binding cannot create or approve a gate.
- `/plan` and `/plan/review` remain absent until their persisted evidence exists.
- Existing failed planning jobs are not reused by regeneration.

## Validation

Run focused backend fingerprint, feasibility, planning, and persistence tests first; then relevant regression tests. Run frontend Vitest/typecheck/build if dependencies are available. Always run `git diff --check` and report environment-level failures separately.

## Out of Scope

Transformation execution, command execution, external source mutation, unrelated test-import/dependency failures, branch operations, commits, and pushes.
