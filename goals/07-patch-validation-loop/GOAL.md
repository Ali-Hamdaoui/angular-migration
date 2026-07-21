# G07 — Exact Patch Apply, G11, and Loop Protection

## Identity

| Field | Value |
|---|---|
| Folder | `07-patch-validation-loop` |
| Base branch | `goal` |
| Assigned branch | `hermes/07-patch-validation-loop` |
| Worktree | `/home/ubuntu/amfa-worktrees/07-patch-validation-loop` |
| External runtime | `/home/ubuntu/amfa-runtime/07-patch-validation-loop` |
| Backend / frontend | `8307` / `3307` |
| Jira features | AMFA-217, AMFA-218, AMFA-219 |
| Jira subtasks | 12 tasks |

## Objective

Validate and apply only the exact persisted approved diff, perform patch preflight, resume the normal validation pipeline through G11, and stop no-progress loops with safe rollback or stage reconstruction.

## Feature coverage

| Backlog feature | Jira | Title | Exact backlog dependencies |
|---|---|---|---|
| S4-F07 | AMFA-217 | Validate and apply only the exact persisted repair diff | S4-F06 |
| S4-F08 | AMFA-218 | Run patch preflight, resume normal validation, and decide G11 | S4-F07, S3-F13 |
| S4-F09 | AMFA-219 | Stop no-progress repair loops and reconstruct or roll back safely | S4-F08 |

## Goal dependencies

- `G04`
- `G06`

All ten sessions may begin together using frozen contracts. Do not absorb unavailable dependencies. Branch-local completion and integrated completion are separate as defined in root `AGENTS.md`.

## Required reading order

1. Root `AGENTS.md`.
2. `goals/shared/ARCHITECTURE.md`, `UPSTREAM_SPRINT2_BOUNDARY.md`, `PARALLEL_EXECUTION.md`, `RUNTIME_ISOLATION.md`, `HERMES_RUNTIME_POLICY.md`, and `LIVE_REPOSITORY_VERIFICATION.md`.
3. `CURRENT_CODE_MAP.md`, `CROSS_GOAL_CONTRACTS.md`, `SOURCE_CONTRACT.md`, `JIRA.md`, `ACCEPTANCE.md`, `OWNERSHIP.yaml`, and `MANUAL_TEST_PLAN.md`.
4. Every file in `tasks/` in `TASK_INDEX.md` order.
5. Applicable shared coding/testing/security/database/API/documentation/completion standards.
6. Live code/tests/docs on the assigned branch.

## Startup and planning

Create `evidence/current-state-gap-map.json`, `dependency-status.json`, and planned `shared-file-changes.json` before production edits. Reuse existing code; do not add parallel authorities. Verify the frozen contracts consumed/provided by this goal.

## Implementation

Execute every Jira task. Each task follows planner → sole implementer → independent reviewer → conditional fixer/re-review on FAIL. Keep the implementation vertical: backend/domain, persistence/API/events/artifacts, frontend/SSE, tests/security, and exact acceptance evidence.

## Runtime and manual validation

Use `/home/ubuntu/amfa-runtime/07-patch-validation-loop` and ports 8307/3307. Run exact manual cases in `manual-tests/` after automated green. Full Angular fixtures must be generated outside Git and submitted through production APIs.

## Documentation and audits

Generate as-built docs only after runtime green, then run the two independent final audits. Correct implementation/docs and rerun affected tests until both pass.

## Completion and push

Validate `evidence/completion.json` against `goals/shared/contracts/goal_completion.schema.json`. Push only `hermes/07-patch-validation-loop` when `branch_ready=true`, all intended changes are committed, and the worktree is clean. `integration_verified` remains false until integration evidence exists.

```bash
git push --set-upstream origin hermes/07-patch-validation-loop
```

Never push protected branches, merge, rebase, cherry-pick, force-push, edit Jira, or modify another worktree.
