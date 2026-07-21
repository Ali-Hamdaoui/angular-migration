# G05 — Failure Evidence, C-Lite, and Repair Context

## Identity

| Field | Value |
|---|---|
| Folder | `05-failure-diagnostics-context` |
| Base branch | `goal` |
| Assigned branch | `hermes/05-failure-diagnostics-context` |
| Worktree | `/home/ubuntu/amfa-worktrees/05-failure-diagnostics-context` |
| External runtime | `/home/ubuntu/amfa-runtime/05-failure-diagnostics-context` |
| Backend / frontend | `8305` / `3305` |
| Jira features | AMFA-211, AMFA-212, AMFA-213 |
| Jira subtasks | 12 tasks |

## Objective

Build immutable FailureEvidence from real failed commands, classify failures deterministically with C-Lite, and create a bounded, sanitized, checksum-bound RepairContextPack without allowing repository-wide model browsing.

## Feature coverage

| Backlog feature | Jira | Title | Exact backlog dependencies |
|---|---|---|---|
| S4-F01 | AMFA-211 | Capture FailureEvidence and parse deterministic diagnostics | S3-F02, S3-F12 |
| S4-F02 | AMFA-212 | Route failures with C-Lite and show environment or retry actions | S4-F01 |
| S4-F03 | AMFA-213 | Build and inspect a bounded sanitized RepairContextPack | S4-F01, S4-F02 |

## Goal dependencies

- `G01`
- `G04`

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

Use `/home/ubuntu/amfa-runtime/05-failure-diagnostics-context` and ports 8305/3305. Run exact manual cases in `manual-tests/` after automated green. Full Angular fixtures must be generated outside Git and submitted through production APIs.

## Documentation and audits

Generate as-built docs only after runtime green, then run the two independent final audits. Correct implementation/docs and rerun affected tests until both pass.

## Completion and push

Validate `evidence/completion.json` against `goals/shared/contracts/goal_completion.schema.json`. Push only `hermes/05-failure-diagnostics-context` when `branch_ready=true`, all intended changes are committed, and the worktree is clean. `integration_verified` remains false until integration evidence exists.

```bash
git push --set-upstream origin hermes/05-failure-diagnostics-context
```

Never push protected branches, merge, rebase, cherry-pick, force-push, edit Jira, or modify another worktree.
