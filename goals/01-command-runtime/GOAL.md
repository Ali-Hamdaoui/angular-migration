# G01 — Governed Command Runtime

## Identity

| Field | Value |
|---|---|
| Folder | `01-command-runtime` |
| Base branch | `goal` |
| Assigned branch | `hermes/01-command-runtime` |
| Worktree | `/home/ubuntu/amfa-worktrees/01-command-runtime` |
| External runtime | `/home/ubuntu/amfa-runtime/01-command-runtime` |
| Backend / frontend | `8301` / `3301` |
| Jira features | AMFA-140, AMFA-141, AMFA-142, AMFA-143 |
| Jira subtasks | 16 tasks |

## Objective

Build the sole structured command path: registry and policy, authoritative execution evidence, durable live logs, and JobSupervisor ownership with leases, timeout, cancellation, and reconnect-safe frontend projection.

## Feature coverage

| Backlog feature | Jira | Title | Exact backlog dependencies |
|---|---|---|---|
| S3-F01 | AMFA-140 | Register structured commands and reject arbitrary shell execution | S2-F07 |
| S3-F02 | AMFA-141 | Execute one approved command and persist authoritative command evidence | S3-F01 |
| S3-F03 | AMFA-142 | Stream live command logs and recover after browser reconnect | S3-F02 |
| S3-F04 | AMFA-143 | Own commands with JobSupervisor, leases, timeout, and explicit cancellation | S3-F02, S3-F03 |

## Goal dependencies

- `S2-F07`

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

Use `/home/ubuntu/amfa-runtime/01-command-runtime` and ports 8301/3301. Run exact manual cases in `manual-tests/` after automated green. Full Angular fixtures must be generated outside Git and submitted through production APIs.

## Documentation and audits

Generate as-built docs only after runtime green, then run the two independent final audits. Correct implementation/docs and rerun affected tests until both pass.

## Completion and push

Validate `evidence/completion.json` against `goals/shared/contracts/goal_completion.schema.json`. Push only `hermes/01-command-runtime` when `branch_ready=true`, all intended changes are committed, and the worktree is clean. `integration_verified` remains false until integration evidence exists.

```bash
git push --set-upstream origin hermes/01-command-runtime
```

Never push protected branches, merge, rebase, cherry-pick, force-push, edit Jira, or modify another worktree.
